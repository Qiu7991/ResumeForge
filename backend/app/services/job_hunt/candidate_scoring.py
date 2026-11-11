# SPDX-License-Identifier: Apache-2.0
"""备选岗位（candidate_job）的评分输入拼装。

为什么要单独一层：备选岗位的 JD 散在四列里，而正式岗位只有一个 ``Job.description``。
评分提示词只认一段「JD 正文」，所以必须有一处**唯一**的拼装规则——采集候选有
``description``/``requirements``/``additional_info`` 三段（服务端已按小标题切好），
手动粘贴的候选只有 ``raw_text``。两处各拼一次，模型看到的输入就会分叉。

判「有没有 JD」与拼 JD 必须同源：如果 ``has_jd`` 说"有"而拼出来是空串，评分会拿
空正文去问模型，得到一个看起来正常但没有依据的分数——比直接报「缺 JD」更糟。
"""

from __future__ import annotations

from typing import Any

# 拼接顺序即重要性：职责 → 要求 → 其他信息。``raw_text`` 放最后当兜底，
# 只在前面三段全空时用（手动粘贴的候选走这条）。
_SECTION_ATTRS = ("description", "requirements", "additional_info", "raw_text")


def _section(candidate: Any, name: str) -> str:
    value = getattr(candidate, name, "") or ""
    return str(value).strip()


def candidate_jd(candidate: Any) -> str:
    """把备选岗位的 JD 四列拼成评分用的正文（空段跳过，段间空一行）。"""
    parts = [text for text in (_section(candidate, name) for name in _SECTION_ATTRS) if text]
    return "\n\n".join(parts)


def candidate_has_jd(candidate: Any) -> bool:
    """是否有可评分的正文。

    与 :func:`candidate_jd` 同源：直接判拼接结果非空，避免"判定说有、拼出来是空"。
    """
    return bool(candidate_jd(candidate))


__all__ = ["candidate_has_jd", "candidate_jd"]
