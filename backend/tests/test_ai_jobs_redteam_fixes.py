# SPDX-License-Identifier: Apache-2.0
"""红队修正回归（F1/F2/F3/F4/F5）：config.yaml 固化、实例采纳、滞留自愈、终态边沿同步、投递环境闸。"""

import contextlib

import pytest  # noqa: F401 - 供 test_deliver_allowed_when_env_absent 的 skip 标记使用（blocked.md SK-1）

from app.models.tracker import ApplicationTrack
from app.services.ai_jobs import tasks
from app.services.ai_jobs.gate import ai_jobs_busy, set_ai_jobs_busy
from app.services.ai_jobs.manager import SidecarManager
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager
from tests.test_ai_jobs_manager import FAKE_SIDECAR, _engine_config

# ===== F1：runtime config.yaml 固化安全端口 =====


def test_start_writes_runtime_config_with_safe_browser_ports(tmp_path, monkeypatch):
    """启动前必须把 browser 段写进 runtime config.yaml（否则引擎回退 3456/9222）。"""
    (tmp_path / "engine_repo").mkdir()
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: [__import__("sys").executable, str(FAKE_SIDECAR), "--port", str(p)],
    )
    config = _engine_config(tmp_path, 9560)  # proxy_port=3457, browser_port=9333（默认值）
    result = manager.start(config, dataset_id="main")
    try:
        assert result.ok, result.error
        config_path = manager.runtime_dir("main") / "config.yaml"
        assert config_path.is_file()
        text = config_path.read_text(encoding="utf-8")
        assert "proxy_port: 3457" in text
        assert "chrome_ports: [9333]" in text
        assert "3456" not in text and "9222" not in text
    finally:
        manager.stop()


def test_start_failure_does_not_write_state_file(tmp_path, monkeypatch):
    """F8：健康检查失败的启动不留死状态文件（干扰下一次复用探测）。"""
    (tmp_path / "engine_repo").mkdir()
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=2, health_interval=0.1)
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: [__import__("sys").executable, "-I", "-c", "import time; time.sleep(60)"],
    )
    result = manager.start(_engine_config(tmp_path, 9570), dataset_id="main")
    assert not result.ok
    assert not (manager.runtime_dir("main") / "sidecar.json").is_file()


# ===== F2：重启后采纳存活引擎，不拉第二个实例 =====


def test_restart_adopts_running_sidecar(tmp_path, monkeypatch):
    (tmp_path / "engine_repo").mkdir()
    import sys

    first = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: [sys.executable, str(FAKE_SIDECAR), "--port", str(p)],
    )
    config = _engine_config(tmp_path, 9585)
    started = first.start(config, dataset_id="main")
    try:
        assert started.ok and started.owned
        original_pid = started.pid
        # 模拟简历通重启：全新 manager 实例（无进程句柄、同 runtime_root）
        second = SidecarManager(runtime_root=tmp_path, health_attempts=2, health_interval=0.1)
        adopted = second.start(config, dataset_id="main")
        assert adopted.ok
        assert adopted.owned is False  # 不是它启动的：不持有句柄、stop() 杀不掉
        assert adopted.pid == original_pid
        assert adopted.port == started.port
        assert second._process is None  # 未拉起新进程
        # 引擎仍是原来那个：健康、端口一致
        assert second.client_for(adopted.port).health().reachable
    finally:
        first.stop()


# ===== F3：滞留 busy 的有界自愈 =====


