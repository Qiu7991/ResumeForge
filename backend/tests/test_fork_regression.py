# SPDX-License-Identifier: Apache-2.0
"""二开功能回归矩阵（Phase 5 / B2）。

矩阵口径：按「记录原本是什么」×「本次写路径喂什么」组合，断言二开不变量仍然成立。
每条断言都写明"失败时是哪条不变量坏了"。

| 写路径 | 请求体 v1 | 请求体 v2 | 记录原本是 v1 | 断言 |
|---|---|---|---|---|
| 生成落库 | 有 | 有 | — | 无重复、技术栈隐藏、页数上限 |
| AI 修订 | — | 有 | 有 | 无重复、技术栈隐藏、条目不减少 |
| 手工保存 | 有 | 有 | — | 不自动删内容，但结构合法 |
| 覆盖补全（保存幂等） | — | 有 | — | 同内容二次保存 written=False |
| 导出四格式 | — | 有 | 有 | 隐藏板块不出现、两源出口逐字节一致 |
"""

import io
import json

from docx import Document
from pypdf import PdfReader

from app.models.resume import ResumeRecord
from app.schemas.resume_document import document_to_json, parse_document
from app.services.docx_exporter import build_resume_docx
from app.services.exporter import export_markdown, render_html
from app.services.pdf_exporter import build_resume_pdf
from app.services.profile.generation_preferences import get_generation_preferences
from app.services.resume import document_io
from app.services.resume.document_html import coerce_document, paper_document
from app.services.resume.document_invariants import finalize_ai_document
from app.services.resume.document_save import save_ai_revision, save_content
from app.services.resume.resume_record import save_record

V1_BODY = {
    "name": "张示例",
    "job_intent": "后端开发",
    "summary": "五年后端经验。",
    "projects": [
        {"name": "同名项目", "description": ["做了 A"], "tech_stack": ["Python", "FastAPI"]},
        {"name": "同名项目", "description": ["做了 B"]},
        {"name": "项目三", "description": ["做了 C"]},
        {"name": "项目四", "description": ["做了 D"]},
        {"name": "项目五", "description": ["做了 E"]},
    ],
}

V2_BODY = {
    "version": 2,
    "language": "zh-CN",
    "header": {"items": [{"kind": "field", "key": "name", "value": "张示例", "placement": "name"}]},
    "sections": [
        {
            "key": "projects",
            "title": "",
            "kind": "entries",
            "entries": [
                {
                    "id": "ob_proj000001",
                    "items": [
                        {"kind": "field", "key": "name", "value": "项目一", "placement": "title"},
                        {"kind": "text", "style": "bullet", "text": "做了 A"},
                    ],
                }
            ],
        }
    ],
}


def _project_entries(doc: dict) -> list[dict]:
    return next(s["entries"] for s in doc["sections"] if s["key"] == "projects")


def _project_names(doc: dict) -> list[str]:
    return [
        item.get("value")
        for entry in _project_entries(doc)
        for item in entry.get("items") or []
        if item.get("kind") == "field" and item.get("key") == "name"
    ]


def _tech_items(doc: dict) -> list[dict]:
    return [
        item
        for entry in _project_entries(doc)
        for item in entry.get("items") or []
        if item.get("kind") == "list" and item.get("key") == "tech_stack"
    ]


def _add_record(db, *, content: dict, title: str = "回归记录") -> ResumeRecord:
    record = ResumeRecord(title=title, content=content, format_config={})
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---- 生成落库：v1 / v2 请求体都要过同一个收口 ----
def test_generate_path_v1_and_v2_bodies_produce_clean_records(db_session):
    assert get_generation_preferences(db_session)["include_tech_stack"] is False, (
        "测试库的生成偏好应为默认（关闭技术栈）；否则本用例前提不成立"
    )
    for label, body in (("v1请求体", dict(V1_BODY)), ("v2请求体", dict(V2_BODY))):
        record = save_record(
            db_session,
            json.loads(json.dumps(body)),
            warnings=[],
            job=None,
            raw="",
            model="test",
            enhancement_enabled=False,
            enhancement_level="standard",
            page_limit=1,
            language="zh-CN",
        )
        doc = record.content
        names = _project_names(doc)
        assert len(names) == len(set(names)), (
            f"生成落库（{label}）：同名项目没有合并——去重不变量坏了（F10）"
        )
        assert len(names) <= 3, (
            f"生成落库（{label}）：1 页上限下项目数 {len(names)} > 3——页数收敛坏了（F10）"
        )
        assert all(item.get("placement") == "hidden" for item in _tech_items(doc)), (
            f"生成落库（{label}）：偏好关闭时技术栈仍可见——F07 坏了"
        )
        try:
            parse_document(doc)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"生成落库（{label}）：落库文档过不了 schema（校验必须收在最后）: {exc}")


