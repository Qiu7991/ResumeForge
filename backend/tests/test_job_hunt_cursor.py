# SPDX-License-Identifier: Apache-2.0
"""断点续采测试：模拟中断 → 带游标恢复 → 断言不重复采（J7）。"""
from __future__ import annotations

import pytest

from app.services.job_hunt.base import JobSiteAdapter, JobStub, HuntCriteria
from app.services.job_hunt.cursor_store import clear_cursor, kv_key, load_cursor, save_cursor
from app.services.job_hunt.runner import HuntCursor, JobHuntRunner, hash_criteria


class FakeAdapter(JobSiteAdapter):
    key = "fake"
    name = "假平台"

    def __init__(self, pages: dict[int, list[str]]):
        self._pages = pages

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        return f"https://fake.example/list?page={page}"

    def parse_list(self, html: str) -> list[JobStub]:
        page = int(html.split("page=")[1])
        return [JobStub(title=t, url=f"https://fake.example/job/{t}.html")
                for t in self._pages.get(page, [])]

    def parse_detail(self, html: str) -> JobStub:  # pragma: no cover
        raise NotImplementedError

    def supports(self, url: str) -> bool:  # pragma: no cover
        return True


def fake_fetch(url: str) -> str:
    return url


def test_hash_criteria_stable_and_distinct():
    a = hash_criteria("boss", {"keywords": "AI", "city": "广州"})
    b = hash_criteria("boss", {"keywords": "AI", "city": "广州"})
    assert a == b and len(a) == 16
    assert a != hash_criteria("boss", {"keywords": "AI", "city": "深圳"})
    assert a != hash_criteria("zhilian", {"keywords": "AI", "city": "广州"})


def test_cursor_roundtrip():
    c = HuntCursor(site_key="boss", criteria_hash="h1", last_page=3,
                   done_urls={"https://a/x.html", "https://a/y.html"})
    d = HuntCursor.from_dict(c.to_dict())
    assert d is not None and d.site_key == "boss" and d.last_page == 3
    assert d.done_urls == {"https://a/x.html", "https://a/y.html"}
    assert HuntCursor.from_dict("垃圾") is None
    assert HuntCursor.from_dict({}) is None
    assert HuntCursor.from_dict({"site_key": "boss", "criteria_hash": "h", "last_page": "abc"}).last_page == 0


def test_interrupt_then_resume_no_refetch():
    pages = {1: ["A", "B"], 2: ["B", "C"], 3: ["D"], 4: ["E"]}
    adapter = FakeAdapter(pages)
    fetched: list[str] = []

    def recording_fetch(url: str) -> str:
        fetched.append(url)
        return url

    # 第一次：第 2 页后中断（模拟停机）
    first = JobHuntRunner(adapter, max_pages=9).run(
        {"keywords": "AI"}, fetch=recording_fetch,
        on_progress=lambda page, new, total: page < 2)
    assert first.stopped_reason == "stopped"
    assert [s.title for s in first.stubs] == ["A", "B", "C"]
    cursor = first.next_cursor
    assert cursor is not None and cursor.last_page == 2
    assert cursor.done_urls == {f"https://fake.example/job/{t}.html" for t in ("A", "B", "C")}

    # 恢复：只翻第 3 页起；第 2 页的 C 再出现也不算新
    second = JobHuntRunner(adapter, max_pages=9).run(
        {"keywords": "AI"}, fetch=recording_fetch, cursor=cursor)
    assert second.resumed_from_page == 2
    assert [s.title for s in second.stubs] == ["D", "E"]
    assert second.stopped_reason == "no_results"  # 第 5 页空 → 正常翻完停
    # 两次 run 合计恰好抓了 5 页（第 1、2 页没有因恢复而重新抓）
    assert fetched == [
        "https://fake.example/list?page=1",
        "https://fake.example/list?page=2",
        "https://fake.example/list?page=3",
        "https://fake.example/list?page=4",
        "https://fake.example/list?page=5",
    ]


def test_resume_counts_known_urls_as_duplicates():
    pages = {1: ["A"], 2: ["A", "B"]}
    cursor = HuntCursor(site_key="fake", criteria_hash=hash_criteria("fake", {}),
                        last_page=1, done_urls={"https://fake.example/job/A.html"})
    report = JobHuntRunner(FakeAdapter(pages), max_pages=2).run({}, fetch=fake_fetch, cursor=cursor)
    # A 在第 2 页再次出现 → 重复；B 新采
    assert [s.title for s in report.stubs] == ["B"]
    assert report.duplicates == 1


def test_error_page_not_counted_in_cursor():
    class HalfBroken(FakeAdapter):
        def parse_list(self, html: str) -> list[JobStub]:
            if "page=2" in html:
                raise RuntimeError("结构炸了")
            return super().parse_list(html)

    report = JobHuntRunner(HalfBroken({1: ["A"], 2: ["B"]}), max_pages=3).run({}, fetch=fake_fetch)
    assert report.stopped_reason == "fetch_error"
    assert report.next_cursor is not None
    assert report.next_cursor.last_page == 1  # 第 2 页失败不计入
    assert report.next_cursor.done_urls == {"https://fake.example/job/A.html"}


def test_mismatched_cursor_starts_fresh():
    pages = {1: ["A"]}
    other = HuntCursor(site_key="other_site", criteria_hash="zzz", last_page=5,
                       done_urls={"https://x/1"})
    report = JobHuntRunner(FakeAdapter(pages), max_pages=2).run({}, fetch=fake_fetch, cursor=other)
    assert report.resumed_from_page == 0
    assert [s.title for s in report.stubs] == ["A"]


# ---------------------------------------------------------------------------
# cursor_store：AppSetting KV 持久化（用 conftest 的测试库）
# ---------------------------------------------------------------------------


def test_store_roundtrip(db_session):
    cursor = HuntCursor(site_key="boss", criteria_hash=hash_criteria("boss", {"keywords": "AI"}),
                        last_page=2, done_urls={"https://a/1"})
    assert load_cursor(db_session, "boss", cursor.criteria_hash) is None
    save_cursor(db_session, cursor)
    loaded = load_cursor(db_session, "boss", cursor.criteria_hash)
    assert loaded is not None and loaded.last_page == 2
    assert loaded.done_urls == {"https://a/1"}
    # 覆盖保存
    cursor.last_page = 5
    save_cursor(db_session, cursor)
    assert load_cursor(db_session, "boss", cursor.criteria_hash).last_page == 5  # type: ignore[union-attr]
    clear_cursor(db_session, "boss", cursor.criteria_hash)
    assert load_cursor(db_session, "boss", cursor.criteria_hash) is None


def test_store_corrupted_value_is_dropped(db_session):
    from app.models.setting import AppSetting

    h = hash_criteria("zhilian", {"keywords": "AI"})
    db_session.add(AppSetting(key=kv_key("zhilian", h), value="{不是JSON"))
    db_session.commit()
    assert load_cursor(db_session, "zhilian", h) is None  # 损坏即丢弃并清理
    assert db_session.get(AppSetting, kv_key("zhilian", h)) is None


def test_store_rejects_incomplete_cursor(db_session):
    with pytest.raises(ValueError, match="criteria_hash"):
        save_cursor(db_session, HuntCursor(site_key="boss", criteria_hash="", last_page=1))
