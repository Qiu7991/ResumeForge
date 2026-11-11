# SPDX-License-Identifier: Apache-2.0
"""任务化自研采集路由：``/api/job-hunt/collect/task*``（可暂停 / 可停止 / 有进度）。

从 ``api/job_hunt.py`` 拆出来（2026-11-11）：那个文件已经越过 500 行预算，而任务化
采集与「开关 / 预览 / 导入 / 黑名单」是两件事——它有自己的生命周期（后台线程、
进度快照、暂停/恢复/停止），单独成模块后两边都不必再挤在一个文件里。

路由前缀与 tag 与原文件一致，所以对外路径没变（``/api/job-hunt/collect/task``），
前端与既有测试无需改动。
"""

from __future__ import annotations

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

router = APIRouter(prefix="/api/job-hunt", tags=["job-hunt"])


class JobHuntTaskStartIn(BaseModel):
    """启动一次后台采集任务。"""

    site_key: str
    keywords: str = ""
    city: str = ""
    max_pages: int = Field(default=1, ge=1, le=10)
    city_code: str = ""


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
            # runner 在用户主动停止时给出 "stopped"（见 runner.run 的 on_progress 分支）。
            task.status = TASK_STOPPED if report.stopped_reason == "stopped" else TASK_COMPLETED
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
