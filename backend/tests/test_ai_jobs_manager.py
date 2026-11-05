# SPDX-License-Identifier: Apache-2.0
"""sidecar manager：命令拼装、端口选择、所有权（只停自己启动的）、日志。"""

import sys
import time
from pathlib import Path

import pytest
from app.schemas.ai_jobs import AiJobsConfig
from app.services.ai_jobs.manager import (
    SidecarManager,
    build_sidecar_command,
    find_free_port,
)

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_SIDECAR = FIXTURES / "fake_bosshunter.py"


def _engine_config(tmp_path: Path, port: int) -> AiJobsConfig:
    return AiJobsConfig(
        engine_python=sys.executable,
        engine_repo=str(tmp_path / "engine_repo"),
        engine_port=port,
    )


@pytest.fixture()
def engine_repo(tmp_path):
    repo = tmp_path / "engine_repo"
    repo.mkdir()
    return repo


# ===== 纯函数 =====


def test_build_sidecar_command_shape(tmp_path):
    config = _engine_config(tmp_path, 8687)
    command = build_sidecar_command(config, tmp_path / "engine", 8687)
    assert command[1:3] == ["-m", "bosshunter.main"]
    assert "--config" in command
    assert str(tmp_path / "engine" / "config.yaml") in command
    assert "web" in command and "--no-open" in command
    assert command[-1] == "8687"


def test_find_free_port_returns_bindable_port():
    port = find_free_port(9500)
    assert port is not None
    assert 9500 <= port <= 9510


# ===== 校验 =====


def test_validate_engine_reports_missing_config(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    message = manager.validate_engine(AiJobsConfig())
    assert "尚未配置引擎位置" in message


def test_validate_engine_reports_missing_paths(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    config = AiJobsConfig(engine_python=str(tmp_path / "nope.exe"), engine_repo=str(tmp_path / "nope"))
    message = manager.validate_engine(config)
    assert "不存在" in message


# ===== 启动/停止（stub 进程，真实 loopback HTTP）=====


def test_start_waits_healthy_and_stop_kills_owned_process(tmp_path, engine_repo, monkeypatch):
    port = find_free_port(9520)
    assert port is not None
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
    stub_command = [
        sys.executable,
        str(FAKE_SIDECAR),
        "--port",
        str(port),
    ]
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: stub_command,
    )
    result = manager.start(_engine_config(tmp_path, port), dataset_id="main")
    try:
        assert result.ok, result.error
        assert result.owned is True
        assert result.health is not None and result.health.version_ok
        assert result.pid is not None
        # 磁盘状态落盘（供重启后展示/复用）
        state = manager.read_state("main")
        assert state.pid == result.pid
        assert state.port == port
        assert state.owner_token
        assert state.command[0] == sys.executable
    finally:
        assert manager.stop() is True
    # 停止后进程确实退出
    time.sleep(0.2)
    assert manager.is_owned_running() is False
    assert manager.stop() is False  # 没有自己持有的进程了：幂等 False


def test_stop_never_touches_unowned_process(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    assert manager.stop() is False


def test_start_failure_terminates_spawned_process(tmp_path, engine_repo, monkeypatch):
    """健康检查不过 = 启动失败，且必须收掉刚拉起的进程（不留孤儿）。"""
    port = find_free_port(9540)
    assert port is not None
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=3, health_interval=0.1)
    sleeping = [sys.executable, "-I", "-c", "import time; time.sleep(60)"]
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: sleeping,
    )
    result = manager.start(_engine_config(tmp_path, port), dataset_id="main")
    assert not result.ok
    assert result.owned is True
    assert result.error  # 健康不过必有可读原因（超时/立即退出/版本不符）
    time.sleep(0.2)
    # 进程已被收掉：再 stop 应为 False（没有存活句柄）
    assert manager.stop() is False


def test_start_reuses_own_running_process(tmp_path, engine_repo, monkeypatch):
    port = find_free_port(9560)
    assert port is not None
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
    stub_command = [sys.executable, str(FAKE_SIDECAR), "--port", str(port)]
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: stub_command,
    )
    first = manager.start(_engine_config(tmp_path, port), dataset_id="main")
    try:
        assert first.ok, first.error
        second = manager.start(_engine_config(tmp_path, port), dataset_id="main")
        assert second.ok and second.pid == first.pid
    finally:
        manager.stop()


def test_log_tail_missing_file_returns_empty(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    assert manager.log_tail("main") == []


def test_log_tail_reads_last_lines(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    log_dir = manager.runtime_dir("main") / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "web.log").write_text("l1\nl2\nl3\n", encoding="utf-8")
    assert manager.log_tail("main", lines=2) == ["l2", "l3"]
