# SPDX-License-Identifier: Apache-2.0
"""智联招聘采集适配器（结构实证自 docs/job-hunt-fixtures/zhilian_*.html）。

数据形态（实测）：
- 列表页：SSR JSON（``__INITIAL_STATE__``）里 ``"positionList":[...]``，每条富对象带
  ``name / companyName / cityDistrict / cardCustomJson(字符串化 JSON，含 address) /
  salary60 / positionURL / publishTime``，甚至自带 ``jobDescription``；
- 详情页：``__INITIAL_STATE__`` 里 ``"jobDetail"."detailedPosition"``，``description``
  是完整 JD（职责+要求混排，\\n 分段），``salary`` 明文（如 "80-120元/天"）。

搜索 URL（``sou.zhaopin.com``）的 ``kw``/``jl``/``p`` 是公开查询参数形态，但**夜间无
登录态未实测**（智联把关键词的路径编码做成私有，参考实现因此宁走页面内提交）；真实验证
留给晨间人工首跑，见 docs/job-hunt-blocked.md ZHILIAN-URL-UNVERIFIED。
"""
from __future__ import annotations

import json
from urllib.parse import quote

from ..base import HuntCriteria, JobDetail, JobParseError, JobSiteAdapter, JobStub

_LIST_MARKER = '"positionList":'
_DETAIL_MARKER = '"detailedPosition":'

#: 详情页 URL 模板（列表记录缺 positionURL 但有 number 时兜底）。
_DETAIL_URL_TPL = "https://www.zhaopin.com/jobdetail/{number}.htm"
SEARCH_URL = "https://sou.zhaopin.com/"


def _extract_balanced(text: str, start: int, *, open_ch: str, close_ch: str) -> str:
    """从 ``start``（指向 open_ch）起做字符串感知的括号配对提取。

    SSR JSON 里嵌着大量「字符串化的 JSON」（cardCustomJson 等），朴素按括号数会
    被字符串里的 ``]`` / ``}`` 骗走——必须跳过引号与转义。
    """
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    raise ValueError(f"括号不配对（起点 {start}）")


def _json_after(text: str, marker: str, *, open_ch: str, close_ch: str) -> object:
    """定位 marker，提取其后第一个平衡的 JSON 值并解析。"""
    i = text.find(marker)
    if i < 0:
        raise JobParseError(f"页面里找不到 {marker}（可能未登录或结构改版）", site_key="zhilian")
    start = text.find(open_ch, i + len(marker))
    if start < 0:
        raise JobParseError(f"{marker} 后没有 {open_ch}（结构改版）", site_key="zhilian")
    try:
        blob = _extract_balanced(text, start, open_ch=open_ch, close_ch=close_ch)
        return json.loads(blob)
    except JobParseError:
        raise
    except (ValueError, json.JSONDecodeError) as exc:
        raise JobParseError(f"岗位数据解析失败：{exc}", site_key="zhilian") from exc


def _location_of(record: dict) -> str:
    """地点：优先 cardCustomJson.address（"广州 天河 冼村"），退化 cityDistrict。"""
    raw = record.get("cardCustomJson")
    if isinstance(raw, str) and raw:
        try:
            custom = json.loads(raw)
        except json.JSONDecodeError:
            custom = None
        if isinstance(custom, dict):
            address = str(custom.get("address") or "").strip()
            if address:
                return address
    return str(record.get("cityDistrict") or "").strip()


class ZhilianAdapter(JobSiteAdapter):
    key = "zhilian"
    name = "智联招聘"

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        """拼智联搜索 URL：``sou.zhaopin.com/?kw=..&p=..``（城市编码可选）。

        城市走 ``criteria.extra['city_code']``（智联城市编码，如广州 763——实测自夹具
        positionList 记录的 ``cityId``）；没给编码就不带 ``jl``，只按关键词搜。
        """
        params: list[str] = []
        kw = (criteria.keywords or "").strip()
        if kw:
            params.append(f"kw={quote(kw)}")
        code = str((criteria.extra or {}).get("city_code") or "").strip()
        if code:
            params.append(f"jl={quote(code)}")
        params.append(f"p={max(int(page), 1)}")
        return SEARCH_URL + "?" + "&".join(params)

    def supports(self, url: str) -> bool:
        return "zhaopin.com" in (url or "").lower()

    def parse_list(self, html: str) -> list[JobStub]:
        records = _json_after(html, _LIST_MARKER, open_ch="[", close_ch="]")
        if not isinstance(records, list):
            raise JobParseError("positionList 不是数组（结构改版）", site_key=self.key)
        if not records:
            # 合法的"无结果"页（翻过头/条件太窄）：返回空列表让 runner 走 no_results；
            # marker 缺失才是结构漂移，在上面的 _json_after 里已经抛了。
            return []
        stubs: list[JobStub] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            title = str(record.get("name") or "").strip()
            if not title:
                continue
            url = str(record.get("positionURL") or record.get("positionUrl") or "").strip()
            if not url:
                number = str(record.get("number") or "").strip()
                if number:
                    url = _DETAIL_URL_TPL.format(number=number)
            stubs.append(
                JobStub(
                    title=title,
                    company=str(record.get("companyName") or "").strip(),
                    location=_location_of(record),
                    salary_raw=str(record.get("salary60") or record.get("salary")
                                   or record.get("salaryReal") or "").strip(),
                    url=url,
                    posted_at=str(record.get("publishTime") or "").strip(),
                )
            )
        if not stubs:
            raise JobParseError("positionList 里没有可识别的岗位（结构改版）", site_key=self.key)
        return stubs

    def parse_detail(self, html: str) -> JobDetail:
        record = _json_after(html, _DETAIL_MARKER, open_ch="{", close_ch="}")
        if not isinstance(record, dict):
            raise JobParseError("detailedPosition 不是对象（结构改版）", site_key=self.key)
        title = str(record.get("positionName") or "").strip()
        if not title:
            raise JobParseError("详情记录没有 positionName（结构改版）", site_key=self.key)
        salary_raw = str(record.get("salary") or record.get("salary60")
                         or record.get("salaryReal") or "").strip()
        return JobDetail(
            title=title,
            company=str(record.get("companyName") or "").strip(),
            location=str(record.get("cityDistrict") or "").strip(),
            salary_raw=salary_raw,
            # 智联薪资是明文，无字体混淆
            salary_decoded=salary_raw,
            salary_decoded_ok=True,
            url=str(record.get("positionURL") or record.get("positionUrl") or "").strip(),
            description=str(record.get("description") or "").strip(),
            requirements="",  # 智联 JD 职责/要求混排在同一段文本里
            posted_at=str(record.get("publishTime") or "").strip(),
        )
