# SPDX-License-Identifier: Apache-2.0
"""自研求职路由测试：开关读写、状态、native 采集的守卫路径（浏览器侧全 mock）。"""
from __future__ import annotations

import pytest

from app.models.setting import AppSetting


@pytest.fixture()
def api(client):
    return client


def _get_config(api):
    return api.get("/api/job-hunt/config")


def test_status_lists_platforms(api):
    resp = api.get("/api/job-hunt/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "sidecar"  # 默认 sidecar（旧路径不动）
    keys = {p["key"] for p in body["platforms"]}
    assert {"zhilian", "job51", "liepin"} <= keys


def test_config_default_sidecar(api):
    resp = _get_config(api)
    assert resp.status_code == 200
    assert resp.json()["job_hunt_backend"] == "sidecar"


def test_config_switch_roundtrip(api):
    resp = api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    assert resp.status_code == 200
    assert resp.json()["job_hunt_backend"] == "native"
    assert _get_config(api).json()["job_hunt_backend"] == "native"
    # 状态跟着变
    assert api.get("/api/job-hunt/status").json()["backend"] == "native"
    # 切回 sidecar
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})
    assert _get_config(api).json()["job_hunt_backend"] == "sidecar"


def test_config_rejects_unknown_backend(api):
    resp = api.put("/api/job-hunt/config", json={"job_hunt_backend": "whatever"})
    assert resp.status_code == 422


def test_collect_rejected_in_sidecar_mode(api):
    """红线：默认 sidecar 模式下 native 采集必须拒绝（409），旧路径不受影响。"""
    resp = api.post("/api/job-hunt/collect", json={"site_key": "zhilian", "keywords": "AI"})
    assert resp.status_code == 409
    assert "sidecar" in resp.json()["detail"]


def test_collect_unknown_platform_in_native_mode(api):
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    resp = api.post("/api/job-hunt/collect", json={"site_key": "nope", "keywords": "AI"})
    assert resp.status_code == 404
    assert "nope" in resp.json()["detail"]
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})


def test_collect_reports_browser_unavailable(api, monkeypatch):
    """浏览器没启动时给 503 + 可操作提示（不发真实请求、不起真实浏览器）。

    打桩打在内层 get_browser_manager 上，让 _acquire_client 自己的 503 转换被测到。
    """
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    monkeypatch.setattr(
        "app.services.apply._site_browser.get_browser_manager",
        lambda db: (_ for _ in ()).throw(RuntimeError("no browser")),
    )
    resp = api.post("/api/job-hunt/collect", json={"site_key": "zhilian", "keywords": "AI"})
    assert resp.status_code == 503
    assert "浏览器" in resp.json()["detail"]
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})


def test_collect_cursor_saved_on_interrupt(api, db_session, monkeypatch):
    """native 采集跑通（假抓取器）：中断时游标落 KV，resume=True 续翻。"""
    from app.services.job_hunt.runner import hash_criteria

    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})

    class Stub:
        def __init__(self, payload):
            self._payload = payload

    # 直接打桩 runner：路由层行为的账目（游标保存/清理）用假报告验证
    from app.services.job_hunt.runner import HuntReport, HuntCursor
    from app.services.job_hunt.base import JobStub

    def fake_run(self, criteria, *, fetch=None, on_progress=None, cursor=None):
        report = HuntReport(
            stubs=[JobStub(title="测试岗", company="测试公司", url="https://x/1")],
            pages_fetched=1,
            stopped_reason="fetch_error",
        )
        report.next_cursor = HuntCursor(
            site_key="zhilian", criteria_hash=hash_criteria("zhilian", criteria),
            last_page=1, done_urls={"https://x/1"})
        return report

    monkeypatch.setattr("app.services.job_hunt.runner.JobHuntRunner.run", fake_run)
    monkeypatch.setattr("app.api.job_hunt._acquire_client", lambda db: Stub(None))

    resp = api.post("/api/job-hunt/collect", json={"site_key": "zhilian", "keywords": "AI"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stopped_reason"] == "fetch_error" and len(body["stubs"]) == 1
    h = hash_criteria("zhilian", {"keywords": "AI"})  # 路由把空 city/extra 归一成默认
    from app.services.job_hunt.cursor_store import kv_key
    assert db_session.get(AppSetting, kv_key("zhilian", h)) is not None  # 游标已落库
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})
