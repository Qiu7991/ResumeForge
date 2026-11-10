# SPDX-License-Identifier: Apache-2.0
"""岗位判重的名称口径：同公司下，两个标题算不算同一个职位（2026-11-10）。

## 为什么需要它

岗位广场的判重原本只看两件事：**同一个投递链接**，或**同一公司 + 标题一字不差**。
这漏掉了真实发生的情况——用户在 BOSS 上投递过某个职位，HR 后来把同一个职位
**重新发布**，于是换了新的 encryptJobId（链接不同），标题也带了一点修饰差异：

    旧：AI 应用运营（AI 提示词 / 智能对话方向）
    新：AI应用运营（AI提示词/智能对话）双休

对系统这是两条记录，对用户这就是同一个岗位。

## 判据（只有两条，故意简单）

1. **公司名**归一化后必须完全相同（不做任何模糊）；
2. **标题**归一化后：完全相等，或一方包含另一方（被包含那方 ≥ ``_MIN_CONTAIN_LEN`` 字）。

归一化只做"显然不影响语义"的收敛：
- 全角转半角、转小写（`AI` 与 `ａｉ` 是同一个词）
- 去空白、标点、分隔符（`AI 应用运营` 与 `AI应用运营`）
- 去掉**末尾**的招聘修饰：`双休` / `急招` / `15-25K·14薪` 这类

**括号内容保留**：`AI产品专员（互动小说）` 与 `AI产品专员（AIGC应用方向）` 是
两个不同岗位，去掉括号就会把它们并成一个。括号里的字常常正是区分点。

## 为什么不用相似度算法

试过字符二元组 Dice 系数（阈值 0.8），结论是**不如包含判断**：
- 真该命中的那一对（上面新旧两条），归一化后恰好是"前者是后者的前缀"，包含判断直接命中；
- 相似度反而会误判：`AI Agent工程师` 与 `AI agent开发工程师` 字面很像，
  但它们是猎头转发的**两个不同雇主**的岗位。

少一层算法，就少一层"为什么这条被判成重复"的解释成本。
"""

from __future__ import annotations

import re
import unicodedata

#: 一方包含另一方时，被包含方至少要这么长才算同一个职位。
#: 太短会误判：同公司的「后端」与「后端开发」——后者包含前者，但后者可能真的多一层职责。
_MIN_CONTAIN_LEN = 6

#: 末尾薪资段：`15-25K·14薪` / `8-12K`。列表标题里薪资常被粘在职位名后面，
#: 它不是职位名的一部分。**必须在去标点之前剥**——否则 `15-25K·14薪` 会先被收成
#: `1525k14薪`，就再也认不出来了。
_TRAILING_SALARY_RE = re.compile(
    r"[\s·・]*\d+(?:\.\d+)?\s*[-~—]\s*\d+(?:\.\d+)?\s*[kK千万元]?(?:\s*[·・]\s*\d+\s*薪)?\s*$"
)
#: 末尾的 `14薪` / `13薪起`。
_TRAILING_MONTHS_RE = re.compile(r"[\s·・]*\d+\s*薪.*$")

#: 其它常见招聘修饰，出现在标题末尾时与职位无关。长的在前，避免被短的截断。
_TRAILING_NOISE = ("五险一金", "六险一金", "包吃住", "包吃", "包住", "双休", "急招", "急聘", "高薪", "直招")

#: 归一化时丢掉的字符：空白、分隔符、标点。
_DROP_RE = re.compile(r"[\s\u3000/／·・\-—_|\\+.,，。:：;；!！?？\"'“”‘’()（）【】\[\]]+")

#: 「公司名」实为占位符的那些——它们不指代具体公司，不能拿来当"同公司"依据。
#: 实测：猎头批量发的岗位公司名统一是「猎头代招（雇主未公开）」，
#: 于是「AI Agent工程师」与「AI agent开发工程师」会被判成同一个职位——
#: 而它们来自 liepin 的两个不同职位、不同雇主。
_PLACEHOLDER_COMPANIES = (
    "猎头代招",
    "雇主未公开",
    "雇主保密",
    "未公开",
    "保密企业",
    "某大型企业",
    "某知名企业",
)


def normalize_company(name: str) -> str:
    """公司名归一化：全半角、大小写、空白与标点。**不做**任何相似处理。

    公司名误判的代价比标题更大（会把不同子公司的岗位并成一条），所以这里只认
    "看起来就是同一家"。
    """
    text = unicodedata.normalize("NFKC", str(name or "")).casefold()
    return _DROP_RE.sub("", text)


def is_placeholder_company(normalized_company: str) -> bool:
    """公司名是不是"谁都可能是"的占位符（猎头、匿名雇主等）。"""
    if not normalized_company:
        return True
    return any(marker in normalized_company for marker in _PLACEHOLDER_COMPANIES)


def normalize_title(title: str) -> str:
    """标题归一化：去末尾薪资/招聘修饰，再做全半角、大小写、空白与标点收敛。

    **不碰括号内容**（见模块说明）。
    """
    text = unicodedata.normalize("NFKC", str(title or "")).casefold()
    text = _TRAILING_SALARY_RE.sub("", text)
    text = _TRAILING_MONTHS_RE.sub("", text)
    text = text.strip()
    for noise in _TRAILING_NOISE:
        if text.endswith(noise):
            text = text[: -len(noise)].strip()
            break
    return _DROP_RE.sub("", text)


def same_posting(left_title: str, right_title: str) -> bool:
    """两个标题是否可能是同一个职位（调用方负责先确认公司相同）。

    只有两种命中方式：归一化后完全相等，或一方包含另一方（被包含方够长）。
    """
    a, b = normalize_title(left_title), normalize_title(right_title)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= _MIN_CONTAIN_LEN and shorter in longer


__all__ = [
    "is_placeholder_company",
    "normalize_company",
    "normalize_title",
    "same_posting",
]
