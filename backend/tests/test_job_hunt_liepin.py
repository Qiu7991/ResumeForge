# SPDX-License-Identifier: Apache-2.0
"""猎聘适配器测试：列表 + 详情都有夹具（E17），缺夹具 skip（E18）。"""
from __future__ import annotations

import pytest

from app.services.job_hunt.base import HuntCriteria
from app.services.job_hunt.registry import get_registry
from app.services.job_hunt.sites.liepin import LiepinAdapter
from job_hunt_fixtures import has, load

pytestmark = pytest.mark.skipif(
    not (has("liepin_list.html") and has("liepin_detail.html")), reason="缺猎聘夹具"
)


@pytest.fixture()
def adapter() -> LiepinAdapter:
    return LiepinAdapter()


def test_registered(adapter):
    got = get_registry().resolve("liepin")
    assert got is not None and got.key == "liepin"


def test_build_search_url(adapter):
    url = adapter.build_search_url(HuntCriteria(keywords="AI"), page=1)
    assert url == "https://www.liepin.com/zhaopin/?key=AI&curPage=0"
    url = adapter.build_search_url(HuntCriteria(keywords="AI", city="广州"), page=3)
    assert "dq=%E5%B9%BF%E5%B7%9E" in url and url.endswith("curPage=2")


def test_parse_list_records(adapter):
    stubs = adapter.parse_list(load("liepin_list.html"))
    assert len(stubs) == 40  # 夹具实测 40 张卡全量可解析
    first = stubs[0]
    assert first.title == "AI技术产品化经理"  # 内部文本不带"招聘"前缀
    assert first.company == "力鸿检验集团有限公司"
    assert first.salary_raw == "15-20k·13薪"
    assert first.location == "北京-顺义区"
    assert first.url.startswith("https://www.liepin.com/job/")
    assert first.url.endswith(".shtml")
    assert first.posted_at == "9小时前在线"
    # 40 条链接唯一、全部绝对
    assert len({s.url for s in stubs}) == 40


def test_parse_list_structure_change_raises(adapter):
    with pytest.raises(Exception) as ei:
        adapter.parse_list("<html>登录失效</html>")
    assert "ellipsis-1" in str(ei.value)


def test_parse_detail(adapter):
    detail = adapter.parse_detail(load("liepin_detail.html"))
    assert detail.title == "AI技术产品化经理"
    # 主薪资是 <span class="salary">（不是相似岗位的 job-salary）
    assert detail.salary_raw == "15-20k·13薪"
    assert detail.salary_decoded == "15-20k·13薪" and detail.salary_decoded_ok
    assert detail.location == "北京-顺义区"
    assert detail.company == "力鸿检验集团有限公司"
    # JD：职责/要求按「任职要求：」分节
    assert "岗位职责" in detail.description
    assert "LangChain/LlamaIndex" in detail.description
    assert detail.requirements.startswith("1.")
    assert "Python" in detail.requirements


def test_supports(adapter):
    assert adapter.supports("https://www.liepin.com/job/123.shtml")
    assert not adapter.supports("https://www.zhaopin.com/jobdetail/x.htm")


def test_text_of_preserves_lines():
    from app.services.job_hunt.sites.liepin import _text_of

    assert _text_of("<p>一</p><br/><p>二</p>") == "一\n二"
    assert _text_of("a&amp;b") == "a&b"
