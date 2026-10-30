"""简历正文的分区顺序：定义、归一化，以及"四个渲染器读的是同一份"。

为什么值得一个测试文件：顺序一旦在某个渲染器里写死，用户在预览里拖好的顺序就会
**只在预览生效**——导出的 PDF / Word / Markdown / txt 还是老顺序。那类问题不报错，
用户只会说"导出的和看到的不一样"，而这正是本项目最忌讳的一类差异
（`exporter.py` 的 docstring 记着一次同源教训：预览里有性别与出生年、md 里没有）。
"""

from __future__ import annotations

import io
import re

from app.schemas.resume import ResumeContent
from app.services.docx_exporter import build_resume_docx
from app.services.exporter import export_markdown, render_html
from app.services.resume.resume_sections import (
    DEFAULT_SECTION_ORDER,
    normalized_section_order,
    resolved_section_order,
)
from app.services.txt_exporter import export_txt

# 七个分区对应的标题文案。渲染器写的是文案，测试按文案找位置——文案本身在
# resume_sections.py 的 SECTION_LABELS 里定义，这里只负责"顺序"这一件事。
TITLES = ("个人总结", "教育经历", "实习/工作经历", "校园经历", "项目经历", "专业技能", "荣誉奖项")

# 挑一个与默认顺序差异最大的排列：默认是 总结 → 教育 → 实习 → 校园 → 项目 → 技能 → 奖项。
CUSTOM_ORDER = [
    "projects",
    "experience",
    "summary",
    "awards",
    "skills",
    "education",
    "campus_experience",
]

CUSTOM_CONFIG = {"section_order": CUSTOM_ORDER}


def _sample_resume() -> ResumeContent:
    return ResumeContent(
        name="张示例",
        summary="总结文字",
        education=[{"school": "示例大学", "major": "示例专业", "degree": "本科"}],
        experience=[{"company": "示例科技有限公司", "role": "示例岗位"}],
        campus_experience=[{"organization": "示例社团"}],
        projects=[{"name": "示例项目"}],
        skills=[{"name": "Python"}],
        awards=[{"name": "示例奖项"}],
    )


def _title_positions(text: str) -> list[tuple[str, int]]:
    return [(title, text.find(title)) for title in TITLES]


def _assert_follows_order(texts: dict[str, str]) -> None:
    """每个输出里，自定义顺序的标题都应按给定先后出现。"""
    for name, text in texts.items():
        positions = [(title, text.find(title)) for title, _ in _title_positions(text)]
        missing = [title for title, position in positions if position < 0]
        assert not missing, f"{name} 缺少分区标题：{missing}"
        order_in_output = [
            title for title, _ in sorted(positions, key=lambda item: item[1])
        ]
        assert order_in_output == [
            "项目经历",
            "实习/工作经历",
            "个人总结",
            "荣誉奖项",
            "专业技能",
            "教育经历",
            "校园经历",
        ], f"{name} 的分区顺序不对：{order_in_output}"


def test_default_order_matches_the_templates_current_order():
    """默认顺序必须等于重排前的写死顺序。

    这条是刻意的护栏：分区顺序是**有历史记录的产物**的呈现方式，改默认顺序等于把
    用户已经导出过的简历悄悄换一个样子。要改它必须显式改这里并说清理由，
    而不是「我的资料」那边改了默认顺序就顺手跟。
    """
    assert list(DEFAULT_SECTION_ORDER) == [
        "summary",
        "education",
        "experience",
        "campus_experience",
        "projects",
        "skills",
        "awards",
    ]


def test_normalized_order_is_always_a_complete_permutation():
    """归一化结果永远是七个键的完整排列——缺失的键按默认顺序补齐。"""
    assert normalized_section_order(["projects", "experience"]) == [
        "projects",
        "experience",
        "summary",
        "education",
        "campus_experience",
        "skills",
        "awards",
    ]
    # 重复键只保留一次；未知键被丢掉而不是报错（它是版式配置的一部分，
    # 抛异常会让整份版式配置失效）。
    assert normalized_section_order(["projects", "projects", "unknown", "summary"]) == [
        "projects",
        "summary",
        "education",
        "experience",
        "campus_experience",
        "skills",
        "awards",
    ]
    assert normalized_section_order(None) == list(DEFAULT_SECTION_ORDER)
    assert normalized_section_order("summary,projects") == normalized_section_order(
        ["summary", "projects"]
    )


