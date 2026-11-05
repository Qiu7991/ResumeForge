# SPDX-License-Identifier: Apache-2.0
"""岗位同步/导入/去重（P2-2）：同 URL 或同 title+company 只有一条正式岗位。"""

from app.models.ai_job_link import AiJobLink
from app.services.ai_jobs.job_sync import import_engine_jobs
from app.services.job.job_service import find_job_by_identity


def _engine_job(**overrides):
    job = {
        "id": "eng-1",
        "title": "AI 应用工程师",
        "company": "示例公司",
        "status": "ready",
        "score": 82,
        "source_platform": "boss",
        "url": "https://www.zhipin.com/job_detail/abc.html?securityId=xxx",
        "jd": "岗位描述",
        "greeting": "您好",
        "reason": "匹配",
    }
    job.update(overrides)
    return job


def test_import_creates_job_and_link(db_session):
    summary = import_engine_jobs(db_session, [_engine_job()])
    assert summary.created == 1
    link = db_session.query(AiJobLink).one()
    assert link.engine_job_id == "eng-1"
    assert link.source_platform == "boss"
    assert link.score == 82
    assert link.engine_url == "https://www.zhipin.com/job_detail/abc.html"
    assert link.greeting == "您好"


def test_same_url_dedupes_across_runs_and_collectors(db_session):
    """同 URL 的岗位重复导入只产生一条 job；与旧投递台采集的岗位也去重。"""
    import_engine_jobs(db_session, [_engine_job()])
    # 同 URL（无跟踪参数）再来一次
    import_engine_jobs(db_session, [_engine_job(id="eng-2")])
    # 旧投递台形态：同 title+company，无 URL
    import_engine_jobs(db_session, [{"id": "eng-3", "title": "AI 应用工程师", "company": "示例公司", "status": "ready", "source_platform": "boss"}])
    # link 是"这张岗位当前的引擎快照"：同一张正式岗位只有一条 link（最新一次引擎行）
    links = db_session.query(AiJobLink).all()
    assert len(links) == 1
    assert links[0].engine_job_id == "eng-3"


def test_reimport_updates_snapshot_without_creating_jobs(db_session):
    import_engine_jobs(db_session, [_engine_job(status="ready", score=82)])
    import_engine_jobs(db_session, [_engine_job(status="sent", score=88, greeting="新招呼语")])
    links = db_session.query(AiJobLink).all()
    assert len(links) == 1
    assert links[0].engine_status == "sent"
    assert links[0].score == 88
    assert links[0].greeting == "新招呼语"


def test_sent_status_marks_job_applied(db_session):
    import_engine_jobs(db_session, [_engine_job(status="sent")])
    link = db_session.query(AiJobLink).one()
    job = find_job_by_identity(db_session, title="AI 应用工程师", company="示例公司")
    assert job is not None and job.status == "已投递"
    assert link.job_id == job.id


def test_filtered_jobs_stay_out_when_auto_import(db_session):
    """filtered/skipped/error 留在引擎暂存区，不进正式岗位池。"""
    summary = import_engine_jobs(db_session, [_engine_job(status="filtered")])
    assert summary.skipped_unimportable == 1
    assert db_session.query(AiJobLink).count() == 0


def test_missing_title_is_skipped(db_session):
    summary = import_engine_jobs(db_session, [{"id": "eng-x", "title": "", "company": "某公司", "status": "ready"}])
    assert summary.skipped_missing_fields == 1
