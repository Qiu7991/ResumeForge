# SPDX-License-Identifier: Apache-2.0
"""采集通用层测试：翻页 / 去重 / 停止语义 / 进度，全部用假适配器 + 假抓取器。

不连真实网站（E17）；浏览器路径只测「没有抓取器时拒绝运行」与 cdp_fetcher 的
消息编排（假 CDP 客户端），不启动任何真实浏览器（红线 3）。
"""
from __future__ import annotations

import pytest

from app.services.job_hunt.base import HuntCriteria, JobParseError, JobSiteAdapter, JobStub
from app.services.job_hunt.runner import JobHuntRunner, cdp_fetcher, criteria_from


class FakeAdapter(JobSiteAdapter):
    """假适配器：URL 里带页码；每页返回预置的岗位标题列表。"""

    key = "fake"
    name = "假平台"

    def __init__(self, pages: dict[int, list[str]], *, fail_pages: set[int] | None = None):
        self._pages = pages
        self._fail_pages = fail_pages or set()
        self.built_urls: list[str] = []

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        self.built_urls.append(f"search?kw={criteria.keywords}&page={page}")
        return f"https://fake.example/list?kw={criteria.keywords}&page={page}"

    def parse_list(self, html: str) -> list[JobStub]:
        page = int(html.split("page=")[1])
        if page in self._fail_pages:
            raise JobParseError("卡片结构不认识", site_key=self.key)
        return [JobStub(title=t, company=f"公司{t}", url=f"https://fake.example/job/{t}.html")
                for t in self._pages.get(page, [])]

    def parse_detail(self, html: str) -> "JobDetail":  # pragma: no cover - runner 不用
        raise NotImplementedError

    def supports(self, url: str) -> bool:  # pragma: no cover - runner 不用
        return "fake.example" in url


def fake_fetch(url: str) -> str:
    return url  # 假抓取器：URL 即页面（页码藏在里面）


def stubs_of(report) -> list[str]:
    return [s.title for s in report.stubs]


def test_pagination_and_dedup():
    adapter = FakeAdapter({1: ["A", "B"], 2: ["B", "C"], 3: ["C", "D"], 4: []})
    report = JobHuntRunner(adapter).run({"keywords": "AI"}, fetch=fake_fetch)
    # B、C 跨页重复被去重；空页触发 no_results
    assert stubs_of(report) == ["A", "B", "C", "D"]
    assert report.duplicates == 2
    assert report.pages_fetched == 4
    assert report.stopped_reason == "no_results"
    assert report.visited_pages == [1, 2, 3, 4]


def test_max_pages_cap():
    adapter = FakeAdapter({p: [f"J{p}"] for p in range(1, 12)})
    report = JobHuntRunner(adapter, max_pages=4).run({}, fetch=fake_fetch)
    assert stubs_of(report) == ["J1", "J2", "J3", "J4"]
    assert report.stopped_reason == "max_pages"


def test_repeated_page_stops_early():
    # 第 4 页全部是已见过的 URL → 站点在循环推送，提前停
    adapter = FakeAdapter({1: ["A", "B"], 2: ["A", "B"], 3: ["A", "B"]})
    report = JobHuntRunner(adapter, max_pages=9).run({}, fetch=fake_fetch)
    assert stubs_of(report) == ["A", "B"]
    assert report.stopped_reason == "repeated_page"
    assert report.pages_fetched == 2
    assert report.duplicates == 2


def test_parse_error_records_and_stops():
    adapter = FakeAdapter({1: ["A"], 2: ["B"]}, fail_pages={2})
    report = JobHuntRunner(adapter, max_pages=5).run({}, fetch=fake_fetch)
    assert stubs_of(report) == ["A"]
    assert report.stopped_reason == "parse_error"
    assert "第 2 页" in report.errors[0]


def test_fetch_error_records_and_stops():
    def broken(url: str) -> str:
        raise ConnectionError("CDP 断了")

    adapter = FakeAdapter({1: ["A"]})
    report = JobHuntRunner(adapter).run({}, fetch=broken)
    assert report.stubs == []
    assert report.stopped_reason == "fetch_error"
    assert "ConnectionError" in report.errors[0]


