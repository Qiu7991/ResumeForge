"""按链接导入岗位：URL 归属、浏览器前置、详情落库与去重。"""

from __future__ import annotations

ZHIPIN_URL = "https://www.zhipin.com/job_detail/abc123.html"


class _FakeCdpClient:
    """导入现在会先开一个专用标签页，再在它上面抓详情；假客户端补齐这两个能力。"""

    def __init__(self) -> None:
        self.closed = False
        self.closed_target = None

    def new_tab(self, url: str = "about:blank") -> str:
        return "fake-target"

    def send(self, method, params=None, **kwargs):
        self.closed_target = (method, params)
        return {}

    def close(self) -> None:
        self.closed = True


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

    class FakeClient(_FakeCdpClient):
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
    # 抓详情用的是新开的专用标签页，抓完关掉；绝不能导航用户当前的活动页。
    assert client_obj.closed_target is not None
    assert client_obj.closed_target[0] == "Target.closeTarget"

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

    class FakeClient(_FakeCdpClient):
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
            class C(_FakeCdpClient):
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


def test_long_tracking_url_is_canonicalized_before_use():
    """BOSS 详情页的 securityId 查询串不是岗位身份，不能顶爆 URL 字段。"""
    from app.api.job_import import _canonical_job_url

    long_url = ZHIPIN_URL + "?securityId=" + "x" * 600
    assert len(long_url) > 512
    assert _canonical_job_url(long_url) == ZHIPIN_URL


def test_import_url_schema_accepts_long_tracking_urls():
    """512 的旧上限会把真实 BOSS 链接直接拦在 422，先放进来再规范化。"""
    from app.schemas.job import JobImportUrlIn

    long_url = ZHIPIN_URL + "?securityId=" + "x" * 600
    assert JobImportUrlIn(url=long_url).url == long_url


def test_long_tracking_url_is_fetched_verbatim_but_stored_canonical(client, monkeypatch):
    """securityId 是抓取详情所必需的，不能丢；但入库只留岗位路径。"""
    from app.api import job_import
    from app.services.sites.registry import get_registry

    class RunningStatus:
        state = "running"

    class FakeClient(_FakeCdpClient):
        def close(self) -> None:
            return None

    class FakeManager:
        def client(self) -> FakeClient:
            return FakeClient()

    monkeypatch.setattr(job_import, "browser_status", lambda _db: RunningStatus())
    monkeypatch.setattr(job_import, "get_browser_manager", lambda _db: FakeManager())

    seen: dict[str, str] = {}
    adapter = get_registry().for_target(ZHIPIN_URL)
    monkeypatch.setattr(
        adapter,
        "fetch_job_detail",
        lambda _client, url: seen.update(url=url) or {
            "job_title": "人工智能训练师",
            "company": "极擎科技",
            "description": "岗位职责全文",
            "requirements": "任职要求全文",
            "url": url,
        },
    )

    long_url = ZHIPIN_URL + "?securityId=" + "x" * 600
    created = client.post("/api/jobs/import-url", json={"url": long_url})
    assert created.status_code == 200, created.text
    assert seen["url"] == long_url
    job = created.json()
    assert job["source_url"] == ZHIPIN_URL

    # 再用规范化链接导入：命中的是同一条，不再造重复岗位。
    again = client.post("/api/jobs/import-url", json={"url": ZHIPIN_URL})
    assert again.status_code == 200
    assert again.json()["id"] == job["id"]
