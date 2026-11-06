# SPDX-License-Identifier: Apache-2.0
"""五维评分 trace（P2-3）：引擎透传 + link 快照刷新。"""

import json

from app.models.ai_job_link import AiJobLink
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


def _engine_job_id(db_session):
    from app.models.job import Job

    job = Job(title="AI 应用工程师", company="示例公司")
    db_session.add(job)
    db_session.flush()
    db_session.add(AiJobLink(job_id=job.id, engine_job_id="job-1", engine_status="ready", score=82))
    db_session.commit()
    return "job-1"


def test_score_trace_proxies_engine(client, db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    engine_job_id = _engine_job_id(db_session)
    response = client.get(f"/api/ai-jobs/engine-jobs/{engine_job_id}/score-trace")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["score"] == 82
    assert "dimensions" in data


def test_score_trace_refreshes_link_snapshot(client, db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    engine_job_id = _engine_job_id(db_session)
    client.get(f"/api/ai-jobs/engine-jobs/{engine_job_id}/score-trace")
    link = db_session.query(AiJobLink).one()
    stored = json.loads(link.score_trace_json)
    assert stored["score"] == 82


def test_score_trace_without_sidecar_is_422(client, db_session, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    manager.read_state = lambda dataset_id=None: type("S", (), {"port": 0})()  # type: ignore[assignment]
    patch_manager(monkeypatch, manager)
    response = client.get("/api/ai-jobs/engine-jobs/job-1/score-trace")
    assert response.status_code == 422
