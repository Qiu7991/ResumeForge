# SPDX-License-Identifier: Apache-2.0
"""通用简历同步（P2-5）：简历中心「通用简历」导出 DOCX → 上传引擎 ``/api/resume/upload``。

**唯一源**：简历通简历中心（``job_id IS NULL`` 且非草稿），favorite 优先、更新时间倒序
取最新一份。**哈希缓存**：内容没变不重复上传（AppSetting ``ai_jobs_resume_hash``）。
DOCX 字节只在内存里流转，不落简历通磁盘。
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.resume import ResumeRecord
from ...models.setting import AppSetting
from ...schemas.ai_jobs import AiJobsConfig
from .manager import SidecarManager, get_sidecar_manager

logger = logging.getLogger(__name__)

_RESUME_HASH_KEY = "ai_jobs_resume_hash"


def get_general_resume_record(db: Session) -> ResumeRecord | None:
    """最新一份通用简历：``job_id IS NULL``、非草稿；favorite 优先、更新时间倒序。"""
    return db.scalar(
        select(ResumeRecord)
        .where(ResumeRecord.job_id.is_(None), ResumeRecord.draft.is_(False))
        .order_by(ResumeRecord.favorite.desc(), ResumeRecord.updated_at.desc())
        .limit(1)
    )


def export_general_resume_docx(db: Session, record: ResumeRecord) -> bytes:
    """把通用简历导出成 DOCX 字节（与简历中心导出同一管线）。"""
    from ...services.export_pipeline import ExportRequest, RenderContext, build_export
    from ...services.resume.document_io import document_for_record
    from ...services.resume.resume_delivery import default_render_context

    document, _report = document_for_record(db, record)
    context = RenderContext(**default_render_context(db, record))
    artifact = build_export(ExportRequest(format="docx"), document, context)
    return artifact.content


def _read_cached_hash(db: Session) -> str:
    row = db.get(AppSetting, _RESUME_HASH_KEY)
    if row is None:
        return ""
    try:
        return str(json.loads(row.value))
    except (json.JSONDecodeError, TypeError):
        return ""


def _write_cached_hash(db: Session, digest: str) -> None:
    row = db.get(AppSetting, _RESUME_HASH_KEY)
    serialized = json.dumps(digest)
    if row is None:
        db.add(AppSetting(key=_RESUME_HASH_KEY, value=serialized))
    else:
        row.value = serialized
    db.commit()


def sync_resume_to_engine(
    db: Session,
    config: AiJobsConfig | None = None,
    manager: SidecarManager | None = None,
    *,
    force: bool = False,
) -> dict:
    """把最新通用简历上传给引擎。返回 ``{uploaded, reason}``；失败不抛（可重试）。"""
    mgr = manager or get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        return {"uploaded": False, "reason": "sidecar 未运行"}
    record = get_general_resume_record(db)
    if record is None:
        return {"uploaded": False, "reason": "简历中心里没有通用简历"}
    try:
        content = export_general_resume_docx(db, record)
    except Exception as exc:  # noqa: BLE001 - 导出失败如实上报
        logger.warning("通用简历导出失败：%s", exc)
        return {"uploaded": False, "reason": f"简历导出失败：{exc}"}
    # DOCX 是 zip：时间戳让同一份内容每次导出字节都不同，**不能**按产物字节做缓存键。
    # 语义键：记录标识 + 更新时间 + 正文与版式字段——这些变了才需要重新上传。
    semantic = json.dumps(
        {
            "id": record.id,
            "updated_at": str(record.updated_at),
            "content": record.content,
            "template": record.template,
            "layout": record.format_config if hasattr(record, "format_config") else None,
            "language": record.language,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(semantic.encode("utf-8")).hexdigest()
    if not force and digest == _read_cached_hash(db):
        return {"uploaded": False, "reason": "简历未变化"}
    filename = f"resume-{record.id}.docx"
    try:
        mgr.client_for(port).post_multipart(
            "/api/resume/upload",
            {"file": (filename, content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    except Exception as exc:  # noqa: BLE001 - 上传失败可重试
        logger.info("简历上传引擎失败：%s", exc)
        return {"uploaded": False, "reason": f"上传失败：{exc}"}
    _write_cached_hash(db, digest)
    logger.info("通用简历已同步给引擎 record=%s bytes=%s", record.id, len(content))
    return {"uploaded": True, "reason": "", "filename": filename}


__all__ = [
    "export_general_resume_docx",
    "get_general_resume_record",
    "sync_resume_to_engine",
]
