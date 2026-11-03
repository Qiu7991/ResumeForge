# SPDX-License-Identifier: Apache-2.0
"""把库里全部 resume_record 的 content 归一为 v2，并消费旧版式键（Phase 1）。

方案：docs/fork-v2-compatibility-plan.md「Phase 1」。行为契约（不要增删）：

1. 默认 ``--dry-run``；``--apply`` 才写库；``--apply`` 前自动做 WAL 安全备份
   （``sqlite3.Connection.backup``，与 ``scripts/v2_gate.py --backup`` 同一套写法；
   **不要用 cp**——库是 WAL 模式，cp 会丢掉 ``-wal`` 里已提交的事务）；
2. 遍历**全部** ``resume_record``（含软删）；
3. 每条记录：``content.version == 2`` → ``parse_document`` 归一化，与原文有差异才写；
   否则 → ``document_io.ensure_document_version(...)`` 转 v2；
4. 旧版式收口顺序（唯一正确顺序，反了会丢信息）：
   ① 先用 ``format_config.section_order`` 重排 ``document.sections``；
   ② 再把 ``format_config.hidden_sections`` 里的 key 映射成 ``section.hidden = True``；
   ③ 最后把这两个键从 ``format_config`` 删除；
5. 写库字段：``content``、``format_config``、``updated_at``；``revision`` 只对 live 记录 +1
   （软删记录没人拿它做条件写，推进无意义）；
6. 幂等：第二次 ``--apply`` 必须 0 条修改；
7. ``--json`` 在 stdout **最后一行**输出一行 JSON（``scripts/v2_gate.py --phase 1`` 解析末行）：

   ``{"total":40,"v1":0,"v2_normalized":0,"skipped":0,"hidden_sections_consumed":0,
     "section_order_consumed":0,"parse_failed":0,"visibility_changes":[{"id":9,
     "hidden":["awards","campus_experience","skills"]}]}``

⚠️ 用户可见变化：``hidden_sections`` 此前从不被消费（P3，转换器只读 section_order），
那些"被隐藏"的板块一直显示在纸面上；本脚本让它们**第一次真正生效**——迁移后这些板块
会从纸面上消失。这是修复，不是 bug；dry-run 的 ``visibility_changes`` 必须人工过目。

用法（仓库根；``--apply`` 前先 ``stop.cmd`` 停应用）：

    backend/.venv/Scripts/python.exe -I scripts/normalize_resume_documents.py --dry-run --json
    backend/.venv/Scripts/python.exe -I scripts/normalize_resume_documents.py --apply --json
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import argparse
import json
import sqlite3
from datetime import datetime
from typing import Any

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.profile import utcnow
from app.models.resume import ResumeRecord
from app.schemas.resume_document import document_to_json, parse_document
from app.services.resume import document_io
from app.services.resume.document_converter import _ordered_sections

LEGACY_LAYOUT_KEYS = ("section_order", "hidden_sections")


def _backup_database(db: Session) -> Path | None:
    """WAL 安全备份（与 scripts/import_portrait.py::_backup_database 同一套写法）。"""
    bind = db.get_bind()
    database = getattr(getattr(bind, "url", None), "database", None)
    if not database:
        return None
    source_path = Path(database)
    if not source_path.is_file():
        return None
    backup = source_path.with_name(
        f"{source_path.name}.pre-normalize-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
    )
    with sqlite3.connect(source_path) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    return backup


def normalize_record(
    content: Any,
    format_config: Any,
    *,
    language: str | None,
    custom_fields: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[str], int]:
    """单条记录归一。

    返回 ``(新 content 或 None=解析失败, 新 format_config, 本次新隐藏的板块 key, 隐藏后可见板块数)``。
    收口顺序是硬契约：section_order 重排 → hidden_sections 映射 → 删两个键。
    """
    config = dict(format_config) if isinstance(format_config, dict) else {}
    raw_hidden = config.get("hidden_sections")
    hidden_keys = {str(key) for key in raw_hidden} if isinstance(raw_hidden, list) else set()
    try:
        if content.get("version") == 2:
            doc = parse_document(content)
        else:
            converted = document_io.ensure_document_version(
                content,
                language=language,
                format_config=config,
                custom_fields=custom_fields,
            )
            doc = parse_document(converted)
    except Exception as exc:  # ConversionError / DocumentValidationError / pydantic
        print(f"PARSE_FAILED detail: {exc}")
        return None, config, [], 0

    # ① section_order 重排：只在键真实存在时做。转换器对 v1 内部已按它排过；
    # v2 在这里补排。键不在时**不能**套 _ordered_sections——它会按默认顺序重排，
    # 把已经"烘焙"进 sections 数组的自定义顺序重置掉（幂等就破了）。
    if "section_order" in config:
        doc.sections = _ordered_sections(list(doc.sections), config)
    # ② hidden_sections 首次真正生效：映射成 section.hidden（只影响纸面，不删数据）。
    newly_hidden: list[str] = []
    for section in doc.sections:
        if section.key in hidden_keys and not section.hidden:
            section.hidden = True
            newly_hidden.append(section.key)
    # ③ 旧键不落库（闸门 --phase 1 会检查两个键都不在 format_config 里）。
    new_config = {key: value for key, value in config.items() if key not in LEGACY_LAYOUT_KEYS}
    visible_after = sum(1 for section in doc.sections if not section.hidden)
    return document_to_json(doc), new_config, newly_hidden, visible_after


def run(db: Session, *, apply: bool) -> dict:
    """处理整个库，返回报告 dict；``apply=True`` 时写库（单事务，最后统一 commit）。"""
    report: dict[str, Any] = {
        "total": 0,
        "v1": 0,
        "v2_normalized": 0,
        "skipped": 0,
        "hidden_sections_consumed": 0,
        "section_order_consumed": 0,
        "parse_failed": 0,
        "visibility_changes": [],
    }
    # 原生 SQL 取行：content 保持 TEXT，坏 JSON 在这里逐条接住（计入 skipped），
    # 而不是在 ORM 反序列化时把整个查询炸掉。
    rows = db.execute(
        text(
            "select id, content, format_config, language, deleted_at, revision "
            "from resume_record order by id"
        )
    ).all()
    custom_fields = document_io.custom_field_definitions(db)
    for rid, raw_content, raw_config, language, deleted_at, revision in rows:
        report["total"] += 1
        try:
            content = json.loads(raw_content) if raw_content else None
        except ValueError:
            report["skipped"] += 1
            print(f"SKIP id={rid}: content 不是合法 JSON")
            continue
        try:
            config = json.loads(raw_config) if raw_config else {}
        except ValueError:
            report["skipped"] += 1
            print(f"SKIP id={rid}: format_config 不是合法 JSON")
            continue
        if not isinstance(content, dict):
            report["skipped"] += 1
            print(f"SKIP id={rid}: content 不是对象")
            continue
        new_content, new_config, newly_hidden, visible_after = normalize_record(
            content, config, language=language, custom_fields=custom_fields
        )
        if new_content is None:
            report["parse_failed"] += 1
            print(f"PARSE_FAILED id={rid}: 文档解析失败")
            continue
        if "hidden_sections" in config:
            report["hidden_sections_consumed"] += 1
        if "section_order" in config:
            report["section_order_consumed"] += 1
        changed = new_content != content or new_config != config
        if not changed:
            continue
        if newly_hidden:
            report["visibility_changes"].append({"id": rid, "hidden": newly_hidden})
            print(f"INFO id={rid}: 隐藏后可见板块 {visible_after}/{len(new_content['sections'])}")
            if visible_after == 0:
                print(f"ALERT id={rid}: 迁移后没有任何可见板块！")
        is_v1 = content.get("version") != 2
        if is_v1:
            report["v1"] += 1
        else:
            report["v2_normalized"] += 1
        tag = "live" if deleted_at is None else "deleted"
        action = "v1→v2" if is_v1 else "v2 归一化"
        print(f"CHANGE id={rid} [{tag}]: {action}" + (f"，新隐藏板块 {newly_hidden}" if newly_hidden else ""))
        if apply:
            values: dict[str, Any] = {
                "content": new_content,
                "format_config": new_config,
                "updated_at": utcnow(),
            }
            if deleted_at is None:
                values["revision"] = int(revision or 0) + 1
            db.execute(
                update(ResumeRecord)
                .where(ResumeRecord.id == rid)
                .values(**values)
                .execution_options(synchronize_session=False)
            )
    if apply:
        db.commit()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="把库里的 v1 简历一次性归一为 v2（默认 dry-run）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="显式声明只预览（默认就是 dry-run；闸门与文档命令都会带上它）",
    )
    parser.add_argument("--apply", action="store_true", help="确认写入数据库（会先自动备份）")
    parser.add_argument("--json", action="store_true", help="stdout 最后一行输出 JSON 报告")
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        if args.apply:
            backup = _backup_database(db)
            if backup is not None:
                print(f"数据库已备份：{backup}")
            else:
                print("警告：未能定位数据库文件，本次 --apply 没有先做备份", file=sys.stderr)
        report = run(db, apply=args.apply)
        if args.json:
            # 闸门解析 stdout 的最后一行；所有人类可读明细都必须在这行之前。
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(
                f"\n汇总：total={report['total']} v1={report['v1']} "
                f"v2_normalized={report['v2_normalized']} skipped={report['skipped']} "
                f"parse_failed={report['parse_failed']} "
                f"hidden_sections_consumed={report['hidden_sections_consumed']} "
                f"section_order_consumed={report['section_order_consumed']}"
            )
            if not args.apply:
                print("（dry-run 未写库；确认明细后加 --apply 执行，写入前会自动备份）")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
