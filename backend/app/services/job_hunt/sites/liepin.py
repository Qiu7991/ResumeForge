# SPDX-License-Identifier: Apache-2.0
"""猎聘采集适配器（结构实证自 docs/job-hunt-fixtures/liepin_*.html）。

列表页（Vue，CSS 类名带随机后缀）每张卡：
- 标题节点 ``<div class="ellipsis-1" title="..">内部文本</div>`` 是**卡片锚点**
  （40 张卡全量可定位）；**岗位链接在标题节点之前**（卡片整体包在
  ``<a href="https://www.liepin.com/job/{id}.shtml?...">`` 里），所以链接要向
  前一张标题的方向回看；
- 薪资明文（``15-20k·13薪``）、公司在 ``class`` 含 cname/company 的节点、地区在
  ``【..】`` 括号内、发布时间形如 ``9小时前在线``。

详情页：主薪资是 ``<span class="salary">``（相似岗位才是 ``job-salary``，别抓错）；
完整 JD 在 ``<dd data-selector="job-intro-content">``，职责/要求混排（用
"任职要求"分节）；公司名取自 meta keywords 的最后一段。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from ..base import HuntCriteria, JobDetail, JobParseError, JobSiteAdapter, JobStub

_TITLE_NODE_RE = re.compile(r'<div class="ellipsis-1" title="[^"]*">([^<]+)</div>')
# 岗位链接：猎聘详情 URL（卡片开头的 <a>，带一堆跟踪参数——只取主路径）。
_JOB_LINK_RE = re.compile(r'href="(https://www\.liepin\.com/job/\d+\.shtml)')
# 薪资：优先形状（防 CSS 类名改版），回退已知的混淆类名。
_SALARY_SHAPE_RE = re.compile(r">(\d{1,3}(?:\.\d)?-\d{1,3}(?:\.\d)?[kK](?:·\d{1,2}薪)?)<")
_SALARY_CLASS_RE = re.compile(r'class="_40108qjbMk[^"]*"[^>]*>([^<]+)<')
_COMPANY_RE = re.compile(r'class="[^"]*(?:cname|company|firm)[^"]*"[^>]*>([^<]{2,40})<')
_AREA_RE = re.compile(r"【</span><span[^>]*>([^<]+)</span>")
_POSTED_RE = re.compile(r">(\d+[^\s<>]{0,6}前在线)<")
SEARCH_URL = "https://www.liepin.com/zhaopin/"


def _first(re_match_result) -> str:
    for g in re_match_result.groups() if re_match_result else ():
        if g:
            return g.strip()
    return ""


class LiepinAdapter(JobSiteAdapter):
    key = "liepin"
    name = "猎聘"

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        """``liepin.com/zhaopin/?key=..``（夹具 canonical 实证的搜索基路径）。

        翻页参数形态夜间未实测 → blocked.md LIEPIN-URL-UNVERIFIED。
        """
        params: list[str] = []
        kw = (criteria.keywords or "").strip()
        if kw:
            params.append(f"key={quote(kw)}")
        city = (criteria.city or "").strip()
        if city:
            params.append(f"dq={quote(city)}")
        params.append(f"curPage={max(int(page) - 1, 0)}")
        return SEARCH_URL + "?" + "&".join(params)

    def parse_list(self, html: str) -> list[JobStub]:
        titles = list(_TITLE_NODE_RE.finditer(html))
        if not titles:
            raise JobParseError(
                "页面里没有岗位标题节点（ellipsis-1 缺失：可能未登录或结构改版）",
                site_key=self.key,
            )
        stubs: list[JobStub] = []
        for i, match in enumerate(titles):
            start = match.start()
            end = titles[i + 1].start() if i + 1 < len(titles) else len(html)
            card = html[start:end]
            # 链接在卡片开头 <a>（标题节点之前）：回看上一张标题之后的区间
            backward_from = titles[i - 1].end() if i > 0 else 0
            link_m = _JOB_LINK_RE.search(html[backward_from:start])
            salary_m = _SALARY_SHAPE_RE.search(card) or _SALARY_CLASS_RE.search(card)
            title = match.group(1).strip()
            if not title or link_m is None:
                continue  # 没有链接/标题的残片不采
            stubs.append(
                JobStub(
                    title=title,
                    company=_first(_COMPANY_RE.search(card)),
                    location=_first(_AREA_RE.search(card)),
                    salary_raw=(salary_m.group(1).strip() if salary_m else ""),
                    url=link_m.group(1),
                    posted_at=_first(_POSTED_RE.search(card)),
                )
            )
        if not stubs:
            raise JobParseError("岗位卡片都解析不出有效字段（结构改版）", site_key=self.key)
        return stubs

    def parse_detail(self, html: str) -> JobDetail:
        title_m = re.search(r'class="job-title[^"]*"[^>]*>([^<]{2,60})<', html)
        salary_m = re.search(r'<span class="salary">([^<]{1,30})</span>', html)
        area_m = re.search(r'class="job-properties">.*?<span>([^<]{2,20})</span>', html, re.S)
        intro_m = re.search(r'data-selector="job-intro-content">(.*?)</dd>', html, re.S)
        if not (title_m and salary_m and intro_m):
            raise JobParseError(
                "详情页缺主标题/主薪资/职位介绍容器（结构改版）", site_key=self.key
            )
        description = _text_of(intro_m.group(1))
        requirements = ""
        for marker in ("任职要求：", "任职资格：", "任职要求:", "职位要求："):
            if marker in description:
                head, _, tail = description.partition(marker)
                description, requirements = head.rstrip(), tail.strip()
                break
        return JobDetail(
            title=title_m.group(1).strip(),
            company=self._company_of(html),
            location=area_m.group(1).strip() if area_m else "",
            salary_raw=salary_m.group(1).strip(),
            salary_decoded=salary_m.group(1).strip(),  # 猎聘薪资是明文
            salary_decoded_ok=True,
            description=description,
            requirements=requirements,
        )

    def supports(self, url: str) -> bool:
        return "liepin.com" in (url or "").lower()

    @staticmethod
    def _company_of(html: str) -> str:
        """公司名：meta keywords 最后一段（"…,公司名招聘"）→ 去掉尾缀"招聘"。"""
        kw = re.search(r'<meta name="keywords" content="([^"]+)"', html)
        if kw and "," in kw.group(1):
            last = kw.group(1).split(",")[-1].strip()
            if last.endswith("招聘"):
                return last[: -len("招聘")].strip()
        return ""


def _text_of(fragment: str) -> str:
    """HTML 片段 → 纯文本：去标签、还原实体、压平空白（保留换行结构）。"""
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    )
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
