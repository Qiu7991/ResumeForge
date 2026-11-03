# SPDX-License-Identifier: Apache-2.0
"""AI 写路径不变量收口的回归测试（Phase 2；覆盖 P8 / P9 / P10）。

生成落库（``save_record``）与 AI 修订（``revise_existing_resume``）共用唯一收口
``finalize_ai_document``，所以这里直接对它测行为契约；另加两条接线级断言：

- 修订路由传 ``page_limit=None``（P9：修订绝不截断）；
- 手工保存（``save_content``）不触发去重（用户手写内容不被系统悄悄改掉）。
"""

from pathlib import Path

from app.models.resume import ResumeRecord
from app.schemas.resume_document import MAX_LIST_VALUES, parse_document
from app.services.resume.document_invariants import finalize_ai_document
from app.services.resume.document_io import document_for_record
from app.services.resume.document_save import save_content


def _finalize(content: dict, *, page_limit: int | None = None, include_tech_stack: bool = True) -> dict:
    return finalize_ai_document(
        content,
        language="zh-CN",
        format_config={},
        custom_fields=None,
        page_limit=page_limit,
        include_tech_stack=include_tech_stack,
    )


def _section(doc: dict, key: str) -> dict:
    return next(section for section in doc["sections"] if section["key"] == key)


def _entry_texts(entry: dict) -> list[str]:
    """条目里的正文内容：TextItem 文本 + list item 的 values 都算。"""
    texts: list[str] = []
    for item in entry.get("items") or []:
        if item.get("kind") == "text":
            texts.append(str(item.get("text") or ""))
        elif item.get("kind") == "list":
            texts.extend(str(value) for value in (item.get("values") or []))
    return texts


def _v1_projects(count: int) -> dict:
    return {
        "name": "张示例",
        "job_intent": "后端开发",
        "projects": [
            {"name": f"项目{index}", "description": [f"做了 {index} 件事"]}
            for index in range(1, count + 1)
        ],
    }


# 1) 模型返回重复项目 → 同名只剩一条，要点合并（不丢要点）
def test_duplicate_projects_merge_without_losing_points():
    content = {
        "name": "张示例",
        "projects": [
            {"name": "同名项目", "description": ["做了 A"], "highlights": ["亮点一"]},
            {"name": "同名项目", "description": ["做了 B"]},
        ],
    }
    doc = _finalize(content, page_limit=None)
    entries = _section(doc, "projects")["entries"]
    assert len(entries) == 1
    texts = _entry_texts(entries[0])
    assert "做了 A" in texts and "做了 B" in texts and "亮点一" in texts


# 2) 开关关闭时 tech_stack 项 placement=hidden（数据保留，出口不可见；导出过滤见 Phase 3）
def test_tech_stack_hidden_when_preference_off():
    content = {
        "name": "张示例",
        "projects": [{"name": "项目1", "tech_stack": ["Python", "FastAPI"], "description": ["做了 A"]}],
    }
    doc = _finalize(content, include_tech_stack=False)
    tech_items = [
        item
        for entry in _section(doc, "projects")["entries"]
        for item in entry.get("items") or []
        if item.get("kind") == "list" and item.get("key") == "tech_stack"
    ]
    assert tech_items, "tech_stack 列表项应存在"
    assert all(item.get("placement") == "hidden" for item in tech_items)
    assert tech_items[0].get("values"), "隐藏只影响纸面，数据不删"
    # 开关打开时同样内容不隐藏
    doc_on = _finalize(content, include_tech_stack=True)
    tech_on = [
        item
        for entry in _section(doc_on, "projects")["entries"]
        for item in entry.get("items") or []
        if item.get("kind") == "list" and item.get("key") == "tech_stack"
    ]
    assert all(item.get("placement") != "hidden" for item in tech_on)


# 3) 页数上限符合 limit_resume 规则（1 页 3 项目 / 2 页 5 项目）
def test_page_limit_caps_entries():
    doc_1p = _finalize(_v1_projects(5), page_limit=1)
    assert len(_section(doc_1p, "projects")["entries"]) == 3
    doc_2p = _finalize(_v1_projects(7), page_limit=2)
    assert len(_section(doc_2p, "projects")["entries"]) == 5