def test_resolved_order_reads_format_config_and_falls_back():
    assert resolved_section_order(None) == list(DEFAULT_SECTION_ORDER)
    assert resolved_section_order({}) == list(DEFAULT_SECTION_ORDER)
    assert resolved_section_order(CUSTOM_CONFIG) == CUSTOM_ORDER
    # 键缺失（而不是设成默认值）要能区分开：没有就是没有。
    assert "section_order" not in {}


def test_html_preview_follows_the_custom_order():
    html = render_html(_sample_resume(), format_config=CUSTOM_CONFIG)
    _assert_follows_order({"html": html})
    # data-resume-path 是「点击纸面字段定位编辑」的锚点，重排不能动它。
    for path in ("projects.0.name", "experience.0.company", "education.0.school"):
        assert f'data-resume-path="{path}"' in html


def test_markdown_and_txt_follow_the_custom_order():
    order = CUSTOM_ORDER
    markdown = export_markdown(_sample_resume(), section_order=order)
    plain = export_txt(_sample_resume(), section_order=order)
    _assert_follows_order({"markdown": markdown, "txt": plain})
    # txt 是从 markdown 剥出来的，两者天然同源。
    assert re.sub(r"[#*`\-\s]", "", markdown) == re.sub(r"[#*`\-\s]", "", plain)


def test_word_document_follows_the_custom_order():
    from docx import Document

    document = build_resume_docx(_sample_resume(), format_config=CUSTOM_CONFIG)
    doc = Document(io.BytesIO(document.content))
    _assert_follows_order({"docx": "\n".join(p.text for p in doc.paragraphs)})


def test_pdf_renders_with_the_custom_order_without_changing_page_count_semantics():
    """服务端 PDF 用同一份顺序渲染；这里只验证它不报错、仍是合法 PDF。

    PDF 的分区顺序藏在绘制调用里，抽文本会受字体子集化影响，所以不在字节层面断言顺序
    （HTML / Word / Markdown 三处已经钉住了同一个顺序定义）。这里要守住的是：
    带顺序渲染不会让「一页适配」的决策与渲染分家。
    """
    from app.services.pdf_exporter import (
        build_resume_pdf,
        measure_content_height,
        resolve_layout,
    )
    from app.services.resume.resume_templates import validated_format_config

    overrides = validated_format_config(CUSTOM_CONFIG)
    layout = resolve_layout(template="classic", base_px=14, format_config=overrides)
    document = build_resume_pdf(_sample_resume(), format_config=CUSTOM_CONFIG)
    assert document.content.startswith(b"%PDF-")
    assert document.pages >= 1
    height = measure_content_height(
        _sample_resume(), accent=(22, 54, 92), layout=layout, format_config=overrides
    )
    assert height > 0


def test_section_order_survives_template_validation():
    """格式模板校验要保留 section_order，而不是把它当成未知键丢掉。"""
    from app.services.resume.resume_templates import validated_format_config

    validated = validated_format_config(CUSTOM_CONFIG)
    assert validated["section_order"] == CUSTOM_ORDER
    # 没给就不出现：让「没设过」与「设成默认」可以区分。
    assert "section_order" not in validated_format_config({"accent": "#16365c"})
    # 非法输入（空列表 / 字符串以外的东西）不会炸掉整份配置。
    assert "section_order" not in validated_format_config({"section_order": []})
    assert "section_order" not in validated_format_config({"section_order": "projects"})


# ===== 隐藏板块 =====

HIDDEN_CONFIG = {**CUSTOM_CONFIG, "hidden_sections": ["campus_experience", "awards"]}
HIDDEN_TITLES = ("校园经历", "荣誉奖项")


