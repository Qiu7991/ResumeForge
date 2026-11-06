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
    report = runner.run(criteria, fetch=cdp_fetcher(client), cursor=cursor)
    if report.next_cursor is not None:
        if report.stopped_reason in ("no_results", "repeated_page"):
            # 翻到头了：游标使命完成，清掉（下次重开从头）。
            clear_cursor(db, adapter.key, report.next_cursor.criteria_hash)
        else:
            save_cursor(db, report.next_cursor)
    return {
        "stubs": [asdict(stub) for stub in report.stubs],
        "pages_fetched": report.pages_fetched,
        "duplicates": report.duplicates,
        "stopped_reason": report.stopped_reason,
        "errors": report.errors,
        "resumed_from_page": report.resumed_from_page,
    }


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