def test_stale_busy_self_heals_and_apply_proceeds(db_session, monkeypatch, tmp_path):
    """任务自行跑完、无人轮询：投递台启动时的有界探测应放行。"""
    from app.services.ai_jobs.gate import try_clear_stale_ai_busy
    from app.services.apply.task_runner import TaskRunner

    # busy=True（滞留），引擎侧已无活动任务（fake workbench task=None 形态）
    set_ai_jobs_busy(True)
    manager = fake_sidecar_manager(tmp_path, task={"id": "t", "status": "completed"})
    monkeypatch.setattr("app.services.ai_jobs.manager.get_sidecar_manager", lambda: manager)
    assert try_clear_stale_ai_busy() is True
    assert ai_jobs_busy() is False
    # TaskRunner.start 不再被 AI 互斥拦下（任务 1 不存在会走它自己的失败路径，与本闸无关）
    runner = TaskRunner()
    try:
        runner.start(1)
    finally:
        # 协作式停止（任务 1 不存在，线程会自行失败退出；这里确保标志复位）
        with contextlib.suppress(Exception):
            runner.stop(1)


def test_stale_busy_kept_when_engine_still_running(db_session, monkeypatch, tmp_path):
    set_ai_jobs_busy(True)
    manager = fake_sidecar_manager(tmp_path)  # task=running
    monkeypatch.setattr("app.services.ai_jobs.manager.get_sidecar_manager", lambda: manager)
    from app.services.ai_jobs.gate import try_clear_stale_ai_busy

    assert try_clear_stale_ai_busy() is False
    assert ai_jobs_busy() is True
    set_ai_jobs_busy(False)


def test_stale_busy_kept_when_engine_unreachable(monkeypatch, tmp_path):
    set_ai_jobs_busy(True)
    try:
        manager = fake_sidecar_manager(tmp_path)
        manager.read_state = lambda dataset_id=None: type("S", (), {"port": 0})()  # type: ignore[assignment]
        monkeypatch.setattr("app.services.ai_jobs.manager.get_sidecar_manager", lambda: manager)
        from app.services.ai_jobs.gate import try_clear_stale_ai_busy

        assert try_clear_stale_ai_busy() is False
        assert ai_jobs_busy() is True
    finally:
        set_ai_jobs_busy(False)


# ===== F4：终态边沿触发 tracker 同步 =====


def test_workbench_transition_syncs_tracker_once(db_session, monkeypatch, tmp_path):
    tasks._last_task_active = None
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    # 第一次观察：任务 running → 记录 active，不同步
    tasks.get_workbench_state(tasks.get_ai_jobs_config(db_session))
    assert db_session.query(ApplicationTrack).count() == 0
    # 任务转终态 → 边沿触发同步（fake 引擎里 job-1 已 sent）
    terminal = fake_sidecar_manager(tmp_path, task={"id": "t", "status": "completed"})
    patch_manager(monkeypatch, terminal)
    tasks.get_workbench_state(tasks.get_ai_jobs_config(db_session))
    rows = db_session.query(ApplicationTrack).all()
    assert len(rows) == 1
    assert rows[0].source == "ai_jobs"
    tasks._last_task_active = None


# ===== F5：投递环境闸 =====


def test_deliver_blocked_when_allow_send_explicit_zero(client, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    patch_manager(monkeypatch, manager)
    monkeypatch.setenv("AI_JOBS_ALLOW_SEND", "0")
    response = client.post("/api/ai-jobs/deliver", json={"job_ids": ["job-1"], "confirm": True})
    assert response.status_code == 403
    assert "AI_JOBS_ALLOW_SEND" in response.json()["detail"]
    monkeypatch.delenv("AI_JOBS_ALLOW_SEND")


@pytest.mark.skip(reason=(
    "2.0 语义反转（红线 4/8：发送总闸默认关）：环境变量未设置时投递必须被拒 403，"
    "而 1.x 默认放行断言 200。2.0 语义由 test_ai_jobs_send_gate.py 覆盖；"
    "依据红线 6「失败只能修实现，或 skip 并写进 blocked.md」，详见 "
    "docs/fork-2.0-ai-jobs-blocked.md SK-1。E4 未改任何断言。"
))
def test_deliver_allowed_when_env_absent(client, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    monkeypatch.delenv("AI_JOBS_ALLOW_SEND", raising=False)
    response = client.post("/api/ai-jobs/deliver", json={"job_ids": ["job-1"], "confirm": True})
    assert response.status_code == 200, response.text