def test_progress_stop_requested():
    adapter = FakeAdapter({1: ["A"], 2: ["B"], 3: ["C"]})
    calls: list[tuple[int, int, int]] = []

    def progress(page: int, new: int, total: int) -> bool:
        calls.append((page, new, total))
        return page < 2  # 第 2 页后喊停

    report = JobHuntRunner(adapter, max_pages=9).run({}, fetch=fake_fetch, on_progress=progress)
    assert stubs_of(report) == ["A", "B"]
    assert report.stopped_reason == "stopped"
    assert calls == [(1, 1, 1), (2, 1, 2)]


def test_progress_none_keeps_going():
    adapter = FakeAdapter({1: ["A"], 2: ["B"], 3: ["C"]})
    report = JobHuntRunner(adapter, max_pages=9).run(
        {}, fetch=fake_fetch, on_progress=lambda *a: None)
    # on_progress 返回 None 不喊停：三页全部采完（第 4 页空 → no_results）
    assert stubs_of(report) == ["A", "B", "C"]
    assert report.stopped_reason == "no_results"


def test_no_fetcher_rejected():
    adapter = FakeAdapter({1: ["A"]})
    with pytest.raises(RuntimeError, match="fetch"):
        JobHuntRunner(adapter).run({})


def test_criteria_dict_normalization():
    adapter = FakeAdapter({1: ["A"]})
    JobHuntRunner(adapter, max_pages=1).run({"keywords": "AI", "city": "广州", "page_size": 15,
                                             "salary_min": 8}, fetch=fake_fetch)
    # keywords 进 URL；extra 键（salary_min）不炸、由适配器自行决定用不用
    assert adapter.built_urls == ["search?kw=AI&page=1"]
    qc = criteria_from({"keywords": "AI", "salary_min": 8})
    assert qc.keywords == "AI" and qc.extra == {"salary_min": 8}
    assert criteria_from(None).keywords == ""
    assert criteria_from(HuntCriteria(keywords="x")).keywords == "x"


def test_stubs_without_url_dropped():
    class NoUrlAdapter(FakeAdapter):
        def parse_list(self, html: str) -> list[JobStub]:
            return [JobStub(title="无链岗位", url=""), JobStub(title="A", url="https://fake.example/job/A.html")]

    report = JobHuntRunner(NoUrlAdapter({1: ["A"]})).run({}, fetch=fake_fetch)
    assert stubs_of(report) == ["A"]


def test_fragment_normalized_in_dedup():
    class FragAdapter(FakeAdapter):
        def parse_list(self, html: str) -> list[JobStub]:
            page = int(html.split("page=")[1])
            suffix = "" if page == 1 else "#same"
            return [JobStub(title=f"A{page}", url=f"https://fake.example/job/A.html{suffix}")]

    report = JobHuntRunner(FragAdapter({1: ["A"]}), max_pages=2).run({}, fetch=fake_fetch)
    # 同一 URL（仅 #fragment 不同）第二页视为重复 → repeated_page
    # （FragAdapter 的标题带页码：第一页 A1 / 第二页 A2，URL 都是 A.html）
    assert stubs_of(report) == ["A1"]
    assert report.stopped_reason == "repeated_page"
    assert report.duplicates == 1


# ---------------------------------------------------------------------------
# cdp_fetcher：用假 CDP 客户端验证消息编排（不启动真实浏览器）
# ---------------------------------------------------------------------------


class FakeCdpClient:
    def __init__(self, html: str, *, ready_after: int = 1):
        self.html = html
        self.calls: list[str] = []
        self._ready_after = ready_after
        self._probes = 0

    def navigate(self, url: str, **kwargs):
        self.calls.append(f"navigate:{url}")

    def evaluate(self, expression: str, **kwargs):
        self.calls.append(f"evaluate:{expression[:40]}")
        if "readyState" in expression:
            self._probes += 1
            return "complete" if self._probes >= self._ready_after else "loading"
        if "outerHTML" in expression:
            return self.html
        return None


def test_cdp_fetcher_navigates_waits_and_reads_html():
    client = FakeCdpClient("<html><body>ok</body></html>")
    fetch = cdp_fetcher(client)
    html = fetch("https://fake.example/list?page=1")
    assert html == "<html><body>ok</body></html>"
    assert client.calls[0] == "navigate:https://fake.example/list?page=1"
    assert any("readyState" in c for c in client.calls)
    assert any("outerHTML" in c for c in client.calls)


