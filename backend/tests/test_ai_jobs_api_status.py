# SPDX-License-Identifier: Apache-2.0
"""``/api/ai-jobs`` 状态/配置/引擎启停接口契约。"""

import sys
from pathlib import Path

from app.schemas.ai_jobs import AiJobsConfig
from app.services.ai_jobs.manager import SidecarManager, find_free_port

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_SIDECAR = FIXTURES / "fake_bosshunter.py"


# ===== status / config =====


def test_status_defaults_to_not_connected(client):
    data = client.get("/api/ai-jobs/status").json()
    assert data["dataset_id"]
    assert data["engine_configured"] is False
    assert "尚未配置引擎位置" in data["engine_error"]
    assert data["sidecar"]["reachable"] is False
    assert data["owned_running"] is False


def test_config_roundtrip(client):
    payload = AiJobsConfig(engine_python="python.exe", engine_repo="D:/engines/bh").model_dump()
    saved = client.put("/api/ai-jobs/config", json=payload).json()
    assert saved["engine_repo"] == "D:/engines/bh"
    loaded = client.get("/api/ai-jobs/config").json()
    assert loaded["engine_port"] == 8687


def test_config_rejects_out_of_range_port(client):
    payload = AiJobsConfig().model_dump() | {"engine_port": 99999}
    assert client.put("/api/ai-jobs/config", json=payload).status_code == 422


# ===== engine start/stop =====


def _fresh_manager(monkeypatch, tmp_path):
    manager = SidecarManager(runtime_root=tmp_path, health_attempts=40, health_interval=0.25)
    monkeypatch.setattr("app.api.ai_jobs.get_sidecar_manager", lambda: manager)
    return manager


def test_engine_start_without_engine_config_is_422(client, monkeypatch, tmp_path):
    _fresh_manager(monkeypatch, tmp_path)
    response = client.post("/api/ai-jobs/engine/start")
    assert response.status_code == 422
    assert "尚未配置引擎位置" in response.json()["detail"]


def test_engine_start_and_stop_with_stub(client, monkeypatch, tmp_path):
    """用本地 stub 进程验证 start→owned→stop 全链（不涉及真实 BossHunter）。"""
    _fresh_manager(monkeypatch, tmp_path)
    port = find_free_port(9580)
    assert port is not None
    client.put(
        "/api/ai-jobs/config",
        json=AiJobsConfig(engine_python=sys.executable, engine_repo=str(tmp_path), engine_port=port).model_dump(),
    )
    stub_command = [sys.executable, str(FAKE_SIDECAR), "--port", str(port)]
    monkeypatch.setattr(
        "app.services.ai_jobs.manager.build_sidecar_command",
        lambda config, runtime_dir, p: stub_command,
    )
    started = client.post("/api/ai-jobs/engine/start").json()
    try:
        assert started["ok"] is True
        assert started["owned"] is True
        assert started["port"] == port
        assert started["health"]["version_ok"] is True
    finally:
        stopped = client.post("/api/ai-jobs/engine/stop").json()
    assert stopped["ok"] is True and stopped["stopped"] is True


def test_engine_stop_without_owned_process_is_idempotent(client, monkeypatch, tmp_path):
    _fresh_manager(monkeypatch, tmp_path)
    data = client.post("/api/ai-jobs/engine/stop").json()
    assert data == {"ok": True, "stopped": False}