# ---- AI 修订：记录原本是 v1，条目绝不减少 ----
def test_revise_path_on_v1_record_never_truncates(db_session):
    record = _add_record(db_session, content=dict(V1_BODY), title="原本是v1")
    # 修订产出（模拟模型回包的 v1 形状）：7 个项目，末尾一条与项目7 同名（应合并要点）
    revised = {
        "name": "张示例",
        "projects": [
            {"name": f"项目{n}", "description": [f"做了 {n}"], "tech_stack": ["Python"]}
            for n in range(1, 8)
        ]
        + [{"name": "项目7", "description": ["补充要点"]}],
    }
    finalized = finalize_ai_document(
        revised,
        language=record.language,
        format_config=record.format_config or {},
        custom_fields=document_io.custom_field_definitions(db_session),
        page_limit=None,  # 修订路径的硬契约：绝不截断（P9）
        include_tech_stack=get_generation_preferences(db_session)["include_tech_stack"],
    )
    outcome = save_ai_revision(
        db_session,
        record_id=record.id,
        content=finalized,
        fact_annotations=[],
        base_revision=None,
    )
    assert outcome is not None and outcome.written, "AI 修订：修订结果没有落库"
    stored = db_session.get(ResumeRecord, record.id)
    db_session.refresh(stored)
    names = _project_names(stored.content)
    assert len(names) == 7 and len(set(names)) == 7, (
        f"AI 修订：期望 7 个不重复项目，实际 {names}——修订截断（P9）或去重失效（F10）"
    )
    assert "做了 7" in json.dumps(stored.content, ensure_ascii=False) and "补充要点" in json.dumps(
        stored.content, ensure_ascii=False
    ), "AI 修订：同名条目合并时丢了要点（F10 的「要点取并集」坏了）"
    assert all(item.get("placement") == "hidden" for item in _tech_items(stored.content)), (
        "AI 修订：偏好关闭时技术栈可见（F07 坏了）"
    )
    try:
        parse_document(stored.content)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"AI 修订：修订后文档过不了 schema: {exc}")


# ---- 手工保存：不自动删内容，但结构合法 ----
def test_manual_save_keeps_content_and_stays_valid(db_session):
    record = _add_record(db_session, content=V2_BODY, title="手工保存")
    v1_dup = {
        "name": "张示例",
        "projects": [
            {"name": "同名项目", "description": ["做了 A"]},
            {"name": "同名项目", "description": ["做了 B"]},
        ],
    }
    for label, body in (("v1请求体", v1_dup), ("v2请求体", V2_BODY)):
        prepared = document_io.prepare_document_for_save(
            json.loads(json.dumps(body)), language=record.language
        )
        outcome = save_content(
            db_session, record_id=record.id, content=prepared, expected_revision=None
        )
        assert outcome is not None and outcome.written
        stored = db_session.get(ResumeRecord, record.id)
        db_session.refresh(stored)
        if label == "v1请求体":
            assert len(_project_names(stored.content)) == 2, (
                "手工保存：两段同名项目被系统悄悄合并/删除——手工内容不得被改（F10 边界）"
            )
        try:
            parse_document(stored.content)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"手工保存（{label}）：落库文档结构不合法: {exc}")


