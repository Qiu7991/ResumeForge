# SPDX-License-Identifier: Apache-2.0
"""前程无忧（51job）适配器测试——只测列表（详情无夹具，见 blocked.md）。"""
from __future__ import annotations

import pytest

from app.services.job_hunt.base import HuntCriteria, JobParseError
from app.services.job_hunt.registry import get_registry
from app.services.job_hunt.sites.job51 import Job51Adapter
from job_hunt_fixtures import has, load

pytestmark = pytest.mark.skipif(not has("job51_list.html"), reason="缺 51job 列表夹具")


@pytest.fixture()
def adapter() -> Job51Adapter:
    return Job51Adapter()


def test_registered(adapter):
    got = get_registry().resolve("job51")
    assert got is not None and got.key == "job51"


def test_build_search_url(adapter):
    assert adapter.build_search_url(HuntCriteria(keywords="AI"), page=2) == \
        "https://we.51job.com/pc/search?keyword=AI&searchType=2&pageNo=2"
    url = adapter.build_search_url(
        HuntCriteria(keywords="AI", extra={"job_area_code": "030800"}), page=1)
    assert "jobArea=030800" in url and url.endswith("pageNo=1")


def test_parse_list_records(adapter):
    stubs = adapter.parse_list(load("job51_list.html"))
    assert len(stubs) == 20  # 夹具实测 20 张卡
    first = stubs[0]
    # 人工核对过的第一条（sensorsdata + cname span）
    assert first.title == "AI视觉大客户代表（SOP作业检测）"
    assert first.company == "广东能哥知识科技有限公司"
    assert first.salary_raw == "1-1.5万"
    assert first.location == "广州·番禺区"
    assert first.posted_at == "2026-11-06 19:13:35"
    assert first.url == "https://jobs.51job.com/all/174153043.html"
    # 全部记录可去重
    assert all(s.title and s.url for s in stubs)


def test_parse_list_same_company_cards(adapter):
    """前 3 张卡是同公司不同岗位：公司名各自提取、URL 按 jobId 区分。"""
    stubs = adapter.parse_list(load("job51_list.html"))
    assert stubs[0].company == stubs[1].company == stubs[2].company
    assert len({s.url for s in stubs[:3]}) == 3


def test_parse_detail_is_blocked(adapter):
    """详情无夹具：必须显式抛错（BLOCKED-FIXTURE-JOB51），不许假装能解析。"""
    with pytest.raises(JobParseError, match="51job"):
        adapter.parse_detail(load("job51_list.html"))


def test_supports(adapter):
    assert adapter.supports("https://jobs.51job.com/all/x.html")
    assert adapter.supports("https://we.51job.com/pc/search?keyword=AI")
    assert not adapter.supports("https://www.zhaopin.com/jobdetail/x.htm")