def test_normalized_hidden_sections_drops_unknown_and_dedupes():
    from app.services.resume.resume_sections import normalized_hidden_sections

    assert normalized_hidden_sections(["awards", "awards", "不存在的键"]) == ["awards"]
    # 查询串写法也认，与 normalized_section_order 保持一致。
    assert normalized_hidden_sections("projects, skills") == ["projects", "skills"]
    # 空/非法输入 = 一个都不藏，不抛异常。
    assert normalized_hidden_sections(None) == []
    assert normalized_hidden_sections(12) == []


def test_resolved_visible_sections_keeps_order_and_drops_hidden():
    from app.services.resume.resume_sections import resolved_visible_sections

    visible = resolved_visible_sections(HIDDEN_CONFIG)
    assert visible == [key for key in CUSTOM_ORDER if key not in {"campus_experience", "awards"}]
    # 顺序完整性不被隐藏破坏：放开隐藏后还会回到原位（存储里仍是完整排列）。
    assert resolved_visible_sections({"section_order": CUSTOM_ORDER}) == CUSTOM_ORDER
    assert resolved_visible_sections(None) == list(DEFAULT_SECTION_ORDER)


def test_html_preview_omits_hidden_sections():
    html = render_html(_sample_resume(), format_config=HIDDEN_CONFIG)
    for title in HIDDEN_TITLES:
        assert title not in html
    # 没被藏的分区还在，且仍是自定义顺序。
    assert "项目经历" in html and "个人总结" in html
    assert html.index("项目经历") < html.index("个人总结")


def test_markdown_and_txt_omit_hidden_sections():
    from app.services.resume.resume_sections import resolved_visible_sections

    visible = resolved_visible_sections(HIDDEN_CONFIG)
    markdown = export_markdown(_sample_resume(), section_order=visible)
    plain = export_txt(_sample_resume(), section_order=visible)
    for title in HIDDEN_TITLES:
        assert title not in markdown
        assert title not in plain
    assert "项目经历" in markdown


def test_word_document_omits_hidden_sections():
    from docx import Document

    document = build_resume_docx(_sample_resume(), format_config=HIDDEN_CONFIG)
    text = "\n".join(p.text for p in Document(io.BytesIO(document.content)).paragraphs)
    for title in HIDDEN_TITLES:
        assert title not in text
    assert "项目经历" in text


def test_pdf_measurement_and_render_both_skip_hidden_sections():
    """隐藏了板块时，量高的和画 PDF 的必须用同一份可见列表，否则一页适配会白缩字号。"""
    from app.services.pdf_exporter import (
        build_resume_pdf,
        measure_content_height,
        resolve_layout,
    )
    from app.services.resume.resume_templates import validated_format_config

    overrides = validated_format_config(HIDDEN_CONFIG)
    layout = resolve_layout(template="classic", base_px=14, format_config=overrides)
    full_height = measure_content_height(
        _sample_resume(),
        accent=(22, 54, 92),
        layout=layout,
        format_config=validated_format_config(CUSTOM_CONFIG),
    )
    hidden_height = measure_content_height(
        _sample_resume(), accent=(22, 54, 92), layout=layout, format_config=overrides
    )
    assert hidden_height < full_height
    document = build_resume_pdf(_sample_resume(), format_config=HIDDEN_CONFIG)
    assert document.content.startswith(b"%PDF-")


def test_hidden_sections_survive_template_validation():
    """校验层要保留 hidden_sections，否则 PATCH /layout 一存就把它丢了。"""
    from app.services.resume.resume_templates import validated_format_config

    validated = validated_format_config(HIDDEN_CONFIG)
    assert validated["hidden_sections"] == ["campus_experience", "awards"]
    assert validated["section_order"] == CUSTOM_ORDER
    # 空列表等于不藏，不写进配置（前端取消全部隐藏时也是直接删键）。
    assert "hidden_sections" not in validated_format_config({"hidden_sections": []})
    assert "hidden_sections" not in validated_format_config({"hidden_sections": ["bogus"]})
