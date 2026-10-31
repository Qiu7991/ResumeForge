"""隐藏板块（本地二开回放）：format_config.hidden_sections 在四个渲染器同源生效。

用户口径：**被隐藏的板块就是不放进简历**，不是"仅预览隐藏"。因此这里钉住：
归一化、顺序不被破坏、HTML / Markdown / txt / Word 都真的不出现该板块。
"""

from __future__ import annotations

import io

from app.schemas.resume import ResumeContent
from app.services.docx_exporter import build_resume_docx
from app.services.exporter import export_markdown, render_html
from app.services.resume.resume_sections import (
    DEFAULT_SECTION_ORDER,
    normalized_hidden_sections,
    resolved_visible_sections,
)
from app.services.resume.resume_template_format import validated_format_config
from app.services.txt_exporter import export_txt

HIDDEN_CONFIG = {"hidden_sections": ["campus_experience", "awards"]}
HIDDEN_TITLES = ("校园经历", "荣誉奖项")


def _sample_resume() -> ResumeContent:
    return ResumeContent(
        name="张示例",
        summary="总结文字",
        education=[{"school": "示例大学", "major": "示例专业", "degree": "本科"}],
        experience=[{"company": "示例科技有限公司", "role": "示例岗位"}],
        campus_experience=[{"organization": "示例社团"}],
        projects=[{"name": "示例项目"}],
        skills=[{"name": "Python"}],
        awards=[{"title": "示例奖项"}],
    )


def test_normalized_hidden_sections_drops_unknown_and_dedupes():
    assert normalized_hidden_sections(["awards", "awards", "不存在的键"]) == ["awards"]
    assert normalized_hidden_sections("projects, skills") == ["projects", "skills"]
    assert normalized_hidden_sections(None) == []
    assert normalized_hidden_sections(12) == []


def test_resolved_visible_sections_keeps_order_and_drops_hidden():
    visible = resolved_visible_sections(HIDDEN_CONFIG)
    assert visible == [
        key for key in DEFAULT_SECTION_ORDER if key not in {"campus_experience", "awards"}
    ]
    assert resolved_visible_sections(None) == list(DEFAULT_SECTION_ORDER)


def test_format_validation_keeps_non_empty_hidden_sections():
    assert validated_format_config(HIDDEN_CONFIG)["hidden_sections"] == [
        "campus_experience",
        "awards",
    ]
    # 空列表 = 恢复默认：不落键；未知键被丢弃。
    assert "hidden_sections" not in validated_format_config({"hidden_sections": []})
    assert "hidden_sections" not in validated_format_config({"hidden_sections": ["不存在"]})


def test_html_preview_omits_hidden_sections():
    html = render_html(_sample_resume(), format_config=HIDDEN_CONFIG)
    for title in HIDDEN_TITLES:
        assert title not in html
    assert "项目经历" in html


def test_markdown_and_txt_omit_hidden_sections():
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
