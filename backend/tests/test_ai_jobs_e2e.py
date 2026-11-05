# SPDX-License-Identifier: Apache-2.0
"""fake sidecar 端到端（P1-8）：预检 → 启动任务 → 待确认 → 确认投递 → tracker 写回。

全链路走 HTTP 层（TestClient）+ 进程内 fake sidecar（MockTransport），不启动
子进程、不访问任何招聘平台、不真实发送。
"""

import pytest
from app.models.tracker import ApplicationTrack
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


@pytest.fixture(autouse=True)
def _reset_busy():
    from app.services.ai_jobs.gate import set_ai_jobs_busy

    set_ai_jobs_busy(False)
    yield
    set_ai_jobs_busy(False)


@pytest.fixture()
def sidecar(client, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    patch_manager(monkeypatch, manager)
    return manager


def _seed_resume(db):
    from app.models.resume import ResumeRecord

    db.add(ResumeRecord(title="通用简历", draft=False))
    db.commit()


def test_full_flow_preflight_task_confirm_deliver(client, db_session, sidecar):
    _seed_resume(db_session)

    # 1. 预检：简历 OK；AI/浏览器/平台如实报告当前环境（fake 下 LLM/浏览器不可用）
    pre = client.post("/api/ai-jobs/preflight").json()
    by_key = {check["key"]: check for check in pre["checks"]}
    assert by_key["resume"]["ok"] is True
    assert len(pre["checks"]) == 6

    # 2. 启动任务：不确认 → 400；确认 → 快照
    assert client.post("/api/ai-jobs/tasks", json={"mode": "full", "confirm": False}).status_code == 400
    started = client.post("/api/ai-jobs/tasks", json={"mode": "full", "confirm": True})
    assert started.status_code == 200, started.text
    assert started.json()["mode"] == "full"

    # 3. 工作台状态可轮询（含当前任务）
    state = client.get("/api/ai-jobs/workbench").json()
    assert state["task"]["id"] == "task-1"

    # 4. 待确认列表可见
    confirmation = client.get("/api/ai-jobs/confirmation").json()
    assert [job["id"] for job in confirmation["pending_confirmation"]] == ["job-1"]
    assert confirmation["send_quota"]["daily_limit"] == 30

    # 5. 确认投递：白名单外的岗位 400；白名单内成功并触发 tracker 同步
    assert (
        client.post("/api/ai-jobs/deliver", json={"job_ids": ["job-999"], "confirm": True}).status_code == 400
    )
    delivered = client.post("/api/ai-jobs/deliver", json={"job_ids": ["job-1"], "confirm": True})
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["result"]["mode"] == "deliver"

    # 6. tracker 已写回（fake 引擎里 job-1 已 sent）
    rows = db_session.query(ApplicationTrack).all()
    assert len(rows) == 1
    assert rows[0].source == "ai_jobs"


def test_stop_task_via_api(client, sidecar):
    client.post("/api/ai-jobs/tasks", json={"mode": "collect", "confirm": True})
    stopped = client.post("/api/ai-jobs/tasks/task-1/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"


def test_mutual_exclusion_between_old_apply_and_ai(client, db_session, sidecar, monkeypatch):
    """旧投递台在跑时，AI 任务 409；反之亦然。"""
    monkeypatch.setattr("app.services.ai_jobs.gate.apply_busy", lambda db: True)
    response = client.post("/api/ai-jobs/tasks", json={"mode": "full", "confirm": True})
    assert response.status_code == 409
    assert "投递任务" in response.json()["detail"]
