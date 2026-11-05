# SPDX-License-Identifier: Apache-2.0
"""AI 任务服务（P1-2）与互斥门（P1-6）：确认门、模式白名单、409、终态自愈。"""

import pytest
from app.services.ai_jobs import tasks
from app.services.ai_jobs.gate import ai_jobs_busy, set_ai_jobs_busy
from app.services.apply.task_runner import TaskRunner, TaskRunnerError
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


@pytest.fixture(autouse=True)
def _reset_busy():
    set_ai_jobs_busy(False)
    yield
    set_ai_jobs_busy(False)


# ===== 启动确认门 =====


def test_start_requires_confirm(db_session, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    patch_manager(monkeypatch, manager)
    with pytest.raises(tasks.TaskGateError) as excinfo:
        tasks.start_task(db_session, "full", confirm=False)
    assert excinfo.value.status_code == 400
    assert "确认" in excinfo.value.message


def test_start_rejects_unknown_mode(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    with pytest.raises(tasks.TaskGateError) as excinfo:
        tasks.start_task(db_session, "deliver", confirm=True)
    assert excinfo.value.status_code == 400
    # deliver 有专用确认门，绝不从通用任务入口走。
    assert "deliver" in excinfo.value.message


def test_start_without_sidecar_is_422(db_session, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    manager.read_state = lambda dataset_id=None: type("S", (), {"port": 0})()  # type: ignore[assignment]
    patch_manager(monkeypatch, manager)
    with pytest.raises(tasks.TaskGateError) as excinfo:
        tasks.start_task(db_session, "full", confirm=True)
    assert excinfo.value.status_code == 422


def test_start_full_sets_busy(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    snapshot = tasks.start_task(db_session, "full", confirm=True)
    assert snapshot["mode"] == "full"
    assert ai_jobs_busy() is True


def test_start_blocked_while_apply_running(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    monkeypatch.setattr(
        "app.services.ai_jobs.gate.apply_busy", lambda db: True
    )
    with pytest.raises(tasks.TaskGateError) as excinfo:
        tasks.start_task(db_session, "collect", confirm=True)
    assert excinfo.value.status_code == 409
    assert "投递任务" in excinfo.value.message


# ===== 终态自愈与停止 =====


def test_workbench_state_releases_busy_on_terminal(db_session, monkeypatch, tmp_path):
    set_ai_jobs_busy(True)
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path, task={"id": "t", "status": "completed"}))
    tasks.get_workbench_state(tasks.get_ai_jobs_config(db_session))
    assert ai_jobs_busy() is False


def test_stop_task_releases_busy(monkeypatch, tmp_path):
    set_ai_jobs_busy(True)
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    snapshot = tasks.stop_task("task-1")
    assert snapshot["status"] == "stopped"
    assert ai_jobs_busy() is False


# ===== 状态映射 =====


def test_normalize_task_status_passthrough_and_fallback():
    assert tasks.normalize_task_status("running") == "running"
    assert tasks.normalize_task_status("waiting_confirmation") == "waiting_confirmation"
    assert tasks.normalize_task_status("stopped") == "stopped"
    assert tasks.normalize_task_status("") == "running"
    assert tasks.normalize_task_status("mystery") == "running"


# ===== P1-6：旧投递台一侧 =====


def test_task_runner_start_blocked_by_ai_jobs():
    runner = TaskRunner()
    set_ai_jobs_busy(True)
    try:
        with pytest.raises(TaskRunnerError) as excinfo:
            runner.start(1)
    finally:
        set_ai_jobs_busy(False)
    assert "AI 求职" in str(excinfo.value)
    # 未启动线程：互斥检查先于租约
    assert runner.is_running() is False
