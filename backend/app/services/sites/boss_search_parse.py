# SPDX-License-Identifier: Apache-2.0
"""BOSS 响应的纯函数解析层：搜索结果规整、岗位详情规整、响应体收集与接口错误归一。

2026-10-22（行数预算审计 A2）：从 ``boss_search`` 拆出——这 4 个模块级函数不依赖
``self``，只回答「这段响应能解析成什么」与「这个接口错误该怎么翻译」。
``boss_search`` 仍以同名 re-export 保留原命名空间（``boss.py`` / ``boss_scroll.py``
的 import 一个字都不用改）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ...models.apply import FAILURE_SELECTOR_INVALID
from ..browser.cdp_client import CdpClient, CdpError
from .base import SearchPage, SearchResult, SiteFailure
from .boss_network import DETAIL_MARKERS, SEARCH_MARKERS, api_error
from .boss_page import BOSS_DISPLAY_NAME
from .boss_search_scripts import NETWORK_RESPONSE_EVENT
from .boss_text import looks_like_salary, normalize_text, split_job_fields, split_title_salary

logger = logging.getLogger(__name__)


def parse_search_payload(
    payload: dict[str, Any], page: int, unmapped_conditions: list[str] | None = None
) -> SearchPage:
    """把 BOSS 搜索结果响应规整成 SearchPage；薪资缺失或不像薪资时退回标题里拆出的薪资。"""
    if not isinstance(payload, dict):
        raise SiteFailure(FAILURE_SELECTOR_INVALID, "搜索结果返回了无法解析的内容")
    results: list[SearchResult] = []
    items = payload.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            title, title_salary = split_title_salary(item.get("title", ""))
            if not title:
                continue
            salary = normalize_text(item.get("salary", ""))
            if not looks_like_salary(salary):
                salary = title_salary
            results.append(
                SearchResult(
                    title=title,
                    company=normalize_text(item.get("company", "")),
                    location=normalize_text(item.get("location", "")),
                    salary=salary,
                    url=str(item.get("url", "")),
                    source=BOSS_DISPLAY_NAME,
                )
            )
    return SearchPage(
        results=results,
        page=page,
        has_next=bool(payload.get("has_next")),
        unmapped_conditions=list(unmapped_conditions or []),
    )


#: 详情页 DOM 的「公司」选择器取错时，常见结果是把岗位名和薪资粘在一起
#: （如 ``“AI 应用开发助理（双休+五险一金）\n8-13K”``）。这两种形状必须拦截。
_SALARY_IN_COMPANY = re.compile(r"\d+(?:\.\d+)?\s*[-~–—至]\s*\d+(?:\.\d+)?\s*[Kk]")
_COMPANY_FROM_TITLE_PATTERNS = (
    re.compile(r"^.+?[_｜|]\s*(.+?)\s*招聘"),
    re.compile(r"^.+?[_｜|]\s*(.+?)\s*[-–—]\s*BOSS", re.IGNORECASE),
    re.compile(r"「.+?」\s*(.+?)招聘"),
)


def _company_from_page_title(title: object) -> str:
    """从 ``“岗位_公司招聘-BOSS直聘”`` 这类页面标题里拆出公司名；拆不出返回空串。"""
    text = normalize_text(title)
    for pattern in _COMPANY_FROM_TITLE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return ""


#: 选择器落在导航/栏目标签上时取到的值，不是公司名。
_GENERIC_COMPANY_LABELS = frozenset({"公司", "企业", "招聘", "BOSS直聘", "公司信息"})


def _clean_detail_company(payload: dict[str, Any], job_title: str) -> str:
    """详情页公司名兜底：选择器取到岗位名/薪资/栏目标签时，改从页面标题拆。"""
    company = normalize_text(payload.get("company", ""))
    if not company:
        return company
    polluted = (
        "\n" in company
        or bool(_SALARY_IN_COMPANY.search(company))
        or company in _GENERIC_COMPANY_LABELS
        or len(company) < 3
        or (job_title and company.startswith(job_title))
    )
    if not polluted:
        return company
    return _company_from_page_title(payload.get("title", "")) or company


def parse_job_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """把 BOSS 岗位详情响应规整成标准字段；需求缺失时退回描述里拆出的需求。"""
    if not isinstance(payload, dict):
        raise SiteFailure(FAILURE_SELECTOR_INVALID, "岗位详情返回了无法解析的内容")
    dom_requirements = normalize_text(payload.get("requirements", ""))
    sections = split_job_fields(payload.get("description", ""))
    job_title = normalize_text(payload.get("job_title", ""))
    return {
        "job_title": job_title,
        "company": _clean_detail_company(payload, job_title),
        "description": sections.description,
        "requirements": dom_requirements or sections.requirements,
        # 福利待遇 / 公司介绍这类第三段（对应 ``Job.additional_info``）。
        "additional_info": sections.additional,
        "url": str(payload.get("url", "")),
    }


def _with_response_bodies(client: CdpClient, events: list[dict[str, Any]]) -> list[Any]:
    from ..browser.network_capture import MAX_PARSED_RESPONSES, collect_bodies, response_urls

    wanted = {
        url
        for markers in (SEARCH_MARKERS, DETAIL_MARKERS)
        for url in response_urls(events, markers=markers)
    }
    body_events: list[dict[str, Any]] = []
    fetched: set[str] = set()
    for event in events:
        if len(body_events) >= MAX_PARSED_RESPONSES:
            break
        if event.get("method") != NETWORK_RESPONSE_EVENT:
            continue
        params = event.get("params")
        if not isinstance(params, dict):
            continue
        request_id = str(params.get("requestId") or "")
        if not request_id or request_id in fetched:
            continue
        response = params.get("response")
        url = str(response.get("url") or "") if isinstance(response, dict) else ""
        if url not in wanted:
            continue
        try:
            result = client.send("Network.getResponseBody", {"requestId": request_id})
        except CdpError:
            logger.debug("取响应体失败（可能已被回收）：%s", url)
            continue
        fetched.add(request_id)
        body_events.append(
            {"method": "Network.getResponseBody", "requestId": request_id, "result": result}
        )
    if not body_events:
        return []
    return collect_bodies([*events, *body_events])


def _raise_api_error(responses: list[Any], markers: tuple[str, ...], operation: str) -> None:
    for response in responses:
        url = str(getattr(response, "url", "") or "")
        if not any(marker and marker in url for marker in markers):
            continue
        error = api_error(getattr(response, "body", None))
        if error is None:
            continue
        code, message = error
        suffix = f"：{message}" if message else ""
        raise SiteFailure(
            FAILURE_SELECTOR_INVALID,
            f"BOSS {operation}接口返回错误 code={code}{suffix}。请检查筛选条件后重试",
            url=url,
        )
