# SPDX-License-Identifier: Apache-2.0
"""BOSS 适配器测试：列表 + 详情都有夹具（E17），缺夹具 skip（E18）。

除了结构解析，这里还锁住两条**实测得出的关键行为**：
1. 列表薪资是字体编码乱码（PUA 码点），parse_list 只保留原文，不做无依据的猜测；
2. 详情页薪资是明文，可作为列表乱码的 ground-truth；
   用「列表第一条 + 详情明文」对照建映射后，应能如实还原出 ``8-12K``。
"""
from __future__ import annotations

import pytest

from app.services.job_hunt.base import HuntCriteria, JobParseError
from app.services.job_hunt.registry import get_registry
from app.services.job_hunt.sites import boss_font
from app.services.job_hunt.sites.boss import BossAdapter
from job_hunt_fixtures import has, load

pytestmark = pytest.mark.skipif(
    not (has("boss_list.html") and has("boss_detail.html")), reason="缺 BOSS 夹具"
)


@pytest.fixture()
def adapter() -> BossAdapter:
    return BossAdapter()


# ---------- 注册与 URL ----------


def test_registered(adapter):
    got = get_registry().resolve("boss")
    assert got is not None and got.key == "boss"


def test_supports(adapter):
    assert adapter.supports("https://www.zhipin.com/job_detail/abc.html")
    assert not adapter.supports("https://www.liepin.com/job/1.shtml")


def test_build_search_url(adapter):
    url = adapter.build_search_url(HuntCriteria(keywords="AI"), page=1)
    assert url == "https://www.zhipin.com/web/geek/jobs?query=AI"
    # 数字城市码直接当 city 传
    url = adapter.build_search_url(HuntCriteria(keywords="AI", city="101280100"), page=1)
    assert "city=101280100" in url
    # 城市名走 cityName
    url = adapter.build_search_url(HuntCriteria(keywords="AI", city="广州"), page=1)
    assert "cityName=%E5%B9%BF%E5%B7%9E" in url
    # 第 2 页起带 page
    assert "page=2" in adapter.build_search_url(HuntCriteria(keywords="AI"), page=2)


# ---------- 列表解析 ----------


def test_parse_list_count_and_fields(adapter):
    stubs = adapter.parse_list(load("boss_list.html"))
    assert len(stubs) >= 10, "夹具里应有 15 张卡"

    first = stubs[0]
    assert first.title == "AI人工智能技术员（服装方向）"
    assert first.company == "依卡瑞"
    assert first.location.startswith("广州")
    assert first.url.startswith("https://www.zhipin.com/job_detail/")
    # 薪资必须是字体编码原文，不能被「猜」成数字
    assert boss_font.encoded_chars_in(first.salary_raw), "列表薪资应是编码乱码"


def test_parse_list_all_have_core_fields(adapter):
    stubs = adapter.parse_list(load("boss_list.html"))
    for s in stubs:
        assert s.title, "标题不能为空"
        assert s.company, f"{s.title} 缺公司"
        assert s.url.startswith("http"), f"{s.title} 链接未补成绝对地址"


def test_parse_list_raises_on_empty_page(adapter):
    with pytest.raises(JobParseError):
        adapter.parse_list("<html><body>登录后查看</body></html>")


def test_card_split_not_broken_by_nested_li(adapter):
    """回归：卡片内有 <ul class="tag-list"><li>，按 </li> 切会提前截断。

    早期实现用 ``<li ...>(.*?)</li>`` 做卡片正则，导致公司/地区全空。
    这里锁住「至少 10 条卡都带公司」来防回归。
    """
    stubs = adapter.parse_list(load("boss_list.html"))
    with_company = [s for s in stubs if s.company]
    assert len(with_company) >= 10


# ---------- 详情解析 ----------


def test_parse_detail_plaintext_salary(adapter):
    d = adapter.parse_detail(load("boss_detail.html"))
    assert d.title == "AI人工智能技术员（服装方向）"
    assert d.salary_decoded == "8-12K"
    assert d.salary_decoded_ok is True, "详情页薪资是明文，应标记为已还原"
    assert len(d.description) > 200, "JD 正文应有实质内容"


