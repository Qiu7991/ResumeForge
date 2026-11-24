# SPDX-License-Identifier: Apache-2.0
"""自研求职采集与评分的数据库查询封装（由 API 路由下沉）。

遵循 ``docs/architecture.md``「路由层允许与禁止」：路由层不做 ``db.query`` /
``db.execute`` 构造，全部查询收口在本模块。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...models.job import Job
from ...models.material import CANDIDATE_JOB_PENDING, CandidateJob

BLOCKLIST_KEY = "job_hunt_blocklist"


def read_blocklist_raw(db: Session) -> str | None:
    """读取黑名单原始 JSON 串；不存在返回 None。"""
    return db.execute(
        text("SELECT value FROM app_setting WHERE key = :key"),
        {"key": BLOCKLIST_KEY},
    ).scalar_one_or_none()


def write_blocklist_raw(db: Session, payload: str) -> None:
    """写入黑名单原始 JSON 串（upsert，不含 commit）。"""
    db.execute(
        text(
            "INSERT INTO app_setting (key, value) VALUES (:key, :value) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        ),
        {"key": BLOCKLIST_KEY, "value": payload},
    )


def list_unscored_pending_candidate_ids(db: Session, *, limit: int = 2000) -> list[int]:
    """按 id 升序列出待处理且尚未评分的备选岗位 id。"""
    rows = (
        db.query(CandidateJob)
        .filter(
            CandidateJob.status == CANDIDATE_JOB_PENDING,
            CandidateJob.deleted_at.is_(None),
            CandidateJob.score_total.is_(None),
        )
        .order_by(CandidateJob.id)
        .limit(limit)
        .all()
    )
    return [row.id for row in rows]


def find_scored_candidate_ids(db: Session, ids: list[int]) -> set[int]:
    """返回 ``ids`` 中已经有评分的备选岗位 id 集合。"""
    if not ids:
        return set()
    rows = (
        db.query(CandidateJob)
        .filter(CandidateJob.id.in_(ids), CandidateJob.score_total.isnot(None))
        .all()
    )
    return {row.id for row in rows}


def list_candidates_by_ids(db: Session, ids: list[int]) -> list[CandidateJob]:
    """按 id 列表批量取备选岗位行。"""
    if not ids:
        return []
    return db.query(CandidateJob).filter(CandidateJob.id.in_(ids)).all()


def find_jobs_for_refetch(
    db: Session,
    *,
    job_ids: list[int],
    short_threshold: int,
) -> list[Job]:
    """查出需要重抓 JD 的候选岗位。"""
    if job_ids:
        return db.query(Job).filter(Job.id.in_(job_ids)).all()
    return [
        job
        for job in db.query(Job).filter(Job.deleted_at.is_(None)).all()
        if (job.source_url or "").strip() and len((job.description or "").strip()) < short_threshold
    ]


__all__ = [
    "BLOCKLIST_KEY",
    "find_jobs_for_refetch",
    "find_scored_candidate_ids",
    "list_candidates_by_ids",
    "list_unscored_pending_candidate_ids",
    "read_blocklist_raw",
    "write_blocklist_raw",
]
