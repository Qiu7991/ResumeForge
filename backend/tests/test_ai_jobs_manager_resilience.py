# SPDX-License-Identifier: Apache-2.0
"""manager 生命周期韧性（P3-5）：端口占用后移、崩溃后可重启、日志截断。"""

import socket
import sys
import time

from app.services.ai_jobs.manager import SidecarManager, find_free_port
from tests.test_ai_jobs_manager import FAKE_SIDECAR, _engine_config


def test_find_free_port_skips_occupied():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 9570))
        sock.listen(1)
        port = find_free_port(9570)
        assert port is not None
        assert port > 9570


def test_start_falls_back_when_configured_port_occupied(tmp_path, monkeypatch):
    """配置端口被占：自动后移到下一个空闲端口并在那里启动。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 9580))
        sock.listen(1)
        occupied = 9580
        (tmp_path / "engine_repo").mkdir()
        manager = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
        # 端口选择发生在 start 内部：stub 会收到实际选中的端口并绑定它
        monkeypatch.setattr(
            "app.services.ai_jobs.manager.build_sidecar_command",
            lambda config, runtime_dir, p: [sys.executable, str(FAKE_SIDECAR), "--port", str(p)],
        )
        result = manager.start(_engine_config(tmp_path, occupied), dataset_id="main")
        try:
            assert result.ok, result.error
            assert result.port > occupied
        finally:
            manager.stop()


def test_restart_after_owned_process_crash(tmp_path, monkeypatch):
    """自己拉起的进程崩了之后，可以再次 start（端口句柄已清理）。"""
    (tmp_path / "engine_repo").mkdir()
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: [sys.executable, str(FAKE_SIDECAR), "--port", str(p)],
    )
    config = _engine_config(tmp_path, 9590)
    first = manager.start(config, dataset_id="main")
    assert first.ok, first.error
    # 模拟崩溃：直接杀掉自己持有的进程
    manager._process.terminate()
    manager._process.wait(timeout=5)
    time.sleep(0.2)
    assert manager.is_owned_running() is False
    second = manager.start(config, dataset_id="main")
    try:
        assert second.ok, second.error
        assert second.pid != first.pid
    finally:
        manager.stop()


def test_log_tail_truncates_large_files(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    log_dir = manager.runtime_dir("main") / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "web.log").write_text("\n".join(f"line-{i}" for i in range(100)), encoding="utf-8")
    tail = manager.log_tail("main", lines=10)
    assert len(tail) == 10
    assert tail[0] == "line-90"
    assert tail[-1] == "line-99"
