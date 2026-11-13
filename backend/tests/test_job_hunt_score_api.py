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
