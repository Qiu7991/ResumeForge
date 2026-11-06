# SPDX-License-Identifier: Apache-2.0
"""sidecar 客户端契约：200/超时/版本窗口/非 JSON/错误归一化/GET 重试。"""

import httpx
import pytest
from app.services.ai_jobs.client import (
    SidecarClient,
    SidecarError,
    parse_version,
    version_in_window,
)


def _client(handler) -> SidecarClient:
    return SidecarClient("http://127.0.0.1:8687", transport=httpx.MockTransport(handler))


# ===== 版本窗口 =====


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2.4.0", True),
        ("2.4.7", True),
        ("v2.9.3", True),
        ("2.4", True),
        ("2.3.9", False),
        ("3.0.0", False),
        ("", False),
        ("abc", False),
    ],
)
def test_version_in_window(version, expected):
    assert version_in_window(version) is expected


def test_parse_version_handles_partial():
    assert parse_version("2.4.1") == (2, 4, 1)
    assert parse_version("v2.4") == (2, 4)
    assert parse_version("x.y") is None


# ===== health =====


def test_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Request-Id"]
        return httpx.Response(200, json={"status": "ok", "version": "2.4.1"})

    health = _client(handler).health()
    assert health.reachable and health.version_ok
    assert health.version == "2.4.1"


def test_health_unreachable_gives_not_running_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    health = _client(handler).health()
    assert not health.reachable
    assert "sidecar 未运行" in health.reason


def test_health_version_mismatch_marks_not_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "version": "3.1.0"})

    health = _client(handler).health()
    assert health.reachable and not health.version_ok
    assert "版本" in health.reason


# ===== 错误归一化 =====


def test_http_error_uses_sidecar_error_field():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "请先处理启动前检查"})

    with pytest.raises(SidecarError) as excinfo:
        _client(handler).post("/api/workbench/task", {"mode": "full"})
    assert excinfo.value.code == "http_error"
    assert "启动前检查" in str(excinfo.value)


def test_non_json_response_is_bad_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(SidecarError) as excinfo:
        _client(handler).get("/api/jobs")
    assert excinfo.value.code == "bad_response"


def test_connect_error_maps_to_not_running():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(SidecarError) as excinfo:
        _client(handler).get("/api/jobs")
    assert excinfo.value.code == "not_running"


def test_get_retries_once_on_5xx():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(200, json={"jobs": []})

    data = _client(handler).get("/api/jobs")
    assert data == {"jobs": []}
    assert len(calls) == 2


def test_post_never_retries():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"error": "busy"})

    with pytest.raises(SidecarError):
        _client(handler).post("/api/workbench/task", {"mode": "collect"})
    assert len(calls) == 1
