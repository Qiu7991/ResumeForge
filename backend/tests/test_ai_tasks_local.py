"""通用 AI 任务表（0048）：登记/执行/取消/恢复，以及与岗位匹配 handler 的接线。

任务执行在线程里，测试用短轮询等待终态；未配置模型时岗位匹配走本地降级，不花模型调用。
"""

from __future__ import annotations

import time

import pytest
from app.models.ai_task import (
    AI_TASK_STATUS_CANCELED,
    AI_TASK_STATUS_FAILED,
    AI_TASK_STATUS_SUCCEEDED,
    AiTask,
)
from app.models.job import JOB_STATUS_OPEN, Job
from app.models.profile import UserProfile
from app.services.ai_task_recovery import fail_orphaned_ai_tasks
from app.services.ai_task_registry import (
    register_ai_task_handler,
    unregister_ai_task_handler,
)
from app.services.ai_task_runner import get_ai_task_runner


def _wait_task(client, task_id: int, *, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    latest: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/ai-tasks/{task_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["status"] not in ("pending", "running"):
            return latest
        time.sleep(0.05)
    pytest.fail(f"任务未在 {timeout}s 内进入终态：{latest}")


@pytest.fixture
def cleanup_kind():
    kinds: list[str] = []
    yield kinds
    for kind in kinds:
        unregister_ai_task_handler(kind)


def test_unknown_kind_is_rejected(client):
    response = client.post("/api/ai-tasks", json={"kind": "not_registered", "payload": {}})

    assert response.status_code == 400
    assert "未注册的任务类型" in response.json()["detail"]


def test_registered_handler_runs_and_returns_result_ref(client, cleanup_kind):
    def handler(ctx) -> None:  # noqa: ANN001 - 测试桩
        ctx.set_progress(50, "正在处理")
        ctx.set_result({"job_id": 7})

    register_ai_task_handler("test_ok", handler)
    cleanup_kind.append("test_ok")

    created = client.post("/api/ai-tasks", json={"kind": "test_ok", "payload": {"x": 1}})
    assert created.status_code == 201, created.text

    task = _wait_task(client, created.json()["id"])
    assert task["status"] == AI_TASK_STATUS_SUCCEEDED
    assert task["progress"] == 100
    assert task["result_ref"] == {"job_id": 7}


def test_active_list_only_returns_unfinished(client, cleanup_kind):
    def slow(ctx) -> None:  # noqa: ANN001 - 测试桩
        for _ in range(50):
            ctx.check_canceled()
            ctx.sleep(0.02)

    register_ai_task_handler("test_slow", slow)
    cleanup_kind.append("test_slow")

    created = client.post("/api/ai-tasks", json={"kind": "test_slow", "payload": {}})
    active = client.get("/api/ai-tasks/active").json()
    assert any(item["id"] == created.json()["id"] for item in active)

    canceled = client.post(f"/api/ai-tasks/{created.json()['id']}/cancel")
    assert canceled.status_code == 200
    assert _wait_task(client, created.json()["id"])["status"] == AI_TASK_STATUS_CANCELED


def test_cancel_is_idempotent_for_terminal_task(client, cleanup_kind):
    def quick(ctx) -> None:  # noqa: ANN001 - 测试桩
        ctx.set_result({})

    register_ai_task_handler("test_quick", quick)
    cleanup_kind.append("test_quick")

    created = client.post("/api/ai-tasks", json={"kind": "test_quick", "payload": {}})
    task = _wait_task(client, created.json()["id"])

    again = client.post(f"/api/ai-tasks/{task['id']}/cancel")
    assert again.status_code == 200
    assert again.json()["status"] == AI_TASK_STATUS_SUCCEEDED


def test_job_match_handler_runs_local_fallback_when_no_model_configured(client, db_session):
    db_session.add(UserProfile(name="张示例", summary="Python 后端开发"))
    job = Job(
        title="后端开发",
        company="示例公司",
        status=JOB_STATUS_OPEN,
        description="负责 Python 服务开发",
        requirements="熟悉 Python；本科及以上",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    created = client.post(
        "/api/ai-tasks",
        json={"kind": "job_match", "payload": {"job_id": job.id}, "label": "岗位匹配度分析"},
    )
    assert created.status_code == 201, created.text

    task = _wait_task(client, created.json()["id"])
    assert task["status"] == AI_TASK_STATUS_SUCCEEDED, task
    assert task["result_ref"] == {"job_id": job.id}


def test_job_match_handler_fails_for_missing_job(client):
    created = client.post(
        "/api/ai-tasks", json={"kind": "job_match", "payload": {"job_id": 999999}}
    )
    task = _wait_task(client, created.json()["id"])

    assert task["status"] == AI_TASK_STATUS_FAILED
    assert "岗位不存在" in task["error"]


def test_startup_recovery_fails_orphaned_tasks(db_session):
    row = AiTask(kind="job_match", label="孤儿任务", status="running", payload={})
    db_session.add(row)
    db_session.commit()

    recovered = fail_orphaned_ai_tasks(db_session)

    assert recovered >= 1
    db_session.refresh(row)
    assert row.status == AI_TASK_STATUS_FAILED
    assert "重启" in row.error


def test_runner_is_singleton():
    assert get_ai_task_runner() is get_ai_task_runner()
