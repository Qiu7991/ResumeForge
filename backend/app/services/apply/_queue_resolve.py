# SPDX-License-Identifier: Apache-2.0
"""投递队列的批量预取与简历 / 招呼语解析助手（由 ``_queue.py`` 按 500 行预算拆出）。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from ...models.apply import ApplyQueueItem, ApplyTaskItem, JobMatchAnalysis
from ...models.job import Job
from ...models.resume import ResumeRecord, saved_only
from ...schemas.apply import ApplyConfigIn
from .. import trash
from ..profile.profile_service import project_legacy_profile
from ._config import get_apply_config


def _resume_titles(db: Session, resume_ids: Sequence[int | None]) -> dict[int, str]:
    """按 id **批量**取简历标题（一次查询覆盖整页），缺失（已删）的不在返回里。

    与单条 ``db.get`` 口径一致，刻意不过软删过滤。
    """
    ids = sorted({int(resume_id) for resume_id in resume_ids if resume_id})
    if not ids:
        return {}
    rows = db.query(ResumeRecord).filter(ResumeRecord.id.in_(ids)).all()
    return {row.id: row.title for row in rows}


def _matches_by_job_id(db: Session, job_ids: Sequence[int | None]) -> dict[int, JobMatchAnalysis]:
    """按岗位批量取最近一次匹配结论（一次查询覆盖整页），等价于逐条 :func:`latest_match`。"""
    ids = sorted({int(job_id) for job_id in job_ids if job_id})
    if not ids:
        return {}
    rows = db.query(JobMatchAnalysis).filter(JobMatchAnalysis.job_id.in_(ids)).all()
    return {int(row.job_id): row for row in rows if row.job_id is not None}


def _jobs_by_id(db: Session, job_ids: Sequence[int | None]) -> dict[int, Job]:
    """按 id 批量取岗位；缺失（已删除）的不在返回里。"""
    ids = sorted({job_id for job_id in job_ids if job_id})
    if not ids:
        return {}
    return {job.id: job for job in db.query(Job).filter(Job.id.in_(ids)).all()}


def _last_apply_results(db: Session, job_ids: Sequence[int | None]) -> dict[int, ApplyTaskItem]:
    """每个岗位**最近一次**投递记录（一次查询，避免逐行 N+1）。

    按 `finished_at` 倒序取，同岗位只留第一条。`finished_at` 为空（还没跑完）的跳过。
    """
    ids = sorted({job_id for job_id in job_ids if job_id})
    if not ids:
        return {}
    rows = (
        db.query(ApplyTaskItem)
        .filter(
            ApplyTaskItem.job_id.in_(ids),
            ApplyTaskItem.deleted_at.is_(None),
            ApplyTaskItem.finished_at.isnot(None),
        )
        .order_by(ApplyTaskItem.finished_at.desc(), ApplyTaskItem.id.desc())
        .all()
    )
    latest: dict[int, ApplyTaskItem] = {}
    for row in rows:
        if row.job_id is None or row.job_id in latest:
            continue
        latest[row.job_id] = row
    return latest


def _job_specific_resume(db: Session, job_id: int | None) -> ResumeRecord | None:
    """该岗位最近一份岗位版简历（不含"默认简历"回落）。"""
    if job_id is None:
        return None
    return (
        db.query(ResumeRecord)
        # 只挑**已保存**的简历：草稿里的内容用户还没认可，拿去投递是不可接受的（0051）。
        .filter(trash.live_only(ResumeRecord), saved_only(), ResumeRecord.job_id == job_id)
        .order_by(ResumeRecord.created_at.desc(), ResumeRecord.id.desc())
        .first()
    )


def resolve_resume(db: Session, job_id: int | None, resume_id: int | None) -> ResumeRecord | None:
    """确定本岗位用哪份简历：显式指定 → 该岗位最近一份岗位版 → 设置里的默认简历。

    「默认简历」在投递设置里随时可改，已经入队的条目也跟着走（解析在运行时做，
    不把默认值固化进队列）。
    """
    if resume_id is not None:
        return db.get(ResumeRecord, resume_id)
    specific = _job_specific_resume(db, job_id)
    if specific is not None:
        return specific
    default_id = get_apply_config(db).default_resume_id
    if default_id is None:
        return None
    return (
        db.query(ResumeRecord)
        .filter(
            trash.live_only(ResumeRecord),
            saved_only(),
            ResumeRecord.id == default_id,
        )
        .first()
    )


def resolve_greeting(item: ApplyQueueItem | None, config: ApplyConfigIn) -> str:
    """本岗位招呼语：条目值优先，为空则退回默认招呼语。"""
    if item is not None and item.greeting.strip():
        return item.greeting.strip()
    return config.default_greeting.strip()


def build_apply_data(db: Session, resume: ResumeRecord | None) -> dict[str, Any]:
    """构造供通用表单引擎映射的字段数据（只取投递必需的展示字段，不含完整资料）。"""
    profile = project_legacy_profile(db)
    data: dict[str, Any] = {
        "name": profile.name,
        "phone": profile.phone,
        "email": profile.email,
        "city": profile.target_city or profile.city,
        "job_intent": profile.job_intent,
        "summary": profile.summary,
    }
    if resume is not None and resume.title:
        data["job_intent"] = data.get("job_intent") or resume.job_title
    return {key: value for key, value in data.items() if value}


def queued_job_ids(db: Session, job_ids: Sequence[int | None]) -> set[int]:
    """这批岗位里**哪些已经在投递队列里**（2026-11-10）。

    一次 ``WHERE job_id IN (...)`` 查完；``None`` 与假值一律忽略。
    """
    wanted = {int(job_id) for job_id in job_ids if job_id}
    if not wanted:
        return set()
    rows = db.query(ApplyQueueItem.job_id).filter(ApplyQueueItem.job_id.in_(wanted)).all()
    return {int(job_id) for (job_id,) in rows if job_id is not None}
