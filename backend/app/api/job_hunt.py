# SPDX-License-Identifier: Apache-2.0
"""自研求职采集路由（``/api/job-hunt/*``）：开关、平台清单、native 采集入口。

与 ``/api/ai-jobs/*``（sidecar 旧路径）**并存**：``job_hunt_backend`` = sidecar（默认）
时本路由的采集入口拒绝执行（409），旧路径照常工作；= native 时走 ``services/job_hunt``
的自研采集（registry 适配器 + runner + CDP 抓取）。设置页的切换项读写的就是这里的
config。
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.job_hunt import JobHuntConfig
from ..services.job_hunt.cursor_store import clear_cursor, load_cursor, save_cursor
from ..services.job_hunt.registry import get_registry
from ..services.job_hunt.runner import JobHuntRunner, HuntCriteria, cdp_fetcher, hash_criteria
from ..services.job_hunt.settings import get_job_hunt_config, save_job_hunt_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-hunt", tags=["job-hunt"])


class JobHuntCollectIn(BaseModel):
    """一次 native 采集的入参。``resume=True`` 时从上次的断点续采。"""

    site_key: str
    keywords: str = ""
    city: str = ""
    max_pages: int = Field(default=1, ge=1, le=10)
    # 平台特有参数原样透传（如智联的城市编码 city_code）。
    city_code: str = ""
    resume: bool = False
    # 采到的岗位是否写进岗位广场（默认写）。关闭时只返回卡片，不落库。
    persist: bool = True
    # 入库后是否对「本次新增」的岗位触发一次批量分析。
    # 复用的批量任务传 ``force=False``：已分析过的岗位服务端自动跳过，
    # 因此同一岗位不会重复评分（不需要新表/新字段）。
    analyze: bool = True
    # 入库后是否后台补抓 JD 正文（评分需要 JD 才能做语义匹配）。
    # 逐个访问详情页、有限速，所以放后台线程，不阻塞本次采集响应。
    backfill_jd: bool = True


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    """开关状态 + 已注册平台清单（设置页/前端切换依据）。"""
    config = get_job_hunt_config(db)
    registry = get_registry()
    return {
        "backend": config.job_hunt_backend,
        "platforms": [{"key": a.key, "name": a.name} for a in registry.all()],
    }


@router.get("/config")
def read_config(db: Session = Depends(get_db)) -> JobHuntConfig:
    return get_job_hunt_config(db)


@router.put("/config")
def write_config(config: JobHuntConfig, db: Session = Depends(get_db)) -> JobHuntConfig:
    """写开关（非法值由 pydantic Literal 直接 422；默认 sidecar，删除键即回默认）。"""
    return save_job_hunt_config(db, config)


@router.post("/collect")
def collect(req: JobHuntCollectIn, db: Session = Depends(get_db)) -> dict:
    """native 采集入口：registry 选适配器 → runner 翻页 → 返回岗位卡片与账目。

    断点续采：``resume=True`` 时读上次游标（AppSetting KV）续翻；每次跑完都落游标，
    完整跑完（no_results / repeated_page）后清掉。
    """
    config = get_job_hunt_config(db)
    if config.job_hunt_backend != "native":
        raise HTTPException(
            409, "当前仍是 sidecar 模式：请在设置里把「自研求职后端」切到 native 后再采集"
        )
    adapter = get_registry().resolve(req.site_key)
    if adapter is None:
        raise HTTPException(
            404, f"未知平台 {req.site_key}；目前支持：{get_registry().supported_names()}"
        )
    client = _acquire_client(db)
    runner = JobHuntRunner(adapter, max_pages=req.max_pages)
    extra = {"city_code": req.city_code} if req.city_code else {}
    criteria = HuntCriteria(keywords=req.keywords, city=req.city, extra=extra)
    cursor = load_cursor(db, adapter.key, hash_criteria(adapter.key, criteria)) \
        if req.resume else None
    report = runner.run(criteria, fetch=cdp_fetcher(client, adapter), cursor=cursor)
    if report.next_cursor is not None:
        if report.stopped_reason in ("no_results", "repeated_page"):
            # 翻到头了：游标使命完成，清掉（下次重开从头）。
            clear_cursor(db, adapter.key, report.next_cursor.criteria_hash)
        else:
            save_cursor(db, report.next_cursor)

    persisted = {"inserted": 0, "skipped_duplicate": 0, "errors": []}
    new_job_ids: list[int] = []
    if req.persist and report.stubs:
        persisted, new_job_ids = _persist_stubs(db, report.stubs)

    # JD 补抓：列表页没有正文，后台线程逐个抓详情页（限速、不阻塞本次响应）。
    # 评分要靠 JD 才能做语义匹配，没有 JD 只能拿标题猜（实测全是中性分 50）。
    if req.backfill_jd and new_job_ids:
        _start_jd_backfill(new_job_ids, adapter)

    analyze_task_id = _start_analysis(db, new_job_ids) if (req.analyze and new_job_ids) else None

    return {
        "stubs": [asdict(stub) for stub in report.stubs],
        "pages_fetched": report.pages_fetched,
        "duplicates": report.duplicates,
        "stopped_reason": report.stopped_reason,
        "errors": report.errors,
        "resumed_from_page": report.resumed_from_page,
        # 入库账目：inserted + skipped_duplicate 应等于 stubs 总数（errors 除外）。
        "persisted": persisted,
        # 有新增岗位且开启分析时给出后台任务 id（前端可轮询进度）。
        "analyze_task_id": analyze_task_id,
    }


def _persist_stubs(
    db: Session, stubs: list[Any]
) -> tuple[dict[str, Any], list[int]]:
    """把采集卡片写进岗位广场。

    去重复用 ``find_job_by_identity``（判据是「同一链接，或同一公司下同名岗位」）——
    与岗位广场手动录入、CSV 导入共用同一份判据，不另写一套。

    返回 ``(账目, 新增岗位 id 列表)``。单条失败不中断整批：记进 errors 后继续。
    """
    from sqlalchemy.exc import SQLAlchemyError

    from ..schemas.job import JobCreate
    from ..services.job.job_service import create_job_record, find_job_by_identity

    ledger: dict[str, Any] = {"inserted": 0, "skipped_duplicate": 0, "errors": []}
    new_ids: list[int] = []

    for stub in stubs:
        try:
            existing = find_job_by_identity(
                db,
                title=stub.title,
                company=stub.company,
                source_url=stub.url,
            )
            if existing is not None:
                ledger["skipped_duplicate"] += 1
                continue
            job = create_job_record(
                db,
                JobCreate(
                    title=stub.title or "(未命名岗位)",
                    company=stub.company,
                    location=stub.location,
                    # salary_decoded 已是明文（BOSS 的字体已在适配器里还原）
                    salary=(stub.salary_decoded or stub.salary_raw)[:64],
                    description="",
                    requirements="",
                    source_url=stub.url,
                    posted_at=stub.posted_at,
                ),
                source="job_hunt",
            )
            db.flush()
            new_ids.append(int(job.id))
            ledger["inserted"] += 1
        except (SQLAlchemyError, ValueError) as exc:
            # 一条脏数据不该让整次采集失败——记下来，继续下一条。
            ledger["errors"].append(f"{stub.title or '(未命名)'}: {exc}")
    db.commit()
    return ledger, new_ids


def _start_jd_backfill(job_ids: list[int], adapter: Any) -> None:
    """后台补抓 JD 正文（限速、只补空 JD）。

    不阻塞采集响应：15 条详情页按 1.5s 间隔要 20+ 秒，挂在请求上会超时。
    浏览器不可用时整批跳过，不影响已经入库的卡片。
    """
    try:
        from ..database import SessionLocal
        from ..services.job_hunt.detail_backfill import start_backfill_in_background
        from ..services.job_hunt.runner import cdp_fetcher

        def _fetch_factory(db: Session) -> Any:
            client = _acquire_client(db)
            return cdp_fetcher(client, adapter)

        start_backfill_in_background(
            SessionLocal, job_ids, fetch_factory=_fetch_factory, adapter=adapter
        )
    except Exception as exc:  # noqa: BLE001 — 补抓是增强项，失败不该连累采集
        logger.info("JD 补抓启动失败（不影响入库）：%s: %s", type(exc).__name__, exc)


def _start_analysis(db: Session, job_ids: list[int]) -> str | None:
    """对本次新增岗位启动一次批量分析（复用现有后台任务）。

    ``force=False`` 是「评一次不重复」的全部实现：服务端对已有分析记录的岗位直接跳过，
    所以这里不需要任何新的存储或状态字段。启动失败返回 None，不影响采集本身。
    """
    try:
        from ..services.job.job_match_background import (
            create_job_match_background_task,
            get_job_match_background_runner,
        )

        task = create_job_match_background_task(db, job_ids, force=False, mode="match")
        get_job_match_background_runner().start(task.task_id)
        return str(task.task_id)
    except Exception as exc:  # noqa: BLE001 — 分析是增强项，失败不该连累采集
        logger.info("采集后启动分析失败（不影响入库）：%s: %s", type(exc).__name__, exc)
        return None


def _acquire_client(db: Session):
    """取专用浏览器的 CDP 客户端（复用投递台的浏览器管理，不自建）。"""
    from ..services.apply._site_browser import get_browser_manager

    try:
        manager = get_browser_manager(db)
        return manager.client()
    except Exception as exc:  # noqa: BLE001 — 浏览器没启动/连不上 → 给可操作的提示
        logger.info("native 采集取浏览器客户端失败：%s: %s", type(exc).__name__, exc)
        raise HTTPException(
            503,
            "native 采集需要先启动专用浏览器（投递台 → 启动浏览器），稍后重试",
        ) from exc
