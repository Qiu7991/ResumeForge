# SPDX-License-Identifier: Apache-2.0
"""语义评分路由测试：无 JD 拒绝、缓存、落库到 semantic_score 子键。

模型调用全部打桩，不发真实请求。
"""

from __future__ import annotations

import json

from app.models.job import JOB_STATUS_OPEN, Job


def _job(db_session, **kw):
    defaults = dict(
        title="AI 工程师",
        company="测试公司",
        location="广州",
        salary="15-25K",
        description="负责 AI 应用开发，要求熟悉 Python。",
        source_url="https://example.com/j1",
        status=JOB_STATUS_OPEN,
    )
    defaults.update(kw)
    job = Job(**defaults)
    db_session.add(job)
    db_session.commit()
    return job


_MODEL_JSON = json.dumps(
    {
        "role_summary": "AI 应用开发",
        "core_duties": {"evidence": "做过 AIGC", "score": 32},
        "transferable_evidence": {"evidence": "有迁移", "score": 18},
        "hard_requirements": {"evidence": "满足", "score": 15},
        "tools_industry": {"evidence": "Python", "score": 8},
        "practical_fit": {"evidence": "广州", "score": 10},
        "caps": [],
        "hard_gaps": [],
        "reason": "匹配",
        "missing": "",
    },
    ensure_ascii=False,
)


def test_rejects_job_without_jd(client, db_session):
    job = _job(db_session, description="")
    resp = client.post(f"/api/job-hunt/jobs/{job.id}/score")
    assert resp.status_code == 409
    assert "JD" in resp.json()["detail"]


def test_rejects_unknown_job(client):
    resp = client.post("/api/job-hunt/jobs/999999/score")
    assert resp.status_code == 404


def test_get_score_returns_not_scored(client, db_session):
    job = _job(db_session)
    resp = client.get(f"/api/job-hunt/jobs/{job.id}/score")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_score_job_persists_and_hits_cache(client, db_session, monkeypatch):
    calls = {"count": 0}

    async def _fake_call(prompt):
        from app.services.job_hunt.scoring import parse_semantic_score

        calls["count"] += 1
        return parse_semantic_score(_MODEL_JSON), "fake-score-model"

    monkeypatch.setattr(
        "app.services.job_hunt.scoring_service.resolve_resume_text",
        lambda db, resume_id=None: (
            None,
            "熟悉 Python 与 AIGC 应用开发",
            "AI 应用工程师简历正文",
        ),
    )
    monkeypatch.setattr(
        "app.services.job_hunt.scoring_service.call_scoring_model",
        _fake_call,
    )

    job = _job(db_session)
    url = f"/api/job-hunt/jobs/{job.id}/score"

    first = client.post(url)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["cached"] is False
    assert first_body["total"] == 83
    assert calls["count"] == 1

    stored = client.get(url)
    assert stored.status_code == 200, stored.text
    assert stored.json()["total"] == 83

    second = client.post(url)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["cached"] is True
    assert second_body["total"] == 83
    assert calls["count"] == 1

    forced = client.post(f"{url}?force=true")
    assert forced.status_code == 200, forced.text
    forced_body = forced.json()
    assert forced_body["cached"] is False
    assert forced_body["total"] == 83
    assert calls["count"] == 2
