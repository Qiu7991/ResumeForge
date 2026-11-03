# SPDX-License-Identifier: Apache-2.0
"""scripts/normalize_resume_documents.py 的行为契约测试（方案 Phase 1 列的 6 条）。

统一用 conftest 的独立测试库（``clean_db`` autouse，每个用例前重建表），
**绝不碰** backend/data/resume_forge.db。脚本本体按文件路径加载（scripts/ 不是包）。
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.profile import utcnow
from app.models.resume import ResumeRecord
from app.services.resume.document_io import ensure_document_version

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "normalize_resume_documents.py"
_spec = importlib.util.spec_from_file_location("normalize_resume_documents", _SCRIPT)
assert _spec is not None and _spec.loader is not None
normalize_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(normalize_script)

V1_CONTENT = {
    "name": "张示例",
    "job_intent": "后端开发",
    "summary": "五年后端经验。",
    "education": [{"school": "测试大学", "major": "计算机科学", "period": "2015-2019"}],
    "skills": [{"name": "Python"}, {"name": "FastAPI"}],
    "projects": [
        {"name": "项目A", "role": "负责人", "period": "2023", "points": ["做了 A", "做了 B"]}
    ],
}


def _make_v2() -> dict:
    """用转换器本尊造一份合法 v2（不手写 v2 形状，避免与 schema 漂移）。"""
    return ensure_document_version(dict(V1_CONTENT), language="zh-CN", format_config={})


def _add_record(db, *, content, format_config=None, deleted=False, title="测试简历"):
    record = ResumeRecord(title=title, content=content, format_config=format_config or {})
    if deleted:
        record.deleted_at = utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _row(db, record_id):
    """重新从库里读这一行。

    ``SessionLocal`` 是 ``expire_on_commit=False``，而脚本用 Core UPDATE（
    ``synchronize_session=False``），identity map 里的实例不会自动变成新值——
    与 document_save._reload 同一个坑，测试里必须显式失效再取。
    """
    db.expire_all()
    return db.get(ResumeRecord, record_id)


# 1) v1 → v2 后再次运行无变化（幂等）
def test_second_apply_is_noop(db_session):
    _add_record(db_session, content=dict(V1_CONTENT))
    _add_record(db_session, content=_make_v2())

    first = normalize_script.run(db_session, apply=True)
    assert first["v1"] == 1

    second = normalize_script.run(db_session, apply=True)
    assert second["v1"] == 0
    assert second["v2_normalized"] == 0
    assert second["skipped"] == 0
    assert second["parse_failed"] == 0
    assert second["visibility_changes"] == []


# 2) hidden_sections 被消费成 section.hidden=True 并从 format_config 删除
def test_hidden_sections_consumed(db_session):
    record = _add_record(
        db_session, content=_make_v2(), format_config={"hidden_sections": ["skills"]}
    )

    report = normalize_script.run(db_session, apply=True)

    assert report["hidden_sections_consumed"] == 1
    assert {"id": record.id, "hidden": ["skills"]} in report["visibility_changes"]
    row = _row(db_session, record.id)
    assert "hidden_sections" not in (row.format_config or {})
    sections = {section["key"]: section for section in row.content["sections"]}
    assert sections["skills"]["hidden"] is True
    assert not sections["education"].get("hidden", False)


# 3) section_order 被消费成 document.sections 顺序并从 format_config 删除
def test_section_order_consumed(db_session):
    v2 = _make_v2()
    original_keys = [section["key"] for section in v2["sections"]]
    assert len(original_keys) >= 2
    reversed_order = list(reversed(original_keys))
    record = _add_record(
        db_session, content=v2, format_config={"section_order": reversed_order}
    )

    report = normalize_script.run(db_session, apply=True)

    assert report["section_order_consumed"] == 1
    row = _row(db_session, record.id)
    assert "section_order" not in (row.format_config or {})
    assert [section["key"] for section in row.content["sections"]] == reversed_order


# 4) 软删记录也被处理；revision 只对 live 推进
def test_soft_deleted_processed_and_revision_kept(db_session):
    live = _add_record(db_session, content=dict(V1_CONTENT))
    deleted = _add_record(db_session, content=dict(V1_CONTENT), deleted=True)
    live_revision = live.revision
    deleted_revision = deleted.revision

    report = normalize_script.run(db_session, apply=True)

    assert report["v1"] == 2
    live_row = _row(db_session, live.id)
    deleted_row = _row(db_session, deleted.id)
    assert live_row.content["version"] == 2
    assert deleted_row.content["version"] == 2
    assert live_row.revision == live_revision + 1
    assert deleted_row.revision == deleted_revision


# 5) 损坏 JSON 不崩溃，计入 skipped 并打印记录 id
def test_corrupt_content_skipped(db_session, capsys):
    record = _add_record(db_session, content=dict(V1_CONTENT))
    db_session.execute(
        text("update resume_record set content = '{oops' where id = :rid"), {"rid": record.id}
    )
    db_session.commit()

    report = normalize_script.run(db_session, apply=True)

    assert report["skipped"] == 1
    assert str(record.id) in capsys.readouterr().out


# 6) dry-run 不写库（revision 不变，content 仍是 v1，format_config 旧键原样）
def test_dry_run_does_not_write(db_session):
    record = _add_record(
        db_session,
        content=dict(V1_CONTENT),
        format_config={"hidden_sections": ["skills"]},
    )
    before_revision = record.revision

    report = normalize_script.run(db_session, apply=False)

    assert report["v1"] == 1
    row = _row(db_session, record.id)
    assert row.revision == before_revision
    assert row.content.get("version") != 2
    assert row.format_config.get("hidden_sections") == ["skills"]
