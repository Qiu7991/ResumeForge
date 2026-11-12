# SPDX-License-Identifier: Apache-2.0
"""搜索筛选：中文标签 → BOSS 编码，以及按标签的本地二次筛选。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.job_hunt.search_filters import (
    filter_stub_by_tags,
    filter_options,
    resolve_search_filters,
)


def test_resolves_chinese_labels_to_codes():
    """界面给用户看中文，站点只认数字编码。"""
    result = resolve_search_filters(
        {"experience": ["应届生", "1-3年"], "degree": ["本科"], "jobType": ["全职"]}
    )

    assert result.params["experience"] == "102,104"
    assert result.params["degree"] == "203"
    assert result.params["jobType"] == "1901"
    assert result.unapplied == []


def test_unlimited_is_not_a_filter():
    """「不限」等于没筛：不该产生参数（站点收到 experience=0 语义不一样）。"""
    result = resolve_search_filters({"experience": ["不限"], "degree": ["学历不限"]})

    # 「不限」在快照里编码是 0 —— 它不进 params。
    assert "experience" not in result.params
    # 「学历不限」是真实编码 201 之前的语义项……快照里它是 (0, 不限) 形态之外的值，
    # 这里只断言「不限」这条不产生参数。
    assert result.unapplied  # 至少有一个没生效（如实上报，不静默）


def test_unknown_label_is_reported_not_dropped():
    """认不出的标签必须进 unapplied——静默丢弃会让用户以为筛了。"""
    result = resolve_search_filters({"experience": ["不存在的年限"]})

    assert "experience" not in result.params
    assert any("不存在的年限" in item for item in result.unapplied)


def test_filter_options_drop_unlimited():
    """下拉选项里不该出现「不限」——不清空就等于没选，界面上用清空表达。"""
    options = filter_options("degree")
    codes = [code for code, _ in options]

    assert "0" not in codes
    assert "203" in codes  # 本科


def test_local_filter_drops_mismatched_experience():
    """本地兜底：选了应届生，10 年经验的卡要被挡掉。

    站点侧筛选不严格（实测选「应届生」仍会看到「1-3年」），所以要有一道按标签的兜底。
    """
    senior = SimpleNamespace(experience="10年以上", education="本科")
    fresh = SimpleNamespace(experience="应届生", education="本科")

    selected = {"experience": ["应届生"]}
    assert filter_stub_by_tags(fresh, selected) is True
    assert filter_stub_by_tags(senior, selected) is False


def test_local_filter_passes_when_tag_missing():
    """标签读不到就放过——宁可多留一条，也不要静默少数据。"""
    unknown = SimpleNamespace(experience="", education="")

    assert filter_stub_by_tags(unknown, {"experience": ["应届生"], "degree": ["本科"]}) is True


def test_unlimited_experience_does_not_constrain():
    """选了「经验不限」就不该筛掉任何岗位。"""
    senior = SimpleNamespace(experience="10年以上", education="")

    assert filter_stub_by_tags(senior, {"experience": ["经验不限"]}) is True


def test_local_filter_keeps_education_unlimited_jobs():
    """「学历不限」的岗位对任何学历都开放，不该被学历筛选挡掉。"""
    job = SimpleNamespace(experience="", education="学历不限")

    assert filter_stub_by_tags(job, {"degree": ["本科"]}) is True
