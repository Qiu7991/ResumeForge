# SPDX-License-Identifier: Apache-2.0
"""引擎岗位同步/导入（P2-2）：BossHunter 岗位 → 简历通 `job` 表 + ``ai_job_link``。

**去重口径**（与旧投递台一致）：同 ``source_url`` 或同 title+company 只有一张正式
岗位——先 ``find_job_by_identity``，命中就复用，不命中才 ``create_job_record``。
引擎侧快照（状态/评分/招呼语）只挂 link，不写进 `job` 表。

**状态映射**（§5.1）：引擎完成态（sent/replied/...）→ ``job.status=已投递``；
拒绝/跳过/过滤不改简历通岗位状态，只更新 ``link.engine_status``。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ...models.ai_job_link import AiJobLink
from ...models.job import JOB_STATUS_APPLIED, JOB_STATUS_OPEN
from ...schemas.job import JobCreate
from ..job.job_service import create_job_record, find_job_by_identity
from .manager import SidecarManager, get_sidecar_manager

logger = logging.getLogger(__name__)

# 引擎侧"已发生投递动作"的状态 → 简历通「已投递」。
_ENGINE_DELIVERED = {"sent", "replied", "resume_sent", "needs_resume", "follow_up_sent"}
# 只读平台（不支持发送），导入时保留标记给前端展示。
READ_ONLY_PLATFORMS = {"zhilian", "51job", "liepin"}

# 引擎库只是暂存区：filtered/skipped/error 留在引擎侧，不进正式岗位池。
_IMPORTABLE_STATUSES = {"ready", "approved"} | _ENGINE_DELIVERED


@dataclass
class SyncSummary:
    created: int = 0
    linked_existing: int = 0
    updated: int = 0
    skipped_unimportable: int = 0
    skipped_missing_fields: int = 0
    engine_job_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "linked_existing": self.linked_existing,
            "updated": self.updated,
            "skipped_unimportable": self.skipped_unimportable,
            "skipped_missing_fields": self.skipped_missing_fields,
            "engine_job_ids": self.engine_job_ids,
        }


def _engine_url_for_identity(job: dict[str, Any]) -> str:
    url = str(job.get("url") or "").strip()
    # BOSS 详情页的跟踪查询串不是岗位身份的一部分（与 job_import 同口径）。
    if "zhipin.com" in url and "?" in url:
        url = url.split("?", 1)[0]
    return url[:512]


def _status_for_job(engine_status: str) -> str:
    return JOB_STATUS_APPLIED if engine_status in _ENGINE_DELIVERED else JOB_STATUS_OPEN


def upsert_link(
    db: Session,
    job_id: int,
    engine_job: dict[str, Any],
) -> AiJobLink:
    """建立或更新一条 link（幂等）。

    link 的语义是"这张正式岗位**当前**的引擎快照"：先按 ``engine_job_id`` 找；
    找不到再按 ``job_id`` 找（同岗位换了一次引擎行——重新采集出的新 id——就地把
    快照换新，而不是另建一条违反 job_id 唯一约束的行）。
    """
    engine_job_id = str(engine_job.get("id") or "")
    score = engine_job.get("score")
    link = db.query(AiJobLink).filter(AiJobLink.engine_job_id == engine_job_id).one_or_none()
    if link is None:
        link = (
            db.query(AiJobLink).filter(AiJobLink.job_id == job_id).one_or_none()
        )
    if link is None:
        link = AiJobLink(job_id=job_id, engine_job_id=engine_job_id)
        db.add(link)
    link.job_id = job_id
    link.engine_job_id = engine_job_id
    link.source_platform = str(engine_job.get("source_platform") or "boss")
    link.engine_status = str(engine_job.get("status") or "")
    link.score = int(score) if isinstance(score, (int, float)) else None
    trace = engine_job.get("score_trace") or engine_job.get("trace")
    link.score_trace_json = json.dumps(trace, ensure_ascii=False) if trace else ""
    link.score_reason = str(engine_job.get("reason") or engine_job.get("score_reason") or "")
    link.greeting = str(engine_job.get("greeting") or "")
    link.engine_url = _engine_url_for_identity(engine_job)[:2048]
    link.last_synced_at = datetime.now()
    return link


def import_engine_jobs(db: Session, jobs: list[dict[str, Any]], *, auto_import: bool = True) -> SyncSummary:
    """把引擎岗位导入正式岗位池并维护 link。``auto_import=False`` 时只导入 ready 及以上。"""
    summary = SyncSummary()
    for engine_job in jobs:
        if not isinstance(engine_job, dict):
            continue
        engine_job_id = str(engine_job.get("id") or "").strip()
        title = str(engine_job.get("title") or "").strip()
        company = str(engine_job.get("company") or "").strip()
        status = str(engine_job.get("status") or "")
        if not engine_job_id or not title:
            summary.skipped_missing_fields += 1
            continue
        if auto_import and status not in _IMPORTABLE_STATUSES:
            summary.skipped_unimportable += 1
            continue
        source_url = _engine_url_for_identity(engine_job)
        existing = find_job_by_identity(db, title=title, company=company, source_url=source_url)
        if existing is None:
            job = create_job_record(
                db,
                JobCreate(
                    title=title[:128],
                    company=company[:128],
                    description=str(engine_job.get("jd") or "")[:20000],
                    source_url=source_url,
                    status=_status_for_job(status),
                    source="AI 求职",
                    origin_source="BossHunter 引擎",
                ),
                source="AI 求职",
            )
            summary.created += 1
        else:
            job = existing
            summary.linked_existing += 1
            if status in _ENGINE_DELIVERED and job.status != JOB_STATUS_APPLIED:
                job.status = JOB_STATUS_APPLIED
        upsert_link(db, job.id, engine_job)
        summary.engine_job_ids.append(engine_job_id)
        summary.updated += 1
    db.commit()
    logger.info(
        "引擎岗位导入完成 created=%s linked=%s skipped=%s",
        summary.created,
        summary.linked_existing,
        summary.skipped_unimportable,
    )
    return summary


def sync_engine_jobs(
    db: Session,
    manager: SidecarManager | None = None,
    *,
    limit: int = 500,
) -> SyncSummary:
    """拉取引擎岗位并导入（全量同步入口）。sidecar 未运行时返回空 summary。"""
    mgr = manager or get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        return SyncSummary()
    try:
        data = mgr.client_for(port).get("/api/jobs", params={"deleted": "active", "limit": limit})
    except Exception as exc:  # noqa: BLE001 - 拉取失败如实返回空
        logger.info("引擎岗位拉取失败：%s", exc)
        return SyncSummary()
    return import_engine_jobs(db, (data or {}).get("jobs") or [])


__all__ = [
    "READ_ONLY_PLATFORMS",
    "SyncSummary",
    "import_engine_jobs",
    "sync_engine_jobs",
    "upsert_link",
]
