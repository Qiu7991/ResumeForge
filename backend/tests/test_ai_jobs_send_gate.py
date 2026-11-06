# SPDX-License-Identifier: Apache-2.0
"""发送总闸 2.0 语义（默认关，红线 4/8）：未设置/非真值 → 一律拒；显式真值 → 放行。

1.x 的 ``test_deliver_allowed_when_env_absent`` 断言「未设置 → 200」（默认放行），
与 2.0 红线直接冲突，已 skip（blocked.md SK-1）；本文件是 2.0 语义的常驻正向
覆盖（对应对抗审查 F2 的测试化形态）。
"""

from __future__ import annotations

import pytest

from app.services.ai_jobs.delivery import send_gate_open


def test_gate_default_closed(monkeypatch):
    monkeypatch.delenv("AI_JOBS_ALLOW_SEND", raising=False)
    assert send_gate_open() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_gate_explicit_truthy_opens(monkeypatch, value):
    monkeypatch.setenv("AI_JOBS_ALLOW_SEND", value)
    assert send_gate_open() is True


@pytest.mark.parametrize("value", ["0", "", "false", "no", "random"])
def test_gate_non_truthy_stays_closed(monkeypatch, value):
    monkeypatch.setenv("AI_JOBS_ALLOW_SEND", value)
    assert send_gate_open() is False


def test_api_deliver_rejected_when_gate_closed(client, monkeypatch, tmp_path):
    """F2：未设置 AI_JOBS_ALLOW_SEND 时，POST /api/ai-jobs/deliver 必须 403 并说明原因。"""
    from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager

    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    monkeypatch.delenv("AI_JOBS_ALLOW_SEND", raising=False)
    response = client.post("/api/ai-jobs/deliver", json={"job_ids": ["job-1"], "confirm": True})
    assert response.status_code == 403
    assert "AI_JOBS_ALLOW_SEND" in response.json()["detail"]


def test_api_deliver_allowed_when_gate_explicitly_opened(client, monkeypatch, tmp_path):
    """显式打开后走通全链路（fake 引擎）：1.x 默认放行测试的 2.0 语义对应版。"""
    from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager

    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    monkeypatch.setenv("AI_JOBS_ALLOW_SEND", "1")
    response = client.post("/api/ai-jobs/deliver", json={"job_ids": ["job-1"], "confirm": True})
    assert response.status_code == 200, response.text
