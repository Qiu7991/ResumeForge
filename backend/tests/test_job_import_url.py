"""按链接导入岗位：URL 归属、浏览器前置、详情落库与去重。"""

from __future__ import annotations

import pytest

ZHIPIN_URL = "https://www.zhipin.com/job_detail/abc123.html"


def test_rejects_a_url_outside_registered_sites(client):
    """非已注册站点：明确 422，并说明不支持——不做通用爬虫硬塞半个空壳。"""
    response = client.post("/api/jobs/import-url", json={"url": "https://example.com/job/1"})
    assert response.status_code == 422
    assert "暂不支持" in response.json()["detail"]


def test_requires_the_dedicated_browser_to_be_running(client, monkeypatch):
    from app.api import job_import

    class StoppedStatus:
        state = "stopped"

    monkeypatch.setattr(job_import, "browser_status", lambda _db: StoppedStatus())
    response = client.post("/api/jobs/import-url", json={"url": ZHIPIN_URL})
    assert response.status_code == 409
    assert "专用浏览器" in response.json()["detail"]


def test_creates_a_job_from_the_page_detail_and_dedupes(client, monkeypatch):
    from app.api import job_import
    from app.services.sites.registry import get_registry

    class RunningStatus:
        state = "running"

    class FakeClient:
        closed = False

        def close(self) -> None:
            self.closed = True

    client_obj = FakeClient()

    class FakeManager:
        def client(self) -> FakeClient:
            return client_obj

    monkeypatch.setattr(job_import, "browser_status", lambda _db: RunningStatus())
    monkeypatch.setattr(job_import, "get_browser_manager", lambda _db: FakeManager())

    adapter = get_registry().for_target(ZHIPIN_URL)
    monkeypatch.setattr(
        adapter,
        "fetch_job_detail",
        lambda _client, url: {
            "job_title": "AI 开发助理",
            "company": "示例贸易",
            "description": "岗位职责全文",
            "requirements": "任职要求全文",
            "additional_info": "福利待遇",
            "url": url,
        },
    )

    created = client.post("/api/jobs/import-url", json={"url": ZHIPIN_URL})
    assert created.status_code == 200, created.text
    job = created.json()
    assert job["title"] == "AI 开发助理"
    assert job["company"] == "示例贸易"
    assert job["description"] == "岗位职责全文"
    assert job["source_url"] == ZHIPIN_URL
    # 来源命中站点域名 → 可以直接进投递台
    assert job["apply_supported"] is True
    assert client_obj.closed is True

    # 同一链接再导入：返回同一条，不在岗位广场里出现重复岗位
    again = client.post("/api/jobs/import-url", json={"url": ZHIPIN_URL})
    assert again.status_code == 200
    assert again.json()["id"] == job["id"]


class _RunningStatus:
    state = "running"


def test_import_current_without_running_browser(client, monkeypatch):
    from app.api import job_import

    class StoppedStatus:
        state = "stopped"

    monkeypatch.setattr(job_import, "browser_status", lambda _db: StoppedStatus())
    response = client.post("/api/jobs/import-current")
    assert response.status_code == 409
    assert "专用浏览器" in response.json()["detail"]


def test_import_current_requires_a_job_detail_tab(client, monkeypatch):
    """只有搜索页/首页时不要瞎猜：直接告诉用户点进岗位再来一次。"""
    from app.api import job_import

    class FakeManager:
        def list_page_targets(self):
            return [
                {"type": "page", "url": "https://www.zhipin.com/web/geek/jobs?query=ai"},
                {"type": "page", "url": "https://www.zhipin.com/"},
            ]

    monkeypatch.setattr(job_import, "browser_status", lambda _db: _RunningStatus())
    monkeypatch.setattr(job_import, "get_browser_manager", lambda _db: FakeManager())

    response = client.post("/api/jobs/import-current")
    assert response.status_code == 409
    assert "岗位详情页" in response.json()["detail"]


def test_import_current_picks_the_detail_tab_and_creates_the_job(client, monkeypatch):
    from app.api import job_import
    from app.services.sites.registry import get_registry

    class FakeClient:
        def close(self) -> None:
            pass

    class FakeManager:
        def list_page_targets(self):
            # 最近的标签在前：搜索页先出现、详情页在第二条，仍要挑详情页。
            return [
                {"type": "page", "url": "https://www.zhipin.com/web/geek/jobs?query=ai"},
                {"type": "page", "url": "https://www.zhipin.com/job_detail/xyz789.html"},
            ]

        def client(self):
            return FakeClient()

    monkeypatch.setattr(job_import, "browser_status", lambda _db: _RunningStatus())
    monkeypatch.setattr(job_import, "get_browser_manager", lambda _db: FakeManager())

    adapter = get_registry().for_target("https://www.zhipin.com/")
    monkeypatch.setattr(
        adapter,
        "fetch_job_detail",
        lambda _client, url: {
            "job_title": "AI 应用与自动化专员",
            "company": "丰域科技",
            "description": "岗位职责全文",
            "requirements": "任职要求全文",
            "url": url,
        },
    )

    response = client.post("/api/jobs/import-current")
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["title"] == "AI 应用与自动化专员"
    assert job["source_url"] == "https://www.zhipin.com/job_detail/xyz789.html"


def test_import_infers_job_type_from_the_jd(client, monkeypatch):
    """导入的岗位类型按 JD 推断：应届字样 → 校招；普通社招 JD → 社招。"""
    from app.api import job_import
    from app.services.sites.registry import get_registry

    class Status:
        state = "running"

    class Manager:
        def client(self):
            class C:
                def close(self) -> None:
                    pass

            return C()

    monkeypatch.setattr(job_import, "browser_status", lambda _db: Status())
    monkeypatch.setattr(job_import, "get_browser_manager", lambda _db: Manager())

    adapter = get_registry().for_target(ZHIPIN_URL)

    def fake_detail(_client, url):
        return {
            "job_title": "AI 应用工程师",
            "company": "示例公司",
            "description": "招聘 2026 届毕业生，负责 LLM 应用落地。",
            "requirements": "本科及以上",
            "url": url,
        }

    monkeypatch.setattr(adapter, "fetch_job_detail", fake_detail)
    job = client.post("/api/jobs/import-url", json={"url": ZHIPIN_URL}).json()
    assert job["job_type"] == "校招"
