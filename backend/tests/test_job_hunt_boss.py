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
    # 路径是 **单数** /web/geek/job：写成 jobs 站点不报错但返回的不是搜索结果，
    # 那种"看起来成功"的错最难查（见 build_search_url 的 docstring）。
    assert url == "https://www.zhipin.com/web/geek/job?query=AI"
    # 数字城市码直接当 city 传
    url = adapter.build_search_url(HuntCriteria(keywords="AI", city="101280100"), page=1)
    assert "city=101280100" in url
    # 城市名走 cityName
    url = adapter.build_search_url(HuntCriteria(keywords="AI", city="广州"), page=1)
    assert "cityName=%E5%B9%BF%E5%B7%9E" in url
    # 第 2 页起带 page
    assert "page=2" in adapter.build_search_url(HuntCriteria(keywords="AI"), page=2)


def test_build_search_url_matches_reference_shape(adapter):
    """与 BossHunter 的实测 URL 逐字符一致。

    参考形态（``collection/platforms/boss.py:563-567`` 按真实地址还原）::

        /web/geek/job?query=ai%E5%BA%94%E7%94%A8&city=101280100
        &jobType=1901&experience=102%2C103%2C104&degree=203&sortType=2&page=2

    四个容易拼错的点都在这一条里：路径单数、参数名 query、多值用 %2C 连接、
    sortType=2 在 page 之前。
    """
    criteria = HuntCriteria(
        keywords="ai应用",
        city="101280100",
        extra={
            "filters": {"jobType": "1901", "experience": "102,103,104", "degree": "203"},
            "sort": "newest",
        },
    )
    assert adapter.build_search_url(criteria, page=2) == (
        "https://www.zhipin.com/web/geek/job?query=ai%E5%BA%94%E7%94%A8&city=101280100"
        "&jobType=1901&experience=102%2C103%2C104&degree=203&sortType=2&page=2"
    )


def test_sort_only_when_newest(adapter):
    """默认排序下**完全不出现** sortType 参数，不是 sortType=0。"""
    plain = adapter.build_search_url(HuntCriteria(keywords="AI"), page=1)
    assert "sortType" not in plain
    # 显式 newest 才加
    newest = adapter.build_search_url(
        HuntCriteria(keywords="AI", extra={"sort": "newest"}), page=1
    )
    assert newest.endswith("&sortType=2")


def test_filter_order_is_fixed(adapter):
    """筛选参数按固定顺序拼（便于逐字符比对与排查）。

    站点对顺序不敏感，但顺序固定 = URL 可断言；乱序时这条测试会红，而不是靠人肉看。
    """
    criteria = HuntCriteria(
        keywords="AI",
        city="101280100",
        extra={"filters": {"salary": "405", "degree": "203", "jobType": "1901"}},
    )
    url = adapter.build_search_url(criteria, page=1)
    # jobType 在 degree 前、degree 在 salary 前（_FILTER_PARAM_ORDER 的顺序）
    assert url.index("jobType=") < url.index("degree=") < url.index("salary=")


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


def test_parse_detail_keeps_nested_div_content(adapter):
    """正文里的嵌套 div 不能被截断。

    回归（2026-11-11）：闭合位置原本用非贪婪 ``(.*?)</div>`` 找，遇到第一个内层
    ``</div>`` 就收尾。实测 266 号岗位的 JD 只剩 70 字——正好截在第一个内层 div
    之前（"工作内容：1、利用AI编程工具…"）。真实页面里 JD 带分组小标题/折叠块是常态，
    所以这不是理论边界。
    """
    html = (
        '<div class="job-sec-text">'
        "工作内容："
        '<div class="group-a">1、做A</div>'
        "<div>2、做B</div>"
        "3、做C"
        "</div>"
        "<div>容器之后的兄弟节点，不能吞进来</div>"
    )
    d = adapter.parse_detail(html)

    assert "1、做A" in d.description
    assert "2、做B" in d.description, "内层 div 之后的内容被截断了"
    assert "3、做C" in d.description, "容器收尾的内容被截断了"
    assert "兄弟节点" not in d.description, "只应取本容器内部，不能吞掉后面的同级节点"


def test_parse_detail_unbalanced_html_keeps_what_it_has(adapter):
    """页面被截断（闭合标签缺失）时要给能取到的那部分，而不是整条丢弃。"""
    html = '<div class="job-sec-text">岗位职责：1、负责A；2、负责B'
    d = adapter.parse_detail(html)

    assert "负责A" in d.description
    assert "负责B" in d.description


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


def test_parse_detail_normalizes_kangxi_radicals(adapter):
    """康熙部首要折回普通汉字。

    回归（2026-11-11）：BOSS 正文里混着 U+2F00–U+2FDF 的部首字形（⽤/⼈/⼯/⼒），
    与普通汉字（用/人/工/力）码位不同、字形几乎一致。不清掉的话关键词匹配与
    岗位评分会漏掉这些字——「有良好的能⼒」搜「能力」搜不到。
    """
    html = (
        '<div class="job-sec-text">'
        "1.具备良好的沟通能⼒与协作能⼒；"
        "2.⽤户⼈群分析，⼯作主动；"
        "</div>"
    )
    d = adapter.parse_detail(html)

    assert "能力" in d.description, "能⼒ 必须折成 能力"
    assert "用户" in d.description
    assert "人群" in d.description
    assert "工作" in d.description
    # 部首本身不该再出现
    for radical in ("⽤", "⼈", "⼯", "⼒"):
        assert radical not in d.description


def test_parse_detail_strips_watermarks(adapter):
    """BOSS 的水印会被插进词中间，必须清掉。

    实测（2026-11-11）：177 条采集里有 24 条 JD 带水印，形态是插在词中间的
    「岗kanzhun位职责」「来自BOSS直聘实现基于LLM…」「岗BOSS直聘位职责」。
    不清掉的话正文读起来就是断句，检索与评分都会受影响。
    """
    html = (
        '<div class="job-sec-text">'
        "岗kanzhun位职责:\n"
        "1、来自BOSS直聘实现基于LLM的智能体架构;\n"
        "2、岗BOSS直聘位相关的维护工作。"
        "</div>"
    )
    d = adapter.parse_detail(html)

    for token in ("kanzhun", "BOSS直聘", "boss"):
        assert token not in d.description, f"水印 {token} 没被清掉"
    assert "岗位职责" in d.description, "去掉水印后词要能接上"
    assert "实现基于LLM" in d.description


def test_list_salary_keeps_private_use_digits(adapter):
    """列表薪资必须保留 PUA 原文——否则字体解密失去输入。

    这条是回归：正文清理统一改用 normalize_text 后，它会把 PUA 数字折成普通数字，
    列表薪资就变成 "9-23K"，`encoded_chars_in()` 认不出密文，父子对照建不出映射。
    所以薪资走单独的 _clean_salary。
    """
    stubs = adapter.parse_list(load("boss_list.html"))
    assert boss_font.encoded_chars_in(stubs[0].salary_raw), (
        "列表 salary_raw 必须是 PUA 密文原文，不能已被折算"
    )