# ---- 覆盖补全的保存幂等：同内容二次保存 written=False ----
def test_coverage_fill_save_is_idempotent(db_session):
    record = _add_record(db_session, content=V2_BODY, title="覆盖补全")
    filled = json.loads(json.dumps(V2_BODY))
    filled["sections"][0]["entries"].append(
        {
            "id": "ob_proj000002",
            "items": [
                {"kind": "field", "key": "name", "value": "补全项目", "placement": "title"},
                {"kind": "text", "style": "bullet", "text": "补的要点"},
            ],
        }
    )
    prepared = document_io.prepare_document_for_save(filled, language=record.language)
    first = save_content(db_session, record_id=record.id, content=prepared, expected_revision=None)
    assert first is not None and first.written, "覆盖补全：首次保存应落库"
    # 真实流程：前端拿「保存返回的文档」原样回传（缺 id 的 header 项由后端补发随机 id，
    # 客户端独立重放会产生不同 id，那不是同一个保存请求）。
    stored = db_session.get(ResumeRecord, record.id)
    db_session.refresh(stored)
    again = document_io.prepare_document_for_save(
        json.loads(json.dumps(stored.content)), language=record.language
    )
    second = save_content(db_session, record_id=record.id, content=again, expected_revision=None)
    assert second is not None and second.written is False, (
        "覆盖补全：重复点「补上这段」把同一内容存了两遍——幂等坏了（F09）"
    )


# ---- 导出四格式：迁移来源（原 v1）与原生 v2 的出口逐字节一致；隐藏板块不出现 ----
def _hidden_skills(doc: dict) -> dict:
    for section in doc["sections"]:
        if section["key"] == "skills":
            section["hidden"] = True
    return doc


def test_exports_identical_for_migrated_and_native_v2(db_session):
    v1_record = _add_record(db_session, content=dict(V1_BODY), title="导出_原v1")
    # 「记录原本是 v1」= Phase 1 迁移后的形态：读时转换 → 用户隐藏 skills → 存回
    converted, _report = document_io.document_for_record(db_session, v1_record)
    v1_record.content = _hidden_skills(json.loads(json.dumps(converted)))
    db_session.commit()
    db_session.refresh(v1_record)
    # 原生 v2：同一种隐藏方式
    v2_record = _add_record(
        db_session, content=_hidden_skills(document_io.ensure_document_version(dict(V1_BODY), language="zh-CN", format_config={})), title="导出_原生v2"
    )

    for record in (v1_record, v2_record):
        markdown = export_markdown(record.content, format_config=record.format_config or {})
        assert "SQL" not in markdown, (
            f"导出（{record.title}）：隐藏板块 skills 的正文出现在 Markdown（P3 复发）"
        )
        html = render_html(record.content, format_config=record.format_config or {})
        assert "SQL" not in html, f"导出（{record.title}）：隐藏板块出现在 HTML（P3 复发）"
        word = build_resume_docx(record.content, format_config=record.format_config or {})
        word_text = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
        assert "SQL" not in word_text, f"导出（{record.title}）：隐藏板块出现在 Word（P3 复发）"
        pdf = build_resume_pdf(record.content, page_limit=1)
        pdf_text = "".join(
            (page.extract_text() or "") for page in PdfReader(io.BytesIO(pdf.content)).pages
        )
        assert "SQL" not in "".join(pdf_text.split()), (
            f"导出（{record.title}）：隐藏板块出现在 PDF（P3 复发）"
        )

    # 顺序一致：迁移来源与原生 v2 的 Markdown 逐字节相同；纸面文档（HTML/PDF 的输入）
    # 也逐字节相同。HTML 字节串本身不比——render_html 每次渲染注入随机 CSP nonce。
    md_a = export_markdown(v1_record.content, format_config=v1_record.format_config or {})
    md_b = export_markdown(v2_record.content, format_config=v2_record.format_config or {})
    assert md_a == md_b, "导出：迁移来源与原生 v2 的 Markdown 不一致（两套真相，P1/P3）"
    paper_a = document_to_json(
        paper_document(
            coerce_document(
                json.loads(json.dumps(v1_record.content)),
                language=v1_record.language,
                format_config=v1_record.format_config or {},
            )
        )
    )
    paper_b = document_to_json(
        paper_document(
            coerce_document(
                json.loads(json.dumps(v2_record.content)),
                language=v2_record.language,
                format_config=v2_record.format_config or {},
            )
        )
    )
    assert json.dumps(paper_a, sort_keys=True) == json.dumps(paper_b, sort_keys=True), (
        "导出：迁移来源与原生 v2 的纸面文档不一致（两套真相，P1/P3）"
    )
