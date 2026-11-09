# SPDX-License-Identifier: Apache-2.0
"""BOSS「感兴趣」个人列表的接口抓取与解析（2026-11-09）。

与 boss_search 的分工：那边是"关键词+城市+筛选 → 搜索结果页 → 滚动加载"；
这里是"个人固定列表 → page 参数翻页"。两套翻页模型不同，所以独立成模块，
但**产出形状与 parse_search_response 完全一致**（同样的 ``SearchResult`` 字段），
下游（Collector）无感知。

接口事实（2026-11-09 实测，勿凭猜测改动）：
- GET /wapi/zprelation/interaction/geekGetJob?page=N&tag=4&isActive=true
- tag=4 是「感兴趣」（实测 134 条），tag=5 是「沟通过」（实测 85 条）——别搞混；
  确认方式：tag=4 返回的前三条岗位名与页面 DOM 里实际渲染的 ``.job-name`` 逐条一致。
- 每页固定 15 条（服务端写死，不是搜索页的 30）；翻页靠 page 参数；hasMore 为终止条件。
- 必须带 ``X-Requested-With: XMLHttpRequest``；cookie 由页面自动带。

为什么必须**在页面内 fetch**：BOSS 会关掉"由脚本新建并直接导航"的标签页（实测落到
about:blank），但在用户界面打开的页面里执行同源 fetch 完全正常。所以抓列表前要先让
适配器把当前标签页导航到「感兴趣」页（见 ``BossPageMixin.open_interest_page``），
再在这个页面里发请求——绝不能新建标签页。

与 boss_network 的失败语义**刻意相反**：那边"失败一律返回 None、退回 DOM 兜底"；
这里**必须显式抛 SiteFailure**——Collector 收到空 results 会当成"这页没岗位"继续翻页，
10 页翻完产出 0 条、任务却显示"完成"，用户无从知道接口已经挂了。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ...models.apply import FAILURE_SELECTOR_INVALID, FAILURE_UNKNOWN
from ..browser.cdp_client import CdpClient
from .base import SearchResult, SiteFailure
from .boss_network import _job_url, api_error
from .boss_page import _SELECTORS, BOSS_DISPLAY_NAME, _as_payload, _js
from .boss_text import normalize_text, split_title_salary

logger = logging.getLogger(__name__)

# 「感兴趣」列表页地址（站内导航用；fetch 走下面的接口，不经过这个地址）。
INTEREST_PATH = "/web/geek/recommend?tab=4&sub=1&page=1&tag=4"
# 上面地址的路径部分：open_interest_page 的就绪判据按 pathname 认页，不认完整查询串
# （SPA 可能增删查询参数，路径才是稳定特征）。
INTEREST_PAGE_PATH = "/web/geek/recommend"
INTEREST_ENDPOINT = "/wapi/zprelation/interaction/geekGetJob"
INTEREST_TAG = 4          # 实测：4=感兴趣、5=沟通过
INTEREST_PAGE_SIZE = 15   # 服务端固定，别当参数传

_MAX_TITLE_CHARS = 200
_MAX_ID_CHARS = 1000


def _text(value: Any, limit: int = _MAX_TITLE_CHARS) -> str:
    """取一段文本：先还原反爬混淆（水印/部首/私用区数字），再截断。"""
    return normalize_text(value)[:limit]


def _fetch_script(page: int) -> str:
    """在「感兴趣」页面里发一页列表请求的 JS（同源 fetch，cookie 由页面自动带）。

    返回 ``JSON.stringify`` 后的字符串：接口响应里混着长文本与二进制无关字段，
    按值拷贝整棵对象不如传一串 JSON 稳。外层 try/catch 把"响应不是 JSON"（多半是
    登录失效被重定向到了别的页面）也折算成业务错误码，让上层能给出可读诊断，
    而不是一条含糊的 CDP 执行错误。
    """
    return "".join(
        [
            "(async () => { /* rf:interest-page */\n",
            "  try {\n",
            f"    const r = await fetch('{INTEREST_ENDPOINT}?page={int(page)}"
            f"&tag={INTEREST_TAG}&isActive=true', {{\n",
            "      credentials: 'include',\n",
            "      headers: { 'X-Requested-With': 'XMLHttpRequest' },\n",
            "    });\n",
            "    const j = await r.json();\n",
            "    return JSON.stringify(j);\n",
            "  } catch (e) {\n",
            "    return JSON.stringify({ code: -1, message: 'fetch failed: ' + (e && e.message || e) });\n",
            "  }\n",
            "})()",
        ]
    )


def interest_ready_script() -> str:
    """「感兴趣」页就绪探针：URL 在个人推荐页上、且页面文本出现「感兴趣」。

    产出键名与 ``boss_page._readiness_script`` 对齐（``matched`` / ``captcha`` /
    ``login_required`` …），供 ``wait_for_page_state`` 与 ``detect_blocker`` 直接消费。
    刻意**不认卡片选择器**：该页的卡片类名与搜索页不同，认类名会在站点改版时把
    "页面还在"误判成"结构变化"。
    """
    return "".join(
        [
            "(() => { /* rf:interest-ready */\n",
            f"  const CAPTCHA = {_js(_SELECTORS['captcha'])};\n",
            f"  const LOGIN = {_js(_SELECTORS['login'])};\n",
            "  const shown = (sel) => [...document.querySelectorAll(sel)]\n",
            "    .some((node) => !!(node && node.getClientRects().length));\n",
            "  const body = (document.body && document.body.innerText) || '';\n",
            f"  const onPage = location.pathname.indexOf({_js(INTEREST_PAGE_PATH)}) >= 0;\n",
            "  return JSON.stringify({\n",
            "    url: location.href,\n",
            "    title: document.title || '',\n",
            "    ready_state: document.readyState || '',\n",
            "    matched: (onPage && body.indexOf('感兴趣') >= 0) ? 1 : 0,\n",
            "    explicitly_empty: false,\n",
            "    captcha: shown(CAPTCHA),\n",
            "    login_required: shown(LOGIN),\n",
            "  });\n",
            "})()",
        ]
    )


def interest_business_failure(code: str, message: str) -> SiteFailure:
    """把 geekGetJob 的业务错误码转成结构化失败；121（请求不合法）单独给可操作提示。"""
    if str(code) == "121":
        return SiteFailure(
            FAILURE_SELECTOR_INVALID,
            "BOSS「感兴趣」接口拒绝请求（code 121），可能页面未加载完成或站点改版；请稍后重试，"
            "若反复出现请把这条信息反馈给维护者",
        )
    return SiteFailure(FAILURE_UNKNOWN, f"BOSS 返回 {code}: {message}")


@dataclass
class InterestPage:
    """一页「感兴趣」列表的解析结果。

    ``invalid`` 是 ``jobValidStatus != 1`` 的条数（如实上报）：它解释了"页面显示 134 条、
    实际只采到 131 条"的差额，不报出来用户会以为丢了数据。
    """

    results: list[SearchResult] = field(default_factory=list)
    has_more: bool = False
    total_count: int = 0
    invalid: int = 0


def parse_interest_card(card: dict[str, Any]) -> SearchResult | None:
    """一张卡 → ``SearchResult``。

    返回 ``None`` 表示这条不可用（``jobValidStatus != 1``，或读不出岗位名/岗位 id）。
    字段映射与搜索侧同口径：岗位名过 ``split_title_salary``（新版列表岗位名与薪资可能
    粘在一个字段里），URL 用 ``_job_url``（卡里带 jobUrl 就用，否则按 encryptJobId 拼）。
    """
    if str(card.get("jobValidStatus") or "") != "1":
        # 实测：1 = 有效；0（或字段缺失）= 失效。失效岗位的详情页多半已下线，
        # 抓回来只会给暂存区堆垃圾，如实计入 invalid 让用户看到差额。
        return None
    job_id = _text(card.get("encryptJobId"), _MAX_ID_CHARS)
    title, title_salary = split_title_salary(card.get("jobName"))
    if not title or not job_id:
        return None
    city = _text(card.get("cityName"))
    district = _text(card.get("areaDistrict"))
    location = _text(card.get("unifyLocationDetail"), _MAX_ID_CHARS)
    if not location:
        location = "·".join(part for part in (city, district) if part)
    return SearchResult(
        title=title,
        company=_text(card.get("brandName")),
        location=location,
        salary=_text(card.get("salaryDesc")) or _text(card.get("jobSalary")) or title_salary,
        url=_job_url(card, job_id),
        source=BOSS_DISPLAY_NAME,
        extra={
            "encrypt_job_id": job_id,
            "security_id": _text(card.get("securityId"), _MAX_ID_CHARS),
            "experience": _text(card.get("jobExperience")),
            "degree": _text(card.get("jobDegree")),
            "city": city,
            "industry": _text(card.get("industryName")),
            "scale": _text(card.get("scaleName")),
            "hr_name": _text(card.get("bossName")),
            "hr_title": _text(card.get("bossTitle")),
        },
    )


def parse_interest_response(payload: Any) -> InterestPage:
    """geekGetJob 的响应 → :class:`InterestPage`；业务错误（``code != 0``）抛 SiteFailure。

    结构不认识（没有 ``zpData`` 容器 / 没有 ``cardList`` 列表）同样显式失败：这是
    "站点改版"的信号，静默当成空列表会把接口故障伪装成"你没感兴趣任何岗位"。
    """
    error = api_error(payload)
    if error is not None:
        raise interest_business_failure(*error)
    data = payload.get("zpData") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise SiteFailure(
            FAILURE_SELECTOR_INVALID,
            "BOSS「感兴趣」接口返回结构不认识（没有 zpData 容器），可能站点已改版；"
            "请把这条信息反馈给维护者",
        )
    cards = data.get("cardList")
    if not isinstance(cards, list):
        raise SiteFailure(
            FAILURE_SELECTOR_INVALID,
            "BOSS「感兴趣」接口返回结构不认识（没有 cardList 列表），可能站点已改版；"
            "请把这条信息反馈给维护者",
        )
    results: list[SearchResult] = []
    invalid = 0
    for card in cards:
        if not isinstance(card, dict):
            invalid += 1
            continue
        parsed = parse_interest_card(card)
        if parsed is None:
            invalid += 1
        else:
            results.append(parsed)
    raw_more = data.get("hasMore")
    try:
        total_count = int(data.get("totalCount") or 0)
    except (TypeError, ValueError):
        total_count = 0
    return InterestPage(
        results=results,
        has_more=raw_more is True or raw_more == 1,
        total_count=total_count,
        invalid=invalid,
    )


def fetch_interest_page(client: CdpClient, page: int) -> InterestPage:
    """在当前页面内 fetch 一页「感兴趣」，解析成 :class:`InterestPage`。

    为什么在页面内 fetch：BOSS 会关掉脚本新建导航的标签页（实测落 about:blank），
    而在已打开页面内 fetch 完全正常——调用方（``Collector._collect_interest``）负责
    先把页面导航到「感兴趣」页。

    两条防御（防御的对象都是"接口挂了却被当成没数据"）：

    1. 第一页 ``totalCount > 0`` 但一条卡都解析不出来（``cardList`` 空且没有失效卡）→
       显式失败。总数说有 N 条、列表却空的，唯一解释就是接口改版了；
    2. 业务错误码见 :func:`interest_business_failure`。
    """
    payload = _as_payload(client.evaluate(_fetch_script(page)))
    if not isinstance(payload, dict):
        raise SiteFailure(
            FAILURE_SELECTOR_INVALID,
            "「感兴趣」接口没有返回 JSON（当前页面可能不是 BOSS 页面或已跳转），请重试",
        )
    page_data = parse_interest_response(payload)
    if page == 1 and page_data.total_count > 0 and not page_data.results and not page_data.invalid:
        raise SiteFailure(
            FAILURE_SELECTOR_INVALID,
            f"BOSS 返回的「感兴趣」总数为 {page_data.total_count}，但列表一条都没解析出来，"
            "可能接口已改版；请把这条信息反馈给维护者",
        )
    return page_data


__all__ = [
    "INTEREST_ENDPOINT",
    "INTEREST_PAGE_PATH",
    "INTEREST_PAGE_SIZE",
    "INTEREST_PATH",
    "INTEREST_TAG",
    "InterestPage",
    "fetch_interest_page",
    "interest_business_failure",
    "interest_ready_script",
    "parse_interest_card",
    "parse_interest_response",
]
