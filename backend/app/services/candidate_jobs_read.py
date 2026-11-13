# SPDX-License-Identifier: Apache-2.0
"""备选岗位的只读查询（批量按 id 取存活候选 + 列表出口注水）。

从 api/candidate_jobs.py 搬来：services/candidate_jobs.py 已贴着 500 行预算，而
"按 id 批量取候选 + 只认未删除"是导出/批量操作共用的存在性校验。为什么放服务层：
这套取数口径属于备选岗位域，路由只该把缺失 id 映射成 404。

``with_queue_flags``（二开 2026-11-10，随 action 机制迁移到这里）：给候选列表补
「是否已在投递队列」与「采集时间」。路由侧（action）与工具侧共用。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.material import CandidateJob
from ..schemas.material import CandidateJobOut
from .apply._queue import queued_job_ids
from .trash import live_only


def candidates_by_ids(
    db: Session, candidate_ids: list[int]
) -> tuple[list[CandidateJob], list[int]]:
    """按给定 id 顺序返回存活候选与缺失 id（回收站里的算"不存在"）。

    缺失 id 交给调用方映射成 404：错误形状是接口层契约，不归服务层管。
    """
    if not candidate_ids:
        return [], []
    rows = (
        db.query(CandidateJob)
        .filter(CandidateJob.id.in_(candidate_ids), live_only(CandidateJob))
        .all()
    )
    by_id = {candidate.id: candidate for candidate in rows}
    ordered = [by_id[candidate_id] for candidate_id in candidate_ids if candidate_id in by_id]
    missing = [candidate_id for candidate_id in candidate_ids if candidate_id not in by_id]
    return ordered, missing


def with_queue_flags(db: Session, rows: list[CandidateJob]) -> list[CandidateJobOut]:
    """给一批候选补上「是否已在投递队列」与「采集时间」（2026-11-10）。

    **一次查询算完全部**（``queued_job_ids`` 走 ``WHERE job_id IN (...)``），不逐条查：
    采集结果一次上百条，逐条查会让打开这一块随条数线性变慢。

    两个字段都只增不改：``status`` / ``imported_job_id`` 的语义原样保留——前端已有代码
    依赖它们，这里只是多给两条**它本来要自己算**的信息。
    """
    queued = queued_job_ids(db, [row.imported_job_id for row in rows])
    out: list[CandidateJobOut] = []
    for row in rows:
        item = CandidateJobOut.model_validate(row)
        out.append(
            item.model_copy(
                update={
                    "in_apply_queue": bool(
                        row.imported_job_id and int(row.imported_job_id) in queued
                    ),
                    # 采集来的候选才有「采集时间」；手动粘贴的留空（界面显示为"手动添加"）。
                    "collected_at": row.created_at if row.collect_task_id else None,
                }
            )
        )
    return out


__all__ = ["candidates_by_ids", "with_queue_flags"]
