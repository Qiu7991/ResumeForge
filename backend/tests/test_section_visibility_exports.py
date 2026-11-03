# SPDX-License-Identifier: Apache-2.0
"""板块显隐的四格式对拍（Phase 3）：隐藏的板块在 HTML / PDF / Word / Markdown 都不上纸面。

断言**正文关键词**而不是标题——标题可能出现在别处，正文出现才算穿帮。
显示 → 恢复；``persistable_format_config`` 同时丢弃两个旧版式键。
"""

import io

from docx import Document
from pypdf import PdfReader

from app.services.docx_exporter import build_resume_docx
from app.services.exporter import export_markdown, render_html
from app.services.pdf_exporter import build_resume_pdf
from app.services.resume.document_io import ensure_document_version
from app.services.resume.resume_sections import persistable_format_config

SECTION_KEY = "campus_experience"
BODY_KEYWORD = "示例社团"  # campus_experience 条目的正文原文


def _v2_document(*, hidden: bool) -> dict:
    """v1 样例转 v2（不手写 v2 形状），再按显隐开关设置 section.hidden。"""
    content = {
        "name": "张示例",
        "summary": "总结文字",
        "education": [{"school": "示例大学", "major": "示例专业"}],
        "campus_experience": [{"organization": "示例社团", "role": "成员"}],
        "projects": [{"name": "示例项目", "description": ["做了 A"]}],
    }
    document = ensure_document_version(dict(content), language="zh-CN", format_config={})
    for section in document["sections"]:
        if section["key"] == SECTION_KEY:
            section["hidden"] = hidden
    return document


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "".join(page.extract_text() or "" for page in reader.pages)


def test_persistable_format_config_drops_both_legacy_keys():
    kept = persistable_format_config(
        {"hidden_sections": ["awards"], "section_order": ["education"], "font_scale_adjust": 1.1}
    )
    assert kept == {"font_scale_adjust": 1.1}


def test_hidden_section_absent_from_all_four_exports():
    document = _v2_document(hidden=True)
    html = render_html(document, format_config={})
    assert BODY_KEYWORD not in html
    markdown = export_markdown(document)
    assert BODY_KEYWORD not in markdown
    word = build_resume_docx(document, format_config={})
    word_text = "\n".join(
        paragraph.text for paragraph in Document(io.BytesIO(word.content)).paragraphs
    )
    assert BODY_KEYWORD not in word_text
    pdf = build_resume_pdf(document, page_limit=1)
    pdf_text = "".join(_pdf_text(pdf.content).split())
    assert BODY_KEYWORD not in pdf_text


def test_visible_section_restored_in_all_four_exports():
    document = _v2_document(hidden=False)
    html = render_html(document, format_config={})
    assert BODY_KEYWORD in html
    markdown = export_markdown(document)
    assert BODY_KEYWORD in markdown
    word = build_resume_docx(document, format_config={})
    word_text = "\n".join(
        paragraph.text for paragraph in Document(io.BytesIO(word.content)).paragraphs
    )
    assert BODY_KEYWORD in word_text
    pdf = build_resume_pdf(document, page_limit=1)
    pdf_text = "".join(_pdf_text(pdf.content).split())
    assert BODY_KEYWORD in pdf_text


def test_markdown_visible_list_filters_hidden_section():
    """旧调用方语义：section_order = 可见板块清单（resolved_visible_sections 的产物）。"""
    document = _v2_document(hidden=False)
    visible = [section["key"] for section in document["sections"] if section["key"] != SECTION_KEY]
    markdown = export_markdown(document, section_order=visible)
    assert BODY_KEYWORD not in markdown
    assert "示例项目" in markdown
