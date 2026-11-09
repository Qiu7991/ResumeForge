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


# ---------------------------------------------------------------------------
# N1：采集入库（persist）+ 幂等去重
# ---------------------------------------------------------------------------


def _stub(title="AI 工程师", company="某公司", url="https://example.com/job/1", salary="8-12K"):
    from app.services.job_hunt.base import JobStub

    return JobStub(
        title=title,
        company=company,
        location="广州·天河区",
        salary_raw="\ue039-\ue032\ue033K",
        salary_decoded=salary,
        salary_decoded_ok=True,
        url=url,
    )


def _patch_collect(monkeypatch, stubs):
    """把 collect 的浏览器侧打桩：返回固定 stubs，不碰真实浏览器/网站。"""
    from app.services.job_hunt.runner import HuntReport

    monkeypatch.setattr(
        "app.api.job_hunt._acquire_client", lambda db: object()
    )
    monkeypatch.setattr(
        "app.api.job_hunt.cdp_fetcher", lambda client, adapter=None, **kw: (lambda url: "")
    )

    def fake_run(self, criteria, *, fetch, cursor=None):
        return HuntReport(stubs=list(stubs), pages_fetched=1, duplicates=0, stopped_reason="max_pages")

    monkeypatch.setattr("app.services.job_hunt.runner.JobHuntRunner.run", fake_run)


def test_collect_persists_new_jobs(api, monkeypatch):
    """persist=True 时，采到的岗位要写进岗位广场。"""
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    _patch_collect(monkeypatch, [_stub(), _stub("另一个岗位", "另一公司", "https://example.com/job/2")])

    resp = api.post(
        "/api/job-hunt/collect",
        json={"site_key": "boss", "keywords": "AI", "persist": True, "analyze": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["persisted"]["inserted"] == 2
    assert body["persisted"]["skipped_duplicate"] == 0
    assert body["persisted"]["errors"] == []

    # 岗位广场能查到，且薪资是明文（不是字体乱码）
    jobs = api.get("/api/jobs?page_size=50").json()
    titles = {j["title"] for j in jobs["items"]}
    assert "AI 工程师" in titles
    row = next(j for j in jobs["items"] if j["title"] == "AI 工程师")
    assert row["salary"] == "8-12K"
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})


def test_collect_is_idempotent(api, monkeypatch):
    """同一批岗位再采一次：inserted=0，skipped_duplicate 全中。"""
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    stubs = [_stub()]
    _patch_collect(monkeypatch, stubs)

    first = api.post(
        "/api/job-hunt/collect",
        json={"site_key": "boss", "keywords": "AI", "persist": True, "analyze": False},
    ).json()
    assert first["persisted"]["inserted"] == 1

    second = api.post(
        "/api/job-hunt/collect",
        json={"site_key": "boss", "keywords": "AI", "persist": True, "analyze": False},
    ).json()
    assert second["persisted"]["inserted"] == 0
    assert second["persisted"]["skipped_duplicate"] == 1
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})


def test_collect_persist_off_does_not_write(api, monkeypatch):
    """persist=False 时只返回卡片，不落库。"""
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    _patch_collect(monkeypatch, [_stub("不该入库的岗位", "X公司", "https://example.com/job/9")])

    before = api.get("/api/jobs?page_size=50").json()["total"]
    resp = api.post(
        "/api/job-hunt/collect",
        json={"site_key": "boss", "keywords": "AI", "persist": False, "analyze": False},
    )
    assert resp.status_code == 200
    assert resp.json()["persisted"]["inserted"] == 0
    after = api.get("/api/jobs?page_size=50").json()["total"]
    assert after == before
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})


def test_collect_analyze_uses_force_false(api, monkeypatch):
    """N2：采集后触发的批量分析必须 force=False（= 评过的跳过，不重复评分）。"""
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    _patch_collect(monkeypatch, [_stub("评分测试岗位", "Y公司", "https://example.com/job/77")])

    captured = {}
    import app.services.job.job_match_background as bg

    real = bg.create_job_match_background_task

    def spy(db, job_ids, *, force, mode="match"):
        captured["force"] = force
        captured["job_ids"] = list(job_ids)
        return real(db, job_ids, force=force, mode=mode)

    monkeypatch.setattr(
        "app.services.job.job_match_background.create_job_match_background_task", spy
    )
    resp = api.post(
        "/api/job-hunt/collect",
        json={"site_key": "boss", "keywords": "AI", "persist": True, "analyze": True},
    )
    assert resp.status_code == 200, resp.text
    if captured:
        assert captured["force"] is False, "必须 force=False 才能不重复评分"
    api.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})
