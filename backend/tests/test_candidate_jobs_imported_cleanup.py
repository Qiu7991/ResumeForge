# SPDX-License-Identifier: Apache-2.0
"""投递台「已导入」候选的孤立判定与批量清理（批次 B / 原任务 4）。

两条不变量：

- 已导入候选关联的正式岗位被删（彻底删除或进回收站）后，两个列表出口都必须如实标出
  ``imported_job_missing``——否则用户永远看不到"这条已经没用了"。
- 批量清理只软删**候选**，正式岗位一个都不动；软删后同一个岗位必须能重新采集
  （``find_staged_candidate`` 不再命中它）。
"""

from typing import Any

from app.models.job import Job
from app.models.material import CandidateJob
from app.services import trash
from app.services.candidate_jobs import (
    find_staged_candidate,
    mark_candidate_imported,
    stage_candidate_job,
)


def _job(db, **overrides) -> Job:
    data = {"title": "后端开发", "company": "A公司", "source_url": "https://example.com/job/1"}
    data.update(overrides)
    job = Job(**data)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _stage(db, **overrides: Any) -> CandidateJob:
    data: dict[str, Any] = {
        "title": "后端开发",
        "company": "A公司",
        "source_url": "https://example.com/job/1",
        "source": "示例站点",
    }
    data.update(overrides)
    candidate = stage_candidate_job(db, **data)
    db.commit()
    db.refresh(candidate)
    return candidate


def _imported_flags(client) -> tuple[bool, bool]:
    """两个列表出口各自的 ``imported_job_missing``（顺序：旧列表、分页列表）。"""
    listed = client.get("/api/candidate-jobs", params={"status": "imported"}).json()
    page = client.get("/api/candidate-jobs/page", params={"status": "imported"}).json()
    return listed[0]["imported_job_missing"], page["items"][0]["imported_job_missing"]


def test_imported_candidate_reports_missing_job_in_both_list_endpoints(db_session, client):
    job = _job(db_session)
    candidate = _stage(db_session)
    mark_candidate_imported(db_session, candidate, job.id)

    # 正式岗位还活着：两条出口都说"在岗位广场"。
    assert _imported_flags(client) == (False, False)

    trash.soft_delete(db_session, "job", job)
    db_session.commit()

    # 岗位进回收站 = 原岗位已不在岗位广场：两处必须同时变成 True。
    assert _imported_flags(client) == (True, True)


def test_bulk_delete_soft_deletes_only_candidates_and_releases_dedupe(db_session, client):
    # 对照组：一条仍然指向存活岗位的已导入候选，清理别的记录时不许被牵连。
    live_job = _job(db_session, title="留下的岗位", source_url="https://example.com/live")
    live_candidate = _stage(
        db_session, title="留下的候选", source_url="https://example.com/live"
    )
    mark_candidate_imported(db_session, live_candidate, live_job.id)

    # 孤立记录：关联岗位已进回收站。
    gone_job = _job(db_session, title="已删岗位", source_url="https://example.com/gone")
    orphan = _stage(db_session, title="孤立候选", source_url="https://example.com/gone")
    mark_candidate_imported(db_session, orphan, gone_job.id)
    trash.soft_delete(db_session, "job", gone_job)
    db_session.commit()

    response = client.post(
        "/api/candidate-jobs/bulk-delete",
        json={"candidate_ids": [orphan.id, orphan.id, 999_999]},
    )

    assert response.status_code == 200, response.text
    # 重复 id 只算一次；不存在的 id 如实记 missing。
    assert response.json() == {"deleted": 1, "missing": 1}

    db_session.expire_all()
    assert db_session.get(Job, live_job.id).deleted_at is None, "清理暂存区不该动正式岗位"
    assert find_staged_candidate(
        db_session,
        title="孤立候选",
        company="A公司",
        source_url="https://example.com/gone",
    ) is None, "软删后同一个岗位必须能被重新采集"
    assert find_staged_candidate(
        db_session,
        title="留下的候选",
        company="A公司",
        source_url="https://example.com/live",
    ) is not None, "没被选中的候选必须留在暂存区"
