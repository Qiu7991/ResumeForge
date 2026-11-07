# SPDX-License-Identifier: Apache-2.0
"""BOSS直聘采集适配器（结构实证自 docs/job-hunt-fixtures/boss_list.html / boss_detail.html）。

列表页（Vue，每张卡包在 ``li.job-card-box`` 里）：
- 标题与链接：``<a class="job-name" href="/job_detail/{id}.html">标题</a>``
  —— **相对路径**，要补成 ``https://www.zhipin.com`` 绝对地址；
- 薪资：``<span class="job-salary">`` 内是**字体编码的乱码**（PUA 码点 U+E031..U+E03A），
  必须经 ``boss_font.decode_salary`` 还原；本适配器的 ``parse_list`` 只保留原文
  （``salary_raw``），解码在 ``parse_detail`` 里做——列表页拿不到字体文件，
  解码映射要靠详情页的明文对照或真实字体建立；
- 公司：``<span class="boss-name">``；地区：``<span class="company-location">``；
- 标签：``<ul class="tag-list"><li>1-3年</li><li>学历不限</li></ul>``。

详情页：
- 标题：``<h1 title="..">``；薪资：``<span class="salary">`` 这里是**明文**（如 ``8-12K``），
  可作列表页乱码的 ground-truth 对照；
- 公司：``.company-info`` 区（``a[href*="/gongsi/"]`` 或 ``.company-name``）；
- JD：``<div class="job-sec-text">`` 内是正文（``<br>`` 分条），末尾常有「（任职要求）」。

**为什么 BOSS 的列表解析要单独写**：``services/sites/boss_search.py`` 那套是给投递台
采集用的（带 CDP 点击与滚动、返回 SearchResult），接口不是 ``JobSiteAdapter``。
这里只做「HTML 文本 → JobStub」的纯解析，不碰浏览器。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from ..base import HuntCriteria, JobDetail, JobParseError, JobSiteAdapter, JobStub
from . import boss_font

_BASE = "https://www.zhipin.com"

# 一张卡 = 一个 li.job-card-box（整页 15 张，实测）。
# 注意：卡片内部还有嵌套的 <ul class="tag-list"><li>，所以不能用
# ``<li ...>...</li>`` 做正则（会被第一个内层 </li> 提前截断）。
# 改为按「卡片起点」切段：每张卡取到下一张卡起点为止。
_CARD_START_RE = re.compile(r'<li[^>]*class="job-card-box"[^>]*>')
_TITLE_LINK_RE = re.compile(
    r'<a[^>]*class="job-name"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
)
# 少数版本把 href 放在 class 之前。
_TITLE_LINK_RE_ALT = re.compile(
    r'<a[^>]*href="([^"]+)"[^>]*class="job-name"[^>]*>([^<]+)</a>'
)
_SALARY_RE = re.compile(r'<span[^>]*class="job-salary"[^>]*>(.*?)</span>', re.S)
_COMPANY_RE = re.compile(r'<span[^>]*class="boss-name"[^>]*>([^<]{1,60})</span>')
_LOCATION_RE = re.compile(r'<span[^>]*class="company-location"[^>]*>(.*?)</span>', re.S)
_TAGS_RE = re.compile(r'<ul[^>]*class="tag-list"[^>]*>(.*?)</ul>', re.S)
_TAG_ITEM_RE = re.compile(r"<li[^>]*>([^<]{1,20})</li>")

# 详情页
_D_TITLE_RE = re.compile(r'<h1[^>]*title="([^"]+)"')
_D_SALARY_RE = re.compile(r'<span[^>]*class="salary"[^>]*>\s*([^<]+?)\s*</span>')
_D_COMPANY_RE = re.compile(r'<a[^>]*href="[^"]*/gongsi/[^"]*"[^>]*>\s*([^<]{2,60}?)\s*</a>')
_D_COMPANY_FALLBACK_RE = re.compile(r'class="[^"]*company-name[^"]*"[^>]*>\s*([^<]{2,60}?)\s*<')
_D_SECTION_RE = re.compile(
    r'<div[^>]*class="job-sec-text"[^>]*>(.*?)</div>', re.S
)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")


def _clean(fragment: str) -> str:
    """把 HTML 片段折成纯文本：<br> 变换行，去标签，压空白。"""
    text = _BR_RE.sub("\n", fragment)
    text = _TAG_STRIP_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def _abs(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    if raw.startswith("/"):
        return _BASE + raw
    return f"{_BASE}/{raw}"


class BossAdapter(JobSiteAdapter):
    key = "boss"
    name = "BOSS直聘"

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        """``zhipin.com/web/geek/jobs?query=..&city=..&page=n``。

        ``city`` 支持两种写法：写城市名时按名称参数传（站点会重定向到对应 city 码），
        写纯数字时按 city 码直接传。真实翻页参数形态夜间未实测 → blocked.md。
        """
        params: list[str] = []
        kw = (criteria.keywords or "").strip()
        if kw:
            params.append(f"query={quote(kw)}")
        city = (criteria.city or "").strip()
        if city:
            if city.isdigit():
                params.append(f"city={city}")
            else:
                params.append(f"cityName={quote(city)}")
        if page and int(page) > 1:
            params.append(f"page={int(page)}")
        return f"{_BASE}/web/geek/jobs?" + "&".join(params)

    def parse_list(self, html: str) -> list[JobStub]:
        starts = list(_CARD_START_RE.finditer(html))
        if not starts:
            raise JobParseError(
                "页面里没有岗位卡片（li.job-card-box 缺失：可能未登录或被风控拦截）",
                site_key=self.key,
            )
        stubs: list[JobStub] = []
        for i, match in enumerate(starts):
            begin = match.end()
            end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
            card = html[begin:end]
            link_m = _TITLE_LINK_RE.search(card) or _TITLE_LINK_RE_ALT.search(card)
            if link_m is None:
                continue
            url, title = _abs(link_m.group(1)), _clean(link_m.group(2))
            if not title:
                continue
            salary_m = _SALARY_RE.search(card)
            company_m = _COMPANY_RE.search(card)
            loc_m = _LOCATION_RE.search(card)
            tags_m = _TAGS_RE.search(card)
            tags = _TAG_ITEM_RE.findall(tags_m.group(1)) if tags_m else []
            location = _clean(loc_m.group(1)) if loc_m else ""
            if not location and tags:
                # 标签里有时混着地区/经验，地区优先取含「·」的那条
                location = next((t for t in tags if "·" in t), "")
            stubs.append(
                JobStub(
                    title=title,
                    company=_clean(company_m.group(1)) if company_m else "",
                    location=location,
                    salary_raw=_clean(salary_m.group(1)) if salary_m else "",
                    url=url,
                )
            )
        if not stubs:
            raise JobParseError("岗位卡片存在但没有一张能解析出标题与链接", site_key=self.key)
        return stubs

    def parse_detail(self, html: str) -> JobDetail:
        title_m = _D_TITLE_RE.search(html)
        section_m = _D_SECTION_RE.search(html)
        if title_m is None and section_m is None:
            raise JobParseError(
                "详情页缺标题与 JD 正文（可能未登录、岗位已下线或结构改版）",
                site_key=self.key,
            )

        title = _clean(title_m.group(1)) if title_m else ""
        description = _clean(section_m.group(1)) if section_m else ""

        salary_m = _D_SALARY_RE.search(html)
        salary_text = _clean(salary_m.group(1)) if salary_m else ""

        company_m = _D_COMPANY_RE.search(html) or _D_COMPANY_FALLBACK_RE.search(html)
        company = _clean(company_m.group(1)) if company_m else ""

        # 详情页薪资是明文：能直接当 ground-truth，不需要字体解密。
        decoded_ok = bool(salary_text) and not boss_font.encoded_chars_in(salary_text)
        if not decoded_ok and salary_text:
            # 少数情况下详情页也给的是编码文本：这里没有字体映射，如实标记未还原。
            salary_text_out = salary_text
        else:
            salary_text_out = salary_text

        return JobDetail(
            title=title,
            company=company,
            location=_detail_location(html),
            salary_raw=salary_text,
            url="",
            description=description,
            requirements="",
            salary_decoded=salary_text_out,
            salary_decoded_ok=decoded_ok,
        )

    def supports(self, url: str) -> bool:
        return "zhipin.com" in (url or "")

    def max_pages(self) -> int:
        # BOSS 列表页实测一页 15 条；翻页上限按 10 页保守设。
        return 10


def _detail_location(html: str) -> str:
    """详情页地区：``.location``/``.job-area`` 一类的短文本。"""
    m = re.search(r'class="[^"]*(?:location|job-area|text-city)[^"]*"[^>]*>\s*([^<]{1,40}?)\s*<', html)
    return _clean(m.group(1)) if m else ""


__all__ = ["BossAdapter"]
