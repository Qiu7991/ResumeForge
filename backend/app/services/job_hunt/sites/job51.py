# SPDX-License-Identifier: Apache-2.0
"""前程无忧（51job）采集适配器——**只做列表**（详情需登录，见 blocked.md）。

结构实证自 docs/job-hunt-fixtures/job51_list.html（Vue SSR 页）：
- 每张卡有 ``sensorsname="JobShortExposure" sensorsdata="{...}"``（HTML 转义的 JSON），
  含 ``jobId / jobTitle / jobSalary / jobArea / jobYear / jobDegree / companyId /
  jobTime(发布时间)``——20/20 全量可解析；
- 卡片**没有岗位链接**（Vue 点击导航），唯一 <a> 是右侧 ``class="comp"`` 的**公司**链接
  （同公司多卡共用）；岗位 URL 只能由 jobId 构造（数字形态，未实测——见 blocked.md
  JOB51-URL-UNVERIFIED）；
- 公司名在右侧 ``<span title="..." class="cname text-cut">`` 的 title 属性里（20/20）。
"""
from __future__ import annotations

import html as html_lib
import json
import re
from urllib.parse import quote

from ..base import HuntCriteria, JobDetail, JobParseError, JobSiteAdapter, JobStub

_CARD_MARKER = 'sensorsname="JobShortExposure"'
_CNAME_RE = re.compile(
    r'title="([^"]{2,40})"[^>]*class="cname|class="cname[^"]*"[^>]*title="([^"]+)"'
)
SEARCH_URL = "https://we.51job.com/pc/search"

#: 数字 jobId 拼 URL 的公开历史形态；当前站内链接用的是另一套混淆码（夜间无法验证
#: 数字形态是否仍解析），晨间首跑人工确认后修订。
_JOB_URL_TPL = "https://jobs.51job.com/all/{job_id}.html"


def _card_slices(html: str) -> list[str]:
    starts = [m.start() for m in re.finditer(re.escape(_CARD_MARKER), html)]
    if not starts:
        return []
    return [html[s:e] for s, e in zip(starts, [*starts[1:], len(html)])]


class Job51Adapter(JobSiteAdapter):
    key = "job51"
    name = "前程无忧"

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        params: list[str] = []
        kw = (criteria.keywords or "").strip()
        if kw:
            params.append(f"keyword={quote(kw)}")
        area = str((criteria.extra or {}).get("job_area_code") or "").strip()
        if area:
            params.append(f"jobArea={quote(area)}")
        params.append("searchType=2")
        params.append(f"pageNo={max(int(page), 1)}")
        return f"{SEARCH_URL}?{'&'.join(params)}"

    def parse_list(self, html: str) -> list[JobStub]:
        cards = _card_slices(html)
        if not cards:
            raise JobParseError(
                "页面里没有岗位卡片（JobShortExposure 标记缺失：可能未登录或结构改版）",
                site_key=self.key,
            )
        stubs: list[JobStub] = []
        for card in cards:
            data = self._card_data(card)
            if data is None:
                continue  # 单卡解析失败不拖垮整页
            job_id, fields = data
            company_m = _CNAME_RE.search(card)
            company = (company_m.group(1) or company_m.group(2) if company_m else "") or ""
            stubs.append(
                JobStub(
                    title=str(fields.get("jobTitle") or "").strip(),
                    company=company.strip(),
                    location=str(fields.get("jobArea") or "").strip(),
                    salary_raw=str(fields.get("jobSalary") or "").strip(),
                    url=_JOB_URL_TPL.format(job_id=job_id),
                    posted_at=str(fields.get("jobTime") or "").strip(),
                )
            )
        if not stubs:
            raise JobParseError("岗位卡片都解析不出有效字段（结构改版）", site_key=self.key)
        return stubs

    def parse_detail(self, html: str) -> JobDetail:
        raise JobParseError(
            "51job 岗位详情需登录后才有正文（当前只有列表能力）；"
            "待人工补抓 docs/job-hunt-fixtures/job51_detail.html 后实现（BLOCKED-FIXTURE-JOB51）",
            site_key=self.key,
        )

    def supports(self, url: str) -> bool:
        return "51job.com" in (url or "").lower()

    @staticmethod
    def _card_data(card: str) -> tuple[str, dict] | None:
        m = re.search(r'sensorsdata="([^"]+)"', card)
        if not m:
            return None
        try:
            data = json.loads(html_lib.unescape(m.group(1)))
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        job_id = str(data.get("jobId") or "").strip()
        if not job_id or not str(data.get("jobTitle") or "").strip():
            return None
        return job_id, data
