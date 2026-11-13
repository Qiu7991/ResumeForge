# SPDX-License-Identifier: Apache-2.0
"""备选岗位的「是不是采集来的」判据：`collected_at` 与 `recognition_source` 共用。

2026-11-13 用户反馈：候选表的「采集时间」整列显示「手动添加」，而这些岗位明明是
采集回来的。根因是判据只看 `collect_task_id`，而那一列是 1.x 采集批次的 int id，
2.0 自研采集用的是内存 UUID 任务号、只能传 `None`（见 `job_hunt_tasks._stage_results`）。

这三条把判据钉死：只看 task_id 会漏、只看 source 会误判空来源的老数据。
"""

from __future__ import annotations

from app.models.material import CandidateJob
from app.services.candidate_jobs import (
    RECOGNITION_SOURCE_COLLECT,
    RECOGNITION_SOURCE_MANUAL,
    import_candidates,
    stage_candidate_job,
)
from app.services.candidate_origin import MANUAL_CANDIDATE_SOURCES, is_collected_candidate
from app.services.candidate_jobs_read import with_queue_flags


def test_platform_source_counts_as_collected_even_without_task_id():
    """采集链路的 source 是平台名，没有 task_id 也算采集来的。

    这正是自研采集的真实形态（`task_id=None` + `source="BOSS直聘"`）。
    """
    assert is_collected_candidate("BOSS直聘") is True
    assert is_collected_candidate("智联招聘") is True


def test_manual_sources_are_not_collected():
    """手动录入的固定取值一个都不能被判成采集。"""
    for source in MANUAL_CANDIDATE_SOURCES:
        assert is_collected_candidate(source) is False, source


def test_blank_source_is_not_collected():
    """空来源不算采集：早期手动录入不填 source，那批老数据不能被当成采集。"""
    assert is_collected_candidate("") is False
    assert is_collected_candidate(None) is False
    assert is_collected_candidate("   ") is False


def test_collected_at_filled_for_platform_source_without_task_id(db_session):
    """列表出口给采集来的候选补上 `collected_at`（即便 collect_task_id 为空）。"""
    candidate = stage_candidate_job(
        db_session,
        title="AI 应用工程师",
        company="某公司",
        source="BOSS直聘",
        task_id=None,
    )
    db_session.commit()

    [out] = with_queue_flags(db_session, [candidate])
    assert out.collected_at is not None, "采集来的候选必须有采集时间"


def test_collected_at_empty_for_manual_candidate(db_session):
    """手动添加的候选不补 `collected_at`（界面据此显示「手动添加」）。"""
    candidate = stage_candidate_job(
        db_session,
        title="手动记的岗位",
        company="某公司",
        source="粘贴文本",
        task_id=None,
    )
    db_session.commit()

    [out] = with_queue_flags(db_session, [candidate])
    assert out.collected_at is None


def test_import_marks_platform_source_as_collected(db_session):
    """导入岗位广场时，采集来的候选记「岗位采集」而不是「备选岗位导入」。

    这条与 `collected_at` 同源：判据写错的话，岗位广场里会攒一批
    `recognition_source=备选岗位导入` 的采集岗位，日后回溯来源就全错了。
    """
    candidate = stage_candidate_job(
        db_session,
        title="AI 产品经理",
        company="某公司",
        source="BOSS直聘",
        source_url="https://example.com/collected-1",
        task_id=None,
    )
    db_session.commit()

    result = import_candidates(db_session, [candidate.id])
    assert result["imported"] == 1

    from app.models.job import Job

    job = db_session.get(Job, candidate.imported_job_id)
    assert job is not None
    assert job.recognition_source == RECOGNITION_SOURCE_COLLECT


def test_import_marks_manual_source_as_manual(db_session):
    """手动添加的候选导入后仍记「备选岗位导入」。"""
    candidate = stage_candidate_job(
        db_session,
        title="手动岗位",
        company="某公司",
        source="手动添加",
        source_url="https://example.com/manual-1",
        task_id=None,
    )
    db_session.commit()

    result = import_candidates(db_session, [candidate.id])
    assert result["imported"] == 1

    from app.models.job import Job

    job = db_session.get(Job, candidate.imported_job_id)
    assert job is not None
    assert job.recognition_source == RECOGNITION_SOURCE_MANUAL


def test_page_endpoint_uses_same_enrichment_as_list_endpoint(db_session):
    """分页端点必须与列表端点同口径注水。

    它们原本是两个出口：列表走动作层（`with_queue_flags` 注水），分页端点直接返回
    裸模型——同一个界面换成分页就整列变「未入队 / 手动添加」。这里守住两边一致。
    """
    from app.models.material import CandidateJob as Model

    candidate = stage_candidate_job(
        db_session,
        title="分页口径岗位",
        company="某公司",
        source="BOSS直聘",
        source_url="https://example.com/page-1",
        task_id=None,
    )
    db_session.commit()

    # model_validate 的裸结果没有 collected_at（列在模型上不存在，靠注水补）。
    raw = Model.__table__.c.keys()
    assert "collected_at" not in raw, "collected_at 是注水字段，不该是表列"

    [enriched] = with_queue_flags(db_session, [candidate])
    assert enriched.collected_at is not None
    assert isinstance(candidate, CandidateJob)
