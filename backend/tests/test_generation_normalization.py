# SPDX-License-Identifier: Apache-2.0
"""生成内容归一化（R1-A/R1-B/R1-E）：去重保序、剥离 markdown 前缀、自建字段落 item。

这些是真实 AI 生成返工里发现的产品缺陷（v2_check 证据）：
- 同一句被 description/highlights 两个槽位写进正文 → 纸面重复；
- 资料行本身带 "- " 前缀 → 渲染成「· - xxx」双项目符号；
- 自建板块 multi_line 字段没有 primary_field_id 时被当成主文本 TextItem，丢掉 label/source。
"""

from __future__ import annotations

from app.schemas.resume import ResumeContent
from app.schemas.resume_custom_sections import (
    ResumeCustomEntry,
    ResumeCustomLine,
    ResumeCustomSection,
)
from app.services.resume.document_io import ensure_document_version
from app.services.resume.generation_postprocess import (
    normalize_generated_content,
    strip_markdown_prefix,
)


def test_strip_markdown_prefix_covers_common_markers():
    assert strip_markdown_prefix("- 主导活动策划") == "主导活动策划"
    assert strip_markdown_prefix("* 负责渠道对接") == "负责渠道对接"
    assert strip_markdown_prefix("• 参与复盘") == "参与复盘"
    assert strip_markdown_prefix("1. 第一步") == "第一步"
    assert strip_markdown_prefix("2、第二步") == "第二步"
    # 数字 + 单位不是列表前缀（「3 天」必须原样保留）。
    assert strip_markdown_prefix("3 天完成 40 家邀约") == "3 天完成 40 家邀约"
    assert strip_markdown_prefix("普通正文") == "普通正文"


def test_normalize_generated_content_strips_prefix_and_dedupes_cross_slots():
    resume = ResumeContent(
        summary="- 三年市场经验\n- 主导增长项目",
        projects=[
            {
                "name": "校园招聘会策划",
                "description": ["- 从 0 到 1 策划校园招聘会", "用分时段数据调度入场节奏"],
                "highlights": ["用分时段数据调度入场节奏", "设计一页纸招募说明"],
            }
        ],
        custom_sections=[
            ResumeCustomSection(
                key="custom:abc12345",
                title="开源贡献",
                entries=[
                    ResumeCustomEntry(
                        entry_id="entry00001",
                        text="- 维护内部组件库",
                        lines=[ResumeCustomLine(label="仓库", value="- https://example.com/repo")],
                    )
                ],
            )
        ],
    )

    normalized = normalize_generated_content(resume)

    project = normalized.projects[0]
    # 跨槽位重复只保留首次出现；两段内容都还在。
    assert project.description == [
        "从 0 到 1 策划校园招聘会",
        "用分时段数据调度入场节奏",
        "设计一页纸招募说明",
    ]
    assert project.highlights == []
    assert normalized.summary == "三年市场经验\n主导增长项目"
    custom = normalized.custom_sections[0].entries[0]
    assert custom.text == "维护内部组件库"
    assert custom.lines[0].value == "https://example.com/repo"


def test_normalize_generated_content_dedupes_skills_by_rank_and_keeps_order():
    """问题 14：同一技能被补两次只留一条，等级取高的一条，顺序按首次出现。"""
    resume = ResumeContent(
        skills=[
            {"name": "MySQL", "level": "掌握"},
            {"name": "Spring Boot", "level": "熟练"},
            {"name": "MySQL ", "level": "熟练"},  # 空白差别的同一条，等级更高
            {"name": "Redis", "level": ""},
            {"name": "mysql", "level": "了解"},  # 大小写不同，等级更低 → 不得降档
        ]
    )

    normalized = normalize_generated_content(resume)

    assert [(skill.name, skill.level) for skill in normalized.skills] == [
        ("MySQL ", "熟练"),
        ("Spring Boot", "熟练"),
        ("Redis", ""),
    ]


def test_skill_dedupe_does_not_touch_distinct_skills():
    """去重不能误删不同技能（数据岗 13 条那种体量不能被压成几条）。"""
    names = ["SQL", "MySQL", "PostgreSQL", "Python", "Pandas", "Spark", "Hive"]
    resume = ResumeContent(skills=[{"name": name, "level": "掌握"} for name in names])

    normalized = normalize_generated_content(resume)

    assert [skill.name for skill in normalized.skills] == names


def test_custom_section_multi_line_field_converts_to_field_item_with_source():
    section_key = "custom:abc12345"
    resume = ResumeContent(
        custom_sections=[
            ResumeCustomSection(
                key=section_key,
                title="作品集",
                entries=[
                    ResumeCustomEntry(
                        entry_id="entry00001",
                        text="",
                        lines=[
                            ResumeCustomLine(label="作品说明", value="一页纸招募说明的设计与复盘"),
                        ],
                    )
                ],
            )
        ]
    )
    hints = {
        section_key: [
            {
                "section_key": section_key,
                "field_id": "fld0000000000001",
                "label": "作品说明",
                "field_type": "multi_line",
                "default_placement": "body",
                "material_only": False,
            }
        ]
    }
    document = ensure_document_version(resume.model_dump(), custom_fields=hints)
    section = next(item for item in document["sections"] if item["key"] == section_key)
    item = section["entries"][0]["items"][0]
    assert item["kind"] == "field"
    assert item["key"] == "custom:fld0000000000001"
    assert item["label"] == "作品说明"
    assert item["placement"] == "body"
    assert item["source"] == {"section_key": section_key, "field_id": "fld0000000000001"}


def test_near_duplicate_bullets_are_merged_but_distinct_ones_are_kept():
    """同一句话被录了两遍（「我定…」/「本人定…」）要并成一条，但两份真成果不能合。

    2026-11-10 实测：资料里同一个项目存了两版写法，亮点被并进来后纸面上同一个项目
    把同一件事写了两行；另一边「10,429 行固件、9 类异常…」与「7 类传感器、3 类执行器…」
    是两条不同的成果，相似度只有 0.67，必须都留下。
    """
    long_a = (
        "主体代码由 Codex / ZCode 生成、我定契约与验收：把需求拆成可验收的小步"
        "（先 schema 再实现再测试），AI 产出后逐段 review，用测试兜底。"
    )
    long_b = (
        "主体代码由 Codex / ZCode 生成、本人定契约与验收：需求拆成可验收的小步"
        "（先 schema 再实现再测试），AI 产出后逐段 review，用测试兜底。"
    )
    fact_a = "10,429 行固件、9 类异常判定、7 类传感器、3 类执行器、1 个微信小程序（3 页）"
    fact_b = "7 类传感器、3 类执行器、9 类异常判定、1 个微信小程序（3 页）"

    resume = ResumeContent(
        projects=[
            {
                "name": "示例项目",
                "role": "个人项目",
                "description": [long_a, long_b, fact_a, fact_b],
            }
        ]
    )

    cleaned = normalize_generated_content(resume).projects[0].description

    assert cleaned == [long_a, fact_a, fact_b]


def test_near_duplicate_merge_keeps_short_distinct_bullets():
    """短要点不参与近似比对：两句话都短时相似度噪音大，宁可都留着。"""
    resume = ResumeContent(
        experience=[
            {
                "company": "示例公司",
                "role": "实习",
                "description": ["负责设备维护", "负责设备巡检"],
            }
        ]
    )

    cleaned = normalize_generated_content(resume).experience[0].description

    assert cleaned == ["负责设备维护", "负责设备巡检"]
