# SPDX-License-Identifier: Apache-2.0
"""备选岗位评分输入的拼装规则（四条分支 + 判空一致性）。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.job_hunt.candidate_scoring import candidate_has_jd, candidate_jd


def _candidate(**fields) -> SimpleNamespace:
    """只带 JD 四列的假候选：这个模块不依赖 ORM 模型。"""
    base = {"description": "", "requirements": "", "additional_info": "", "raw_text": ""}
    return SimpleNamespace(**{**base, **fields})


def test_collected_candidate_joins_three_sections():
    """采集候选：服务端已切好三段，按「职责 → 要求 → 其他」拼起来。"""
    c = _candidate(
        description="负责 AI 应用开发。",
        requirements="本科以上。",
        additional_info="双休。",
    )
    assert candidate_jd(c) == "负责 AI 应用开发。\n\n本科以上。\n\n双休。"
    assert candidate_has_jd(c) is True


def test_manual_candidate_falls_back_to_raw_text():
    """手动粘贴的候选没有三段，只有 raw_text —— 它是唯一的正文来源。"""
    c = _candidate(raw_text="招聘：AI 工程师，负责模型落地。")
    assert candidate_jd(c) == "招聘：AI 工程师，负责模型落地。"
    assert candidate_has_jd(c) is True


def test_empty_sections_are_skipped_not_left_as_blank_lines():
    """空段要被跳过：留着空行会让提示词里出现连续空段落，白占 token。"""
    c = _candidate(description="职责 A。", additional_info="福利 B。")
    assert candidate_jd(c) == "职责 A。\n\n福利 B。"
    assert "\n\n\n" not in candidate_jd(c)


def test_whitespace_only_fields_count_as_missing():
    """只有空白字符的段落等于没有 —— 判空与拼接必须同源。"""
    c = _candidate(description="   \n\t ", requirements="")
    assert candidate_jd(c) == ""
    assert candidate_has_jd(c) is False


def test_has_jd_agrees_with_joined_text():
    """两条判据不能分叉：has_jd 为真时拼出来必须有内容，反之亦然。

    这是本模块最重要的不变量——判定说"有 JD"而拼出来是空串，评分会拿空正文去问
    模型，得到一个看似正常但没有依据的分数。
    """
    cases = [
        _candidate(),
        _candidate(description="x"),
        _candidate(raw_text="y"),
        _candidate(description="  "),
        _candidate(description="a", raw_text="b"),
    ]
    for c in cases:
        assert candidate_has_jd(c) is bool(candidate_jd(c))
