# SPDX-License-Identifier: Apache-2.0
"""智联适配器测试：全部吃本地夹具（E17），缺夹具 skip（E18）。

断言字段值来自对夹具的人工核对（见 docs/job-hunt-progress.md J4 节的实证记录），
不是"跑一遍解析再抄结果"。
"""
from __future__ import annotations

import pytest

from app.services.job_hunt.base import HuntCriteria
from app.services.job_hunt.registry import get_registry
from app.services.job_hunt.runner import JobHuntRunner
from app.services.job_hunt.sites.zhilian import ZhilianAdapter
from job_hunt_fixtures import has, load

pytestmark = pytest.mark.skipif(not has("zhilian_list.html"), reason="缺智联列表夹具")


@pytest.fixture()
def adapter() -> ZhilianAdapter:
    return ZhilianAdapter()


def test_registered_in_default_registry():
    assert get_registry().resolve("zhilian") is not None


def test_build_search_url_basic(adapter):
    url = adapter.build_search_url(HuntCriteria(keywords="AI"), page=2)
    assert url == "https://sou.zhaopin.com/?kw=AI&p=2"


def test_build_search_url_city_code_and_quoting(adapter):
    url = adapter.build_search_url(
        HuntCriteria(keywords="AI 产品", extra={"city_code": "763"}), page=1)
    # 关键词 URL 编码、城市编码进 jl、页码从 1 起
    assert url.startswith("https://sou.zhaopin.com/?kw=AI%20")
    assert "jl=763" in url and url.endswith("p=1")


def test_parse_list_records(adapter):
    stubs = adapter.parse_list(load("zhilian_list.html"))
    # 夹具 positionList 实测 20 条
    assert len(stubs) == 20
    first = stubs[0]
    # 人工核对过的第一条记录（创意设计主管）
    assert first.title.startswith("创意设计主管")
    assert first.company == "美赞臣营养品(中国)有限公司"
    assert first.salary_raw == "1.2-1.5万·15薪"
    assert first.url == "https://www.zhaopin.com/jobdetail/CC136143370J40979639315.htm"
    assert first.posted_at == "2026-11-06 17:45:17"
    assert "广州" in first.location
    # 全部记录都有可去重的绝对链接与标题
    assert all(s.url.startswith("https://") for s in stubs)
    assert all(s.title for s in stubs)


def test_parse_list_structure_change_raises(adapter):
    with pytest.raises(Exception) as ei:
        adapter.parse_list("<html>没有数据</html>")
    assert "positionList" in str(ei.value)


def test_parse_detail(adapter):
    pytest.importorskip("json")
    detail = adapter.parse_detail(load("zhilian_detail.html"))
    assert detail.title == "java研发实习生"
    assert detail.salary_raw == "80-120元/天"
    assert detail.salary_decoded == "80-120元/天" and detail.salary_decoded_ok
    assert detail.location == "黄埔区"
    assert "岗位职责" in detail.description
    assert "LlamaIndex" in detail.description  # JD 尾部内容也完整
    assert isinstance(detail.company, str)


def test_supports(adapter):
    assert adapter.supports("https://www.zhaopin.com/jobdetail/X.htm")
    assert adapter.supports("https://sou.zhaopin.com/?kw=AI")
    assert not adapter.supports("https://www.zhipin.com/job_detail/X.html")


def test_runner_integration_first_page(adapter):
    """runner + 真夹具：第 1 页采完、第 2 页合法空结果 → 20 条 + no_results。"""
    pages = {1: load("zhilian_list.html"), 2: '{"positionList":[]}'}

    def fetch(url: str) -> str:
        page = int(url.rsplit("p=", 1)[1])
        return pages.get(page, pages[2])

    report = JobHuntRunner(adapter, max_pages=3).run({"keywords": "AI"}, fetch=fetch)
    assert len(report.stubs) == 20
    assert report.stopped_reason == "no_results"
    assert report.duplicates == 0


def test_parse_list_missing_marker_is_drift_not_empty(adapter):
    """marker 缺失（登录失效/改版）必须抛错，与合法空结果区分开。"""
    from app.services.job_hunt.base import JobParseError

    with pytest.raises(JobParseError):
        adapter.parse_list("<html>登录失效</html>")