def test_parse_detail_raises_on_blank(adapter):
    with pytest.raises(JobParseError):
        adapter.parse_detail("<html><body>职位不存在</body></html>")


# ---------- 字体解密端到端（列表乱码 → 详情明文对照）----------


def test_decode_list_salary_via_detail_ground_truth(adapter):
    """最有价值的一条：用真实夹具证明「乱码可被明文还原」。

    列表第一条与详情页是同一岗位：
      列表 ``\\ue039-\\ue032\\ue033K`` + 详情明文 ``8-12K``
    → 建映射后解码应逐字还原成 ``8-12K``。
    """
    stubs = adapter.parse_list(load("boss_list.html"))
    detail = adapter.parse_detail(load("boss_detail.html"))
    assert stubs[0].title == detail.title, "夹具应指向同一岗位"

    mapping = boss_font.mapping_from_pairs([(stubs[0].salary_raw, detail.salary_decoded)])
    assert mapping, "明文对照应能建出映射"

    result = boss_font.decode_salary(stubs[0].salary_raw, mapping)
    assert result.text == "8-12K"
    assert result.ok is True


def test_decode_refuses_to_guess_unknown_symbols(adapter):
    """未知符号必须原样保留且 ok=False——不许把没依据的数字编出来。"""
    stubs = adapter.parse_list(load("boss_list.html"))
    detail = adapter.parse_detail(load("boss_detail.html"))
    mapping = boss_font.mapping_from_pairs([(stubs[0].salary_raw, detail.salary_decoded)])

    # 第 2 条含未映射符号
    second = stubs[1]
    result = boss_font.decode_salary(second.salary_raw, mapping)
    if boss_font.encoded_chars_in(result.text):
        assert result.ok is False, "仍有未解码字符时必须标记 ok=False"


# ---------- 内容就绪选择器（实测踩坑的回归锁）----------


def test_content_ready_selector_declared(adapter):
    """列表页内容就绪判据必须声明。

    实测：BOSS 搜索页 ``readyState=complete`` 时 Vue 列表尚未渲染，
    直接取 outerHTML 会拿到空壳（0 张卡）。通用层靠这个选择器等内容出现。
    """
    selector = adapter.content_ready_selector()
    assert selector == "li.job-card-box"
    # 该选择器必须真的能在夹具里命中，否则等待毫无意义
    html = load("boss_list.html")
    assert html.count("job-card-box") >= 10


# ---------- 完整字体映射（2026-11-08 实证收敛）----------


def test_default_mapping_covers_all_ten_symbols():
    """BOSS 现行字体的 10 个 PUA 符号必须都有确定映射。"""
    mapping = boss_font.default_mapping()
    assert len(mapping) == 10
    assert set(mapping.values()) == set("0123456789")


def test_default_mapping_decodes_all_cards():
    """用固定映射解真实夹具里的全部卡片，必须 15/15 成功。

    这是「映射正确」的端到端锁：任何一位搞错，都会出现「下限 > 上限」
    或解码不完整（ok=False）。
    """
    adapter = BossAdapter()
    stubs = adapter.parse_list(load("boss_list.html"))
    assert len(stubs) >= 10
    for s in stubs:
        assert s.salary_decoded_ok is True, f"{s.title} 未完整解码：{s.salary_raw}"
        assert boss_font.encoded_chars_in(s.salary_decoded) == set()


def test_default_mapping_ranges_are_sane():
    """区间型薪资必须满足「下限 < 上限」——映射错一位就会违反。"""
    import re

    adapter = BossAdapter()
    stubs = adapter.parse_list(load("boss_list.html"))
    rng = re.compile(r"(\d+)\s*-\s*(\d+)")
    checked = 0
    for s in stubs:
        m = rng.search(s.salary_decoded)
        if not m:
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        assert lo < hi, f"{s.title} 薪资区间倒挂：{s.salary_decoded}"
        checked += 1
    assert checked >= 10, f"应至少校验 10 条区间薪资，实际 {checked}"
