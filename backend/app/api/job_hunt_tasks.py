# SPDX-License-Identifier: Apache-2.0
"""任务化自研采集路由：``/api/job-hunt/collect/task*``（可暂停 / 可停止 / 有进度）。

从 ``api/job_hunt.py`` 拆出来（2026-11-11）：那个文件已经越过 500 行预算，而任务化
采集与「开关 / 预览 / 导入 / 黑名单」是两件事——它有自己的生命周期（后台线程、
进度快照、暂停/恢复/停止），单独成模块后两边都不必再挤在一个文件里。

路由前缀与 tag 与原文件一致，所以对外路径没变（``/api/job-hunt/collect/task``），
前端与既有测试无需改动。
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.job_hunt.collect_task import (
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_STOPPED,
    get_collect_manager,
)
from ..services.job_hunt.registry import get_registry
from ..services.job_hunt.settings import get_job_hunt_config
from .job_hunt_shared import acquire_client, is_blocked, read_blocklist_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-hunt", tags=["job-hunt"])


class JobHuntTaskStartIn(BaseModel):
    """启动一次后台采集任务。"""

    site_key: str
    keywords: str = ""
    city: str = ""
    max_pages: int = Field(default=1, ge=1, le=10)
    city_code: str = ""
    # 采集结果是否写进备选岗位暂存区。
    #
    # **默认 True** 是刻意的（2026-11-11）：用户反馈的痛点就是「采完就停」——原来
    # 结果只活在内存里，刷新即丢，也没有后续动作。保留 False 只用于调试，或用户明确
    # 只想看一轮列表、不想留痕的场景。
    persist: bool = True
    # 落库后是否自动补 JD + 评分。关掉它 = 只入库不评分（分数显示为「未评分」）。
    auto_score: bool = True
    # 用哪份简历评分；不传走设置里的默认简历。
    resume_id: int | None = None


@router.post("/collect/task")
def start_collect_task(
    req: JobHuntTaskStartIn, db: Session = Depends(get_db)
) -> dict:
    """启动后台采集任务，立刻返回 task_id。

    与 ``POST /collect``（同步跑完）的区别：这个能查进度、能暂停、能停止。
    同一时刻只允许一个采集任务——两个任务同时驱动同一个浏览器会互相踩。
    """
    config = get_job_hunt_config(db)
    if config.job_hunt_backend != "native":
        raise HTTPException(409, "当前是 sidecar 模式：请先在设置里切到 native")

    adapter = get_registry().resolve(req.site_key)
    if adapter is None:
        raise HTTPException(404, f"未知平台 {req.site_key}")

    manager = get_collect_manager()
    running = manager.active()
    if running is not None:
        raise HTTPException(
            409,
            f"已有采集任务在跑（{running.site_key} {running.message or '进行中'}），请等它结束或先停止",
        )

    # 浏览器必须可用：在启动线程前就检查，避免任务起来后立即失败留下一个"已失败"任务。
    client = acquire_client(db)
    blocklist = read_blocklist_config(db)

    def worker(task: Any) -> None:
        from ..database import SessionLocal
        from ..services.job_hunt.collect_task import control_hook
        from ..services.job_hunt.runner import HuntCriteria, JobHuntRunner, cdp_fetcher

        session = SessionLocal()
        try:
            task.status = "running"
            task.message = "开始采集…"
            extra = {"city_code": req.city_code} if req.city_code else {}
            criteria = HuntCriteria(keywords=req.keywords, city=req.city, extra=extra)
            runner = JobHuntRunner(adapter, max_pages=req.max_pages)
            report = runner.run(
                criteria,
                fetch=cdp_fetcher(client, adapter),
                on_progress=control_hook(task),
            )
            kept = [s for s in report.stubs if not is_blocked(s, blocklist)]
            task.blocked = len(report.stubs) - len(kept)
            task.stubs = [asdict(s) for s in kept]
            task.collected = len(kept)
            task.stopped_reason = report.stopped_reason
            task.stage = "collected"
            task.message = (
                f"采集到 {len(kept)} 条"
                + (f"（黑名单挡掉 {task.blocked} 条）" if task.blocked else "")
            )
            # **这里不设终态**（2026-11-12 修正）：采集只是第一步，后面还有落库、补 JD、
            # 评分。以前在这里就把 status 设成 completed，于是 `finished` 立刻为真——
            # 界面据此判"全部完成"、进度条冲到 100%，而补 JD 明明还在跑（截图里
            # "0/1 成功 0" 与 "已完成" 同时出现就是这个原因）。
            #
            # 与 BossHunter 的差距也在这里：它的采集/评分是**一条串行管道，末端才终态**。
            # 现在改成同样的口径：整个 worker 结束才落终态。

            # 用户主动停止：不再做后续两步，直接终态。
            if report.stopped_reason == "stopped":
                task.status = TASK_STOPPED
                task.stage = "done"
                return

            # ---- 落暂存区（方案 3 的核心：采集结果不再只活在内存里）----
            if req.persist and kept:
                try:
                    candidate_ids = _stage_results(session, task, kept, adapter)
                    task.candidate_ids = candidate_ids
                    task.stage = "staged"
                    # 0 条新建时要说清"都收过了"，而不是"已入库 0 条"——后者看着像失败。
                    task.message = (
                        f"已入库 {len(candidate_ids)} 条备选岗位"
                        if candidate_ids
                        else f"这批 {task.duplicates} 条都已经收过了，没有新岗位"
                    )
                except Exception as exc:  # noqa: BLE001 — 落库失败不该吞掉已采到的结果
                    logger.warning("采集结果落暂存区失败：%s: %s", type(exc).__name__, exc)
                    task.error = f"落库失败：{exc}"
                    return

                # ---- 自动补 JD + 评分 ----
                if req.auto_score and candidate_ids:
                    _auto_score(session, task, candidate_ids, adapter, client, req.resume_id)
                elif not candidate_ids:
                    # 这一批全是重复（都已经在库里或暂存区里）——**没有可补 JD/评分的**。
                    # 必须把 stage 推到终点，否则它会停在 "staged"，而界面把 "staged"
                    # 判成"写入待导入进行中"，于是永远转着蓝圈、总进度卡在 25%。
                    # 实测就是这个：采 12 条全重复，界面看着像卡住，实际早跑完了。
                    task.stage = "done"

            # 全部步骤做完，这才算完成。**必须放在最后**：这里的 status 是界面判断
            # "还要不要等"的唯一依据。
            task.status = TASK_COMPLETED
            task.stage = "done"
            task.message = (
                f"完成：{len(kept)} 条"
                + (f"（黑名单挡掉 {task.blocked} 条）" if task.blocked else "")
            )
        except Exception as exc:  # noqa: BLE001
            # 用户已点停止时，抓取层抛的异常是"停止的副作用"，不是真失败：
            # 此时应如实标 stopped（并保留已采到的部分），不要吓用户。
            if task._stop.is_set():
                task.status = TASK_STOPPED
                task.stopped_reason = "stopped"
                task.message = f"已停止（已采 {task.collected} 条）"
            else:
                task.status = TASK_FAILED
                task.error = f"{type(exc).__name__}: {exc}"
                task.message = "采集失败"
        finally:
            session.close()

    task = manager.start(
        site_key=req.site_key,
        keywords=req.keywords,
        city=req.city,
        max_pages=req.max_pages,
        worker=worker,
    )
    return task.snapshot()


@router.get("/collect/active")
def get_active_collect_task() -> dict:
    """当前还没结束的采集任务（没有则 ``{active: false}``）。

    **为什么需要它**（2026-11-12）：任务快照只活在前端内存里，页面一刷新就 null——
    但采集/补 JD/评分在后台还在跑。用户刷一下页面，进度全没了，只能干等或者以为挂了。

    前端挂载时先问一次这个接口，拿到就把轮询接上；进程重启后任务确实丢了，
    这时返回 ``{active: false}`` 是诚实的（任务生命周期就几分钟，不做持久化）。

    路由必须声明在 ``/collect/task/{task_id}`` **之前**：否则 "active" 会被当成
    task_id 去解析。字面量段优先是 FastAPI 的既定规则，这里显式遵守。
    """
    task = get_collect_manager().active()
    if task is None:
        return {"active": False}
    return {"active": True, **task.snapshot()}


@router.get("/collect/task/{task_id}")
def get_collect_task(task_id: str) -> dict:
    """查任务进度（前端轮询这个）。"""
    task = get_collect_manager().get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在（进程重启后任务会丢失，这是预期行为）")
    return task.snapshot()


@router.get("/collect/task/{task_id}/result")
def get_collect_task_result(task_id: str) -> dict:
    """取任务完整结果（含 stubs）；未完成时返回 409。"""
    task = get_collect_manager().get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if not task.snapshot()["finished"]:
        raise HTTPException(409, "任务还没结束")
    return task.full_result()


@router.post("/collect/task/{task_id}/pause")
def pause_collect_task(task_id: str) -> dict:
    task = get_collect_manager().pause(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task.snapshot()


@router.post("/collect/task/{task_id}/resume")
def resume_collect_task(task_id: str) -> dict:
    task = get_collect_manager().resume(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task.snapshot()


@router.post("/collect/task/{task_id}/stop")
def stop_collect_task(task_id: str) -> dict:
    task = get_collect_manager().stop(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task.snapshot()


# ---------------------------------------------------------------------------
# 采集结果的后续两步：落暂存区 → 补 JD → 评分
# ---------------------------------------------------------------------------


def _stage_results(session: Any, task: Any, stubs: list[Any], adapter: Any) -> list[int]:
    """把采集结果写进备选岗位暂存区，返回新建的候选 id。

    **为什么要落库**（2026-11-11 用户反馈）：之前任务式采集只把结果放在
    ``task.stubs`` 内存里，采完刷新页面就没了，也没有任何后续动作——用户看到的就是
    「采完就停」。落库后才有东西可评分、可勾选。

    去重口径与投递台采集保持一致：先查正式岗位（同链接/同公司同标题），再查暂存区。
    命中就跳过——重复采集同一个岗位不该在备选里堆第二份。
    """
    from ..models.material import CANDIDATE_JOB_PENDING
    from ..services.candidate_jobs import find_staged_candidate, stage_candidate_job
    from ..services.job.job_service import find_job_by_identity

    created: list[int] = []
    duplicates = 0
    for stub in stubs:
        title = (getattr(stub, "title", "") or "").strip()
        if not title:
            continue
        company = (getattr(stub, "company", "") or "").strip()
        url = (getattr(stub, "url", "") or "").strip()

        if find_job_by_identity(session, title=title, company=company, source_url=url):
            duplicates += 1
            continue
        if find_staged_candidate(session, title=title, company=company, source_url=url):
            duplicates += 1
            continue

        candidate = stage_candidate_job(
            session,
            title=title,
            company=company,
            location=(getattr(stub, "location", "") or "").strip(),
            salary=(getattr(stub, "salary_decoded", "") or getattr(stub, "salary_raw", "") or "").strip(),
            source_url=url,
            source=adapter.name,
            task_id=None,
            job_type=(getattr(stub, "job_type", "") or "").strip(),
        )
        candidate.status = CANDIDATE_JOB_PENDING
        created.append(candidate.id)

    session.commit()
    task.duplicates = duplicates
    logger.info("采集落暂存区：新建 %s 条，重复跳过 %s 条", len(created), duplicates)
    return created


def _auto_score(
    session: Any,
    task: Any,
    candidate_ids: list[int],
    adapter: Any,
    client: Any,
    resume_id: int | None,
) -> None:
    """补 JD → 起评分任务。两步都是**尽力而为**：任一步失败都不该让采集任务变成失败。

    为什么先补 JD：评分是拿 JD 正文去比简历。列表页只给标题/公司/地区/薪资，没有
    正文时评分只能拿标题猜，分数没有参考价值。补不到的那些会在发起评分时被标成
    「缺 JD」（见 ``api/candidate_job_score.start_score``），不会硬评。
    """
    from ..services.job_hunt.candidate_jd_backfill import backfill_candidate_jd
    from ..services.job_hunt.candidate_score_task import (
        CandidateScoreBusy,
        get_candidate_score_runner,
    )
    from ..services.job_hunt.runner import cdp_fetcher

    # ---- 1. 补 JD ----
    task.stage = "filling_jd"
    task.jd_total = len(candidate_ids)
    task.message = "正在补抓 JD 正文…"
    try:
        fetch = cdp_fetcher(client, adapter, page_kind="detail")
        # **必须用候选专用的补抓**：detail_backfill 是按 Job 模型读写的，
        # 拿候选 id 传进去会全部被判成"已有 JD"静默跳过（实测 尝试 0/跳过 11）。
        def _jd_progress(done: int, total: int) -> None:
            # 直接改进度字段：轮询接口读的是 task.snapshot()，不需要额外的通道。
            task.jd_done = done
            task.jd_total = total

        report = backfill_candidate_jd(
            session,
            candidate_ids,
            fetch=fetch,
            adapter=adapter,
            limit=len(candidate_ids),
            on_progress=_jd_progress,
        )
        task.jd_filled = report.filled
        # 把失败原因也打出来：只记数量时"尝试 3 / 成功 0"完全查不出为什么。
        logger.info(
            "采集后补 JD：尝试 %s / 成功 %s / 跳过 %s / 无链接 %s%s",
            report.attempted,
            report.filled,
            report.skipped_has_jd,
            report.no_url,
            ("；失败：" + " | ".join(report.errors[:5])) if report.errors else "",
        )
    except Exception as exc:  # noqa: BLE001 — 补不到就按「缺 JD」处理，不阻断评分
        logger.info("采集后补 JD 跳过：%s: %s", type(exc).__name__, exc)

    # ---- 2. 起评分任务 ----
    task.stage = "scoring"
    task.message = "正在评分…"
    try:
        runner = get_candidate_score_runner()
        runner.start(candidate_ids, resume_id=resume_id)
        task.score_started = True
    except CandidateScoreBusy:
        # 已有别的评分任务在跑：只用日志记一笔，让本次采集照常成功结束。
        task.message = "已有评分任务在跑，本次结果待你手动评分"
        logger.info("采集后评分跳过：已有评分任务在运行")
    except Exception as exc:  # noqa: BLE001
        logger.info("采集后评分启动失败：%s: %s", type(exc).__name__, exc)
        task.message = f"评分启动失败：{exc}"

    # 采集线程的全部工作到此结束：把 stage 推到终点。
    # "scoring" 只是**交接给评分任务**的那一刻，不是终点——评分是另一个后台任务，
    # 它的进度看 CandidateScoreTask。stage 留在这里会让采集任务看起来永远没跑完。
    task.stage = "done"
