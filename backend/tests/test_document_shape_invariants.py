# SPDX-License-Identifier: Apache-2.0
"""同形不变量（Phase 5 / B1）：同一份记录，从任何入口取出的文档必须完全一样。

锁住两类历史问题：P1（同一功能时好时坏）与 P3（v1/v2 两套真相）。以后任何人改读路径
（详情 / 导出 / 历史 / preflight / AI 上下文），只要有一个入口取出的形状和别人不一样，
这个文件就会红。

入口矩阵（对应真实读路径）：
- ``document_for_record``        详情 API / render / export 的统一入口
- ``ensure_document_version``    裸读收口（各路由直接调用）
- ``coerce_document``            Markdown / HTML / PDF / Word 出口的归一化入口
- ``paper_document``             纸面视角（唯一过滤点；允许与全量不同，但要"剔除得对"）
- ``document_content``           历史快照路径（document_versions）
"""

import hashlib
import json

from app.models.resume import ResumeRecord
from app.schemas.resume_document import document_to_json
from app.services.resume import document_io
from app.services.resume.document_html import coerce_document, paper_document
from app.services.resume.document_versions import document_content, layout_snapshot
from app.services.resume.document_io import ensure_document_version

V1_SAMPLE = {
    "name": "张示例",
    "job_intent": "后端开发",
    "summary": "五年后端经验。",
    "education": [{"school": "示例大学", "major": "计算机科学", "period": "2015-2019"}],
    "experience": [
        {
            "company": "示例科技",
            "role": "工程师",
            "start_date": "2020-01",
            "end_date": "2022-01",
            "description": ["第一段职责"],
        }
    ],
    "projects": [{"name": "示例项目", "description": ["做了 A"], "tech_stack": ["Python", "FastAPI"]}],
    "skills": [{"name": "Python"}, {"name": "SQL"}],
}


def _sha(doc: dict) -> str:
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _v2() -> dict:
    return ensure_document_version(dict(V1_SAMPLE), language="zh-CN", format_config={})


def _add(db, *, title: str, content: dict) -> ResumeRecord:
    record = ResumeRecord(title=title, content=content, format_config={})
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _fresh(content: dict) -> dict:
    return json.loads(json.dumps(content))


def _paper_json(record: ResumeRecord) -> dict:
    document = paper_document(
        coerce_document(
            _fresh(record.content), language=record.language, format_config=record.format_config or {}
        )
    )
    return document_to_json(document)


def _section_keys(doc: dict) -> list[str]:
    return [section["key"] for section in doc["sections"]]


def _make_records(db) -> dict[str, ResumeRecord]:
    with_hidden_section = _v2()
    for section in with_hidden_section["sections"]:
        if section["key"] == "skills":
            section["hidden"] = True

    with_hidden_tech = _v2()
    for section in with_hidden_tech["sections"]:
        if section["key"] != "projects":
            continue
        for entry in section["entries"]:
            for item in entry["items"]:
                if item.get("kind") == "list" and item.get("key") == "tech_stack":
                    item["placement"] = "hidden"

    return {
        # 1：纯 v2、结构干净
        "pure_v2": _add(db, title="纯v2", content=_v2()),
        # 2：v1 来源（content 原样存 v1 dict，每个入口都要现场转换）
        "from_v1": _add(db, title="v1来源", content=dict(V1_SAMPLE)),
        # 3：带 section.hidden=True（v2 原生板块隐藏）
        "hidden_section": _add(db, title="隐藏板块", content=with_hidden_section),
        # 4：带技术栈项 placement=hidden（v2 原生字段隐藏）
        "hidden_tech": _add(db, title="隐藏技术栈", content=with_hidden_tech),
    }