# 4) P8 回归：合并后 values 不超过 MAX_LIST_VALUES，且能再次 parse_document
def test_merged_values_stay_under_schema_cap_and_reparse():
    content = {
        "name": "张示例",
        "projects": [
            {"name": "同名", "tech_stack": [f"技术{index}" for index in range(500)]},
            {"name": "同名", "tech_stack": [f"技术{index}" for index in range(500, 1000)]},
        ],
    }
    doc = _finalize(content, page_limit=None)
    entries = _section(doc, "projects")["entries"]
    assert len(entries) == 1
    values = next(
        item["values"]
        for item in entries[0]["items"]
        if item.get("kind") == "list" and item.get("key") == "tech_stack"
    )
    assert len(values) <= MAX_LIST_VALUES
    parse_document(doc)  # 校验在流水线最后：产物必须能再次通过 schema


# 5) P9 回归：修订配置（page_limit=None）下 7 个项目修订后仍是 7 个
def test_revision_path_never_truncates_seven_projects():
    doc = _finalize(_v1_projects(7), page_limit=None)
    assert len(_section(doc, "projects")["entries"]) == 7


def test_revision_route_passes_page_limit_none():
    """接线级 P9 防线：修订路由对 finalize 的调用必须显式 page_limit=None。"""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "resumes" / "ai_edits_routes.py"
    ).read_text(encoding="utf-8")
    assert "page_limit=None" in source


# 6) P10 回归：同公司两段不同职位不被合并；同公司同职位同期仍合并
def test_same_company_two_roles_stay_separate():
    two_roles = {
        "name": "张示例",
        "experience": [
            {
                "company": "同一家公司",
                "role": "工程师",
                "start_date": "2020-01",
                "end_date": "2022-01",
                "description": ["第一段职责"],
            },
            {
                "company": "同一家公司",
                "role": "高级工程师",
                "start_date": "2022-01",
                "end_date": "2024-01",
                "description": ["第二段职责"],
            },
        ],
    }
    doc = _finalize(two_roles, page_limit=None)
    entries = _section(doc, "experience")["entries"]
    assert len(entries) == 2, "晋升经历不能被合并掉"

    same_role = {
        "name": "张示例",
        "experience": [
            {
                "company": "另一家公司",
                "role": "工程师",
                "start_date": "2020-01",
                "end_date": "2022-01",
                "description": ["一段"],
            },
            {
                "company": "另一家公司",
                "role": "工程师",
                "start_date": "2020-01",
                "end_date": "2022-01",
                "description": ["二段"],
            },
        ],
    }
    doc_same = _finalize(same_role, page_limit=None)
    entries_same = _section(doc_same, "experience")["entries"]
    assert len(entries_same) == 1
    texts = _entry_texts(entries_same[0])
    assert "一段" in texts and "二段" in texts


# 7) AI 修订产物落库后再读详情，不变量仍成立（读路径归一化不改写内容）
def test_finalize_output_survives_a_save_and_read_cycle(db_session):
    doc = _finalize(_v1_projects(7), page_limit=None, include_tech_stack=False)
    record = ResumeRecord(title="不变量回归", content=doc, format_config={})
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    read_back, _report = document_for_record(db_session, record)
    proj = _section(read_back, "projects")
    assert len(proj["entries"]) == 7
    tech_items = [
        item
        for entry in proj["entries"]
        for item in entry.get("items") or []
        if item.get("kind") == "list" and item.get("key") == "tech_stack"
    ]
    assert all(item.get("placement") != "hidden" for item in tech_items)


# 8) 手工保存不触发去重：两段同名项目原样落库
def test_manual_save_does_not_dedupe(db_session):
    doc = _finalize(_v1_projects(1), page_limit=None)
    duplicate = dict(doc)
    entries = list(_section(doc, "projects")["entries"])
    sections = [
        dict(section, entries=[*entries, dict(entries[0])])
        if section["key"] == "projects"
        else section
        for section in doc["sections"]
    ]
    duplicate["sections"] = sections
    record = ResumeRecord(title="手工保存", content=dict(doc), format_config={})
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    outcome = save_content(db_session, record_id=record.id, content=duplicate, expected_revision=None)
    assert outcome is not None and outcome.written
    stored = db_session.get(ResumeRecord, record.id)
    db_session.refresh(stored)
    assert len(_section(stored.content, "projects")["entries"]) == 2, "手工保存不去重"
