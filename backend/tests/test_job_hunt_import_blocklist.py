# SPDX-License-Identifier: Apache-2.0
"""预览导入 + 黑名单测试：只导勾选的、来源标注、黑名单过滤。"""
from __future__ import annotations

import pytest



def _stub_dict(title="AI 工程师", company="某公司", url="https://example.com/j1", salary="8-12K"):
    return {
        "title": title,
        "company": company,
        "location": "广州",
        "salary_raw": "\ue039-\ue032\ue033K",
        "salary_decoded": salary,
        "salary_decoded_ok": True,
        "url": url,
        "posted_at": "",
    }


@pytest.fixture()
def native(client):
    client.put("/api/job-hunt/config", json={"job_hunt_backend": "native"})
    yield client
    client.put("/api/job-hunt/config", json={"job_hunt_backend": "sidecar"})


# ---------- 导入 ----------


def test_import_only_selected(native):
    """只导勾选的那几条，不是全部。"""
    resp = native.post(
        "/api/job-hunt/import",
        json={"site_key": "boss", "stubs": [_stub_dict()], "backfill_jd": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["persisted"]["inserted"] == 1
    assert body["origin_source"] == "BOSS直聘"

    jobs = native.get("/api/jobs?page_size=100").json()["items"]
    assert any(j["title"] == "AI 工程师" for j in jobs)


def test_import_marks_origin_source(native):
    """来源字段写明平台名，岗位广场能直接看到。"""
    native.post(
        "/api/job-hunt/import",
        json={
            "site_key": "liepin",
            "stubs": [_stub_dict(title="猎聘独有岗位", company="猎聘独有公司", url="https://example.com/unique-liepin")],
            "backfill_jd": False,
        },
    )
    jobs = native.get("/api/jobs?page_size=100").json()["items"]
    job = next(j for j in jobs if j["title"] == "猎聘独有岗位")
    assert job["origin_source"] == "猎聘"
    assert job["source"] == "job_hunt"


def test_import_is_idempotent(native):
    payload = {"site_key": "boss", "stubs": [_stub_dict()], "backfill_jd": False}
    first = native.post("/api/job-hunt/import", json=payload).json()
    second = native.post("/api/job-hunt/import", json=payload).json()
    assert first["persisted"]["inserted"] == 1
    assert second["persisted"]["inserted"] == 0
    assert second["persisted"]["skipped_duplicate"] == 1


def test_import_rejects_empty_stubs(native):
    resp = native.post("/api/job-hunt/import", json={"site_key": "boss", "stubs": []})
    assert resp.status_code == 400


def test_import_unknown_platform(native):
    resp = native.post(
        "/api/job-hunt/import", json={"site_key": "nope", "stubs": [_stub_dict()]}
    )
    assert resp.status_code == 404


# ---------- 黑名单 ----------


def test_blocklist_default_empty(native):
    resp = native.get("/api/job-hunt/blocklist")
    assert resp.status_code == 200
    assert resp.json() == {"companies": [], "keywords": []}


def test_blocklist_roundtrip(native):
    payload = {"companies": ["某外包"], "keywords": ["销售"]}
    assert native.put("/api/job-hunt/blocklist", json=payload).json() == payload
    assert native.get("/api/job-hunt/blocklist").json() == payload


def test_blocklist_can_be_cleared(native):
    native.put("/api/job-hunt/blocklist", json={"companies": ["A"], "keywords": ["B"]})
    native.put("/api/job-hunt/blocklist", json={"companies": [], "keywords": []})
    assert native.get("/api/job-hunt/blocklist").json() == {"companies": [], "keywords": []}


def test_is_blocked_logic():
    from app.api.job_hunt import BlocklistConfig, is_blocked

    class S:
        company = "某某外包科技有限公司"
        title = "AI 销售顾问"

    cfg = BlocklistConfig(companies=["外包"], keywords=[])
    assert is_blocked(S(), cfg) is True

    cfg2 = BlocklistConfig(companies=[], keywords=["销售"])
    assert is_blocked(S(), cfg2) is True

    cfg3 = BlocklistConfig(companies=["别的公司"], keywords=["别的词"])
    assert is_blocked(S(), cfg3) is False


def test_is_blocked_case_insensitive():
    from app.api.job_hunt import BlocklistConfig, is_blocked

    class S:
        company = "ABC Tech"
        title = "AI Engineer"

    assert is_blocked(S(), BlocklistConfig(keywords=["abc"])) is True