def test_all_read_paths_produce_identical_documents(db_session):
    """详情 / 裸读 / coerce / 历史四个入口的全量文档必须逐字节同形。

    失败时说明某个读路径对同一份记录给出了不同的 v2 形状——P1/P3 复发。
    """
    records = _make_records(db_session)
    for label, record in records.items():
        full, _report = document_io.document_for_record(db_session, record)
        bare = ensure_document_version(
            _fresh(record.content),
            language=record.language,
            format_config=record.format_config or {},
            custom_fields=document_io.custom_field_definitions(db_session),
        )
        coerced = document_to_json(
            coerce_document(
                _fresh(record.content),
                language=record.language,
                format_config=record.format_config or {},
            )
        )
        history = document_content(_fresh(record.content), layout_snapshot(db_session, record))

        shapes = {
            "document_for_record": full,
            "ensure_document_version": bare,
            "coerce_document": coerced,
            "document_content(历史)": history,
        }
        baseline = _sha(full)
        for name, doc in shapes.items():
            assert _sha(doc) == baseline, (
                f"{label}: {name} 取出的文档与详情路径不同形（P1/P3 复发）；"
                f"sha({name})={_sha(doc)} sha(详情)={baseline}"
            )


def test_paper_view_only_drops_hidden_content(db_session):
    """paper_document 允许与全量不同，但必须"恰好剔除隐藏项"，别的什么都不动。"""
    records = _make_records(db_session)

    # 无隐藏内容的记录：纸面 = 全量
    for label in ("pure_v2", "from_v1"):
        record = records[label]
        full, _report = document_io.document_for_record(db_session, record)
        assert _sha(_paper_json(record)) == _sha(full), (
            f"{label}: 没有任何隐藏项时 paper_document 却改动了文档（过滤点越界）"
        )

    # 隐藏板块：板块消失，正文数据保留在源里，其他板块原样
    hidden = records["hidden_section"]
    full, _report = document_io.document_for_record(db_session, hidden)
    paper = _paper_json(hidden)
    assert "skills" not in _section_keys(paper), "隐藏的板块仍出现在纸面上（P3 复发）"
    assert "skills" in _section_keys(full), "源文档的隐藏板块数据丢了（hidden 应只影响纸面）"
    assert "SQL" not in json.dumps(paper, ensure_ascii=False), "隐藏板块的正文泄漏到纸面"
    for key in _section_keys(full):
        if key != "skills":
            assert key in _section_keys(paper), f"隐藏 skills 时把无关板块 {key} 也弄丢了"

    # 隐藏技术栈项：tech_stack 值不上纸面，条目与描述保留
    tech = records["hidden_tech"]
    tech_full, _report = document_io.document_for_record(db_session, tech)
    tech_paper = _paper_json(tech)
    assert "FastAPI" not in json.dumps(tech_paper, ensure_ascii=False), (
        "placement=hidden 的技术栈值仍出现在纸面上（F07 复发）"
    )
    assert "FastAPI" in json.dumps(tech_full, ensure_ascii=False), "源文档的技术栈数据丢了"
    assert "做了 A" in json.dumps(tech_paper, ensure_ascii=False), (
        "隐藏技术栈项把项目描述也弄丢了（过滤粒度越界）"
    )


def test_v1_source_and_v2_source_render_identically(db_session):
    """同一份简历的 v1 存储与 v2 存储在纸面视角必须完全一致（P3 的最终形态）。"""
    from_v1 = _make_records(db_session)["from_v1"]
    converted, _report = document_io.document_for_record(db_session, from_v1)
    twin = _add(db_session, title="孪生v2", content=json.loads(json.dumps(converted)))

    # 存储态转换（Phase 1 迁移用的路径）与读时转换逐字节一致
    assert _sha(document_io.document_for_record(db_session, twin)[0]) == _sha(converted), (
        "v1 读时转换与 v2 存储不一致：迁移脚本与读路径出现了两套真相"
    )
    # 纸面视角一致
    assert _sha(_paper_json(twin)) == _sha(_paper_json(from_v1)), (
        "同一份简历的 v1/v2 存储在纸面视角不一致（P3 复发）"
    )