def test_cdp_fetcher_timeout_is_loud():
    client = FakeCdpClient("<html></html>", ready_after=10**9)
    fetch = cdp_fetcher(client, timeout_seconds=0.3, poll_interval=0.05)
    with pytest.raises(TimeoutError):
        fetch("https://fake.example/list")


def test_cdp_fetcher_empty_html_is_parse_error():
    client = FakeCdpClient("")
    with pytest.raises(JobParseError):
        cdp_fetcher(client)("https://fake.example/list")


# ---------------------------------------------------------------------------
# 列表 / 详情 用各自的内容就绪选择器（2026-11-11：详情错用列表选择器 → JD 残缺）
# ---------------------------------------------------------------------------


class _SelectorRecorder:
    """记录抓取层问了哪个选择器、等了哪个选择器。

    ``hits`` 决定 querySelectorAll 的返回值：只有命中指定选择器时才算渲染完，
    这样才能区分「等对了」和「等到超时仍在解析」。
    """

    def __init__(self, html: str, *, hits_for: str):
        self.html = html
        self.hits_for = hits_for
        self.expressions: list[str] = []

    def navigate(self, url: str, **kwargs):
        self.expressions.append(f"navigate:{url}")

    def evaluate(self, expression: str, **kwargs):
        self.expressions.append(expression)
        if "readyState" in expression:
            return "complete"
        if "querySelectorAll" in expression:
            return 1 if self.hits_for in expression else 0
        if "outerHTML" in expression:
            return self.html
        return None

    def waited_for(self) -> list[str]:
        return [
            e for e in self.expressions if "querySelectorAll" in e and "outerHTML" not in e
        ]


class _DetailAdapter:
    """只声明两个选择器的假适配器。"""

    content_ready_selector = lambda self: "li.job-card-box"  # noqa: E731
    detail_ready_selector = lambda self: ".job-sec-text"  # noqa: E731


def test_cdp_fetcher_list_mode_waits_for_list_selector():
    client = _SelectorRecorder("<html>list</html>", hits_for="li.job-card-box")
    html = cdp_fetcher(client, _DetailAdapter(), page_kind="list", poll_interval=0.01)(
        "https://fake.example/web/geek/jobs"
    )

    assert html == "<html>list</html>"
    waited = client.waited_for()
    assert waited, "列表模式必须等内容就绪，而不是只等 readyState"
    assert any("li.job-card-box" in e for e in waited)
    assert not any("job-sec-text" in e for e in waited), "列表页不该去等详情页的选择器"


def test_cdp_fetcher_detail_mode_waits_for_detail_selector():
    """回归：详情抓取曾错用列表选择器，导致等满超时后用半渲染 DOM 解析出残缺 JD。"""
    client = _SelectorRecorder("<html>detail</html>", hits_for=".job-sec-text")
    html = cdp_fetcher(client, _DetailAdapter(), page_kind="detail", poll_interval=0.01)(
        "https://fake.example/job_detail/abc.html"
    )

    assert html == "<html>detail</html>"
    waited = client.waited_for()
    assert any(".job-sec-text" in e for e in waited), "详情模式必须等 JD 正文容器"
    assert not any("li.job-card-box" in e for e in waited), (
        "详情模式绝不能等列表页的卡片选择器——它永远命中不了，"
        "只会白等满超时后拿半渲染的 DOM 解析出残缺 JD"
    )


def test_cdp_fetcher_defaults_to_list_mode():
    """默认保持既有行为：不传 page_kind 时按列表页处理。"""
    client = _SelectorRecorder("<html>x</html>", hits_for="li.job-card-box")
    cdp_fetcher(client, _DetailAdapter(), poll_interval=0.01)("https://fake.example/x")

    waited = client.waited_for()
    assert any("li.job-card-box" in e for e in waited)
    assert not any("job-sec-text" in e for e in waited)


def test_boss_adapter_declares_distinct_selectors():
    """BOSS 的两个选择器必须不同且都非空，否则详情抓取会退回等固定时长。"""
    from app.services.job_hunt.sites.boss import BossAdapter

    adapter = BossAdapter()
    list_selector = adapter.content_ready_selector()
    detail_selector = adapter.detail_ready_selector()

    assert list_selector == "li.job-card-box"
    assert detail_selector == ".job-sec-text"
    assert list_selector != detail_selector
