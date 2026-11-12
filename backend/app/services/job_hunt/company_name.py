# SPDX-License-Identifier: Apache-2.0
"""公司名的清洗与「该不该用详情页的名字覆盖」判定。

## 为什么要这一层

同一家公司在两处会得到两个不同的名字：

- **列表页**：BOSS 给的品牌展示名（`示例传媒`）或 BOSS 自己截断的串（`广州市示例国际贸...`）
- **详情页「工商信息」**：工商全称（`广州示例传媒科技有限公司`）

采集先把列表名写进库，补抓详情时才有全名。这里判定**什么时候用详情名覆盖列表名**。

## 覆盖必须是单向的：只允许「更完整」替换「更不完整」

反向覆盖是这类修复最常见的错误——详细页解析偶尔会拿到导航菜单文本（`公司`）或
相似职位卡片里的别的公司（`广州另一家公司`）。如果无脑覆盖，那些脏值会把本来正确的
列表名冲掉，而且用户看不出是什么时候变坏的。

所以三条同时成立才覆盖：

1. 新名字非空、且不是明显的界面噪声（`公司` / `查看` / `更多` 这类）；
2. 新名字**比现有的长**（工商全称 > 品牌短名，这是唯一可靠的信号）；
3. 现有名字为空，或现有名字带截断标记（`...` / `…`）——**带截断标记时无条件替换**，
   因为截断名本身就是残的。
"""

from __future__ import annotations

import re

# 详情页里被误当成公司名的界面文本。都是导航/按钮，不是公司。
_UI_NOISE = frozenset(
    {
        "公司",
        "企业",
        "查看",
        "更多",
        "详情",
        "首页",
        "招聘",
        "工商信息",
        "公司名称",
    }
)

# 截断标记：BOSS 服务端截断时用 ASCII 三点；前端/某些场景用省略号。
_TRUNCATION_MARKS = ("...", "…")


def is_truncated_company(name: str) -> bool:
    """公司名是否被截断（尾部带 `...` / `…`）。

    界面上要据此给不同提示：截断名查风鸟也查不到，得先补抓详情。
    """
    return (name or "").strip().endswith(_TRUNCATION_MARKS)


def looks_like_company_name(name: str) -> bool:
    """这个名字是否像个正经公司名（够长、不是界面噪声）。"""
    clean = (name or "").strip()
    if not clean or clean in _UI_NOISE:
        return False
    # 中文公司名最短也在 2 字以上（`示例传媒`）；再短基本是解析错的碎片。
    return len(clean) >= 2 and not re.fullmatch(r"[\s\W]+", clean)


def should_replace_company(current: str, candidate: str) -> bool:
    """详情页解析出的 ``candidate`` 是否应当覆盖库里已有的 ``current``。

    规则见模块 docstring：只允许「更完整」替换「更不完整」。
    """
    existing = (current or "").strip()
    incoming = (candidate or "").strip()

    if not looks_like_company_name(incoming):
        return False
    if existing == incoming:
        return False
    # 现有名字是空的或被截断 → 替代它只会更好。
    if not existing or is_truncated_company(existing):
        return True
    # 否则只在新名字更长时替换（工商全称 vs 品牌短名的唯一可靠区分）。
    return len(incoming) > len(existing)


__all__ = [
    "is_truncated_company",
    "looks_like_company_name",
    "should_replace_company",
]
