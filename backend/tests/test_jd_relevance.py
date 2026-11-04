# SPDX-License-Identifier: Apache-2.0
"""按 JD 给项目排序：最相关的项目必须排到「项目经历」最前面并标注。

回归的是一次真实事故：JD 要「大模型平台 + 具身智能」，招呼语却举了排在第一、
篇幅最长的「AIGC 短视频」——模型对"排在前面的内容"有强烈偏好，提示词里的挑选
规则拦不住。这里给一层确定性排序兜底。
"""

from __future__ import annotations

from app.services.job.jd_relevance import reorder_projects_by_relevance

BODY = """# 赵示例（求职意向：AI 产品经理）

## 教育经历
### 示例大学 · 计算机科学与技术

## 项目经历
### AIGC 短视频生产体系
- ComfyUI 工作流、关键帧、成片

### ESP-SparkBot AI 桌面机器人复刻
- ESP32-S3 桌面机器人，具身智能方向的硬件复刻

### 微信公众号民生消费类
- 内容运营，17 篇长文

## 专业技能
- Python
"""


def _first_project(text: str) -> str:
    """取「项目经历」板块下第一个 ``### `` 标题。"""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "项目经历" in line)
    return next(
        line.lstrip("# ").strip()
        for line in lines[start:]
        if line.strip().startswith("### ")
    )


def test_embodied_jd_puts_robot_project_first():
    """JD 提「具身智能 / 大模型平台」→ 机器人项目排第一。"""
    jd = {
        "title": "人工智能开发工程师",
        "description": "围绕公司自研的大模型平台及具身智能产品，进行行业应用开发",
        "requirements": "熟悉使用大模型工具平台解决问题，具备 Vibe coding 能力者优先",
    }
    out = reorder_projects_by_relevance(BODY, jd)
    assert _first_project(out) == "ESP-SparkBot AI 桌面机器人复刻"
    # 标注要写进文本，让模型看得见"该用哪个"
    assert "第 3 句应优先举这个项目" in out


def test_content_jd_puts_wechat_project_first():
    """同一个简历，换成内容运营 JD → 公众号项目排第一（不是固定的排序）。"""
    jd = {"title": "内容运营", "description": "公众号选题、爆款内容生产"}
    out = reorder_projects_by_relevance(BODY, jd)
    assert _first_project(out) == "微信公众号民生消费类"


def test_no_jd_leaves_order_untouched():
    """没有 JD 时原样返回——没有依据就不排序，避免每次顺序都不一样。"""
    assert reorder_projects_by_relevance(BODY, None) == BODY
    assert reorder_projects_by_relevance(BODY, {}) == BODY


def test_unmatched_jd_leaves_order_untouched():
    """JD 与所有项目都不沾边时也不排序（不凭空制造"最相关"）。"""
    jd = {"title": "财务审计", "description": "负责月度报表与税务申报"}
    assert reorder_projects_by_relevance(BODY, jd) == BODY


def test_other_sections_are_not_disturbed():
    """只重排「项目经历」，教育经历/专业技能保持原样。"""
    jd = {"title": "具身智能工程师", "description": "机器人/端侧 AI"}
    out = reorder_projects_by_relevance(BODY, jd)
    assert "示例大学 · 计算机科学与技术" in out
    assert "## 专业技能" in out
    # 教育经历仍在项目经历之前
    assert out.index("教育经历") < out.index("项目经历")
