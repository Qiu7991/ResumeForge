# SPDX-License-Identifier: Apache-2.0
"""公司名覆盖判定：只允许「更完整」替换「更不完整」。"""
from __future__ import annotations

from app.services.job_hunt.company_name import (
    is_truncated_company,
    looks_like_company_name,
    should_replace_company,
)


def test_truncated_detection():
    """BOSS 用 ASCII 三点截断（`广州市示例国际贸...`），不是省略号。"""
    assert is_truncated_company("广州市示例国际贸...") is True
    assert is_truncated_company("广州示例传媒科技有限公司") is False


def test_full_name_replaces_short_brand():
    """品牌短名 → 工商全称：这是主用例。"""
    assert should_replace_company("示例传媒", "广州示例传媒科技有限公司") is True


def test_truncated_name_always_replaced():
    """带截断标记的名字无条件替换——它本身就是残的。"""
    assert should_replace_company("广州市示例国际贸...", "海森国际") is True


def test_empty_current_always_replaced():
    assert should_replace_company("", "广州示例传媒科技有限公司") is True


def test_ui_noise_never_replaces():
    """回归：详情页解析可能命中导航菜单文本「公司」，绝不能拿它覆盖。

    实测踩过：裸 `a[href*="/gongsi/"]` 会命中顶部导航「公司」菜单。
    """
    assert should_replace_company("广州示例传媒科技有限公司", "公司") is False
    assert should_replace_company("示例传媒", "查看") is False


def test_shorter_name_never_replaces():
    """反向覆盖防护：更短的名字不能冲掉已有的全名。"""
    assert should_replace_company("广州示例传媒科技有限公司", "示例传媒") is False


def test_similar_job_company_does_not_replace():
    """回归：详情页「相似职位」卡片里的别的公司（广州另一家公司）不能覆盖本岗位公司。

    它长度可能更长，但当前名字已完整且更长时应拒绝——这条断言靠"更短即拒绝"生效，
    长度相同时也会拒绝（见 test_same_length_rejected）。
    """
    assert should_replace_company("广州示例传媒科技有限公司", "广州另一家公司") is False


def test_same_length_rejected():
    """长度相同时不替换：没有证据说明新的更好，不该乱动。"""
    assert should_replace_company("广州甲信息技术有限公司", "广州乙信息技术有限公司") is False


def test_identical_rejected():
    assert should_replace_company("广州示例传媒科技有限公司", "广州示例传媒科技有限公司") is False


def test_noise_detection():
    assert looks_like_company_name("公司") is False
    assert looks_like_company_name("") is False
    assert looks_like_company_name("示例传媒") is True
