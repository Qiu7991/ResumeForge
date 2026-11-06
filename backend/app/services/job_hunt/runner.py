# SPDX-License-Identifier: Apache-2.0
"""自研求职采集的通用层：翻页、去重、进度上报。平台无关。

分工：**适配器**（``sites/``）只回答「搜索 URL 怎么拼、页面怎么解析」；本模块回答
「翻几页、哪些重复了、什么情况下停」。与既有 ``services/apply/collector.py`` 的关系：
那是投递台"采集→暂存备选岗位"的编排（直接落库），这里只产出内存里的 ``JobStub``
列表——入库/入队是后续层（API / J7 断点续采）的事，两层各自独立演进。

取页面走**注入的抓取器**（``fetch(url) -> html``）：生产用 ``cdp_fetcher``（复用
既有 CDP 客户端与 ``page_ready`` 等待原语，不自建浏览器管理），测试注入假抓取器
（夜间无登录态，E17）。

停止语义（按页判断，先到先停）：
- 翻满 ``max_pages``；
- 某页解析结果为空（翻过头了）；
- 某页的岗位**全部**是已见过的 URL（站点开始重复推送，再翻只会原样循环）；
- ``on_progress`` 回调返回 False（调用方主动喊停）；
- 抓取/解析抛异常（记录后停止——站点改版或风控，继续翻没有意义）。
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .base import HuntCriteria, JobParseError, JobSiteAdapter, JobStub

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 10


@dataclass
class HuntReport:
    """一次采集的结果与账目。

    ``stubs`` 是**本条 URL 首次出现**的岗位（跨页重复已去重）；``duplicates`` 是
    被去重跳过的条数；``stopped_reason`` 说明翻页为何停（见模块 docstring）。
    """

    stubs: list[JobStub] = field(default_factory=list)
    pages_fetched: int = 0
    duplicates: int = 0
    stopped_reason: str = ""
    errors: list[str] = field(default_factory=list)
    # 实际翻到的页码清单（断点续采 J7 用它登记游标）。
    visited_pages: list[int] = field(default_factory=list)


def criteria_from(value: dict | HuntCriteria | None) -> HuntCriteria:
    """把 dict / HuntCriteria / None 统一成 ``HuntCriteria``（多余键不炸，进 extra）。"""
    if value is None:
        return HuntCriteria()
    if isinstance(value, HuntCriteria):
        return value
    known = {k: value[k] for k in ("keywords", "city", "page_size") if k in value}
    extra = {k: v for k, v in value.items() if k not in ("keywords", "city", "page_size")}
    return HuntCriteria(extra=extra, **known)


class JobHuntRunner:
    """采集编排器：拼 URL → 取页面 → 解析 → 翻页 → 去重。"""

    def __init__(self, adapter: JobSiteAdapter, *, max_pages: int | None = None) -> None:
        self._adapter = adapter
        self._max_pages = max_pages if max_pages is not None else adapter.max_pages()

    def run(
        self,
        criteria: dict | HuntCriteria | None = None,
        *,
        fetch: Callable[[str], str] | None = None,
        on_progress: Callable[[int, int, int], bool | None] | None = None,
    ) -> HuntReport:
        """跑一次采集。

        Args:
            criteria: 搜索条件（dict 或 ``HuntCriteria``）。
            fetch: 取页面回调（url → HTML）。缺省时用构造时给的客户端，两者都没有
                则拒绝运行（宁可报错，不偷偷连网）。
            on_progress: 每页回调 ``(page, new_count, total)``；返回 False 主动停止。

        Returns:
            ``HuntReport``——调用方只管消费，翻页/去重/停止的账目都在里面。
        """
        report = HuntReport()
        if fetch is None:
            # 快速失败：没有抓取器就不该开始（也避免 RuntimeError 被下面的逐页
            # except 吞成一笔"抓取失败"账目）。
            raise RuntimeError(
                f"平台 {self._adapter.key} 的自研采集需要页面抓取器："
                "请注入 fetch 回调（生产用 cdp_fetcher(client)，测试注入假抓取器）"
            )
        query = criteria_from(criteria)
        seen: set[str] = set()
        for page in range(1, self._max_pages + 1):
            url = self._adapter.build_search_url(query, page)
            try:
                html = fetch(url)
                page_stubs = self._adapter.parse_list(html)
            except JobParseError as exc:
                report.errors.append(f"第 {page} 页解析失败：{exc.detail}")
                report.stopped_reason = "parse_error"
                return report
            except Exception as exc:  # noqa: BLE001 — 抓取层异常按页记账并停，不炸整个 run
                report.errors.append(f"第 {page} 页抓取失败：{exc.__class__.__name__}: {exc}")
                report.stopped_reason = "fetch_error"
                return report
            report.pages_fetched += 1
            report.visited_pages.append(page)
            fresh: list[JobStub] = []
            for stub in page_stubs:
                if not stub.url:
                    continue  # 没有链接的卡片无法去重也无法投递，直接丢弃
                key = _dedup_key(stub.url)
                if key in seen:
                    report.duplicates += 1
                    continue
                seen.add(key)
                fresh.append(stub)
            if not page_stubs:
                report.stopped_reason = "no_results"
                return report
            if not fresh:
                report.stopped_reason = "repeated_page"
                return report
            report.stubs.extend(fresh)
            if on_progress is not None:
                keep_going = on_progress(page, len(fresh), len(report.stubs))
                if keep_going is False:
                    report.stopped_reason = "stopped"
                    return report
        report.stopped_reason = "max_pages"
        return report


def _dedup_key(url: str) -> str:
    """URL 归一化：去 fragment 与尾部空白（query 保留——那是翻页/筛选的一部分）。"""
    return url.strip().split("#", 1)[0]


def cdp_fetcher(
    client: Any, *, timeout_seconds: float = 20.0, poll_interval: float = 0.4
) -> Callable[[str], str]:
    """生产抓取器：复用既有 CDP 客户端（导航 + 就绪等待 + 取 outerHTML）。

    就绪等待复用 ``services/browser/page_ready`` 的轮询原语（只等文档可用，不做
    站点特定的内容判定——内容是否解析得出来由适配器负责）。超时/轮询间隔可调
    （测试注入小值，不真等 20 秒）。
    """
    from ..browser.page_ready import ReadyWait, wait_for_page_state

    def fetch(url: str) -> str:
        client.navigate(url)
        wait_for_page_state(
            lambda: {"readyState": client.evaluate("document.readyState")},
            is_ready=lambda state: state.get("readyState") in ("interactive", "complete"),
            on_timeout=lambda state: TimeoutError(f"页面加载超时：{url}（state={state}）"),
            config=ReadyWait(timeout=timeout_seconds, poll_interval=poll_interval),
        )
        html = client.evaluate("document.documentElement.outerHTML")
        if not isinstance(html, str) or not html:
            raise JobParseError("页面内容为空", site_key="")
        return html

    return fetch


__all__ = ["JobHuntRunner", "HuntReport", "criteria_from", "cdp_fetcher", "DEFAULT_MAX_PAGES"]
