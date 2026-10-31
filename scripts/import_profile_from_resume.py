"""用一份已保存简历的正文覆盖新版资料（用户指定"按照这份简历"）。

与 `import_legacy_profile_to_new_model.py` 的区别：那份读旧六段式资料表；本脚本读
`resume_record.content`，适合"旧资料表已过时、以某份简历为准"的情况。默认拒绝覆盖
已有资料，必须显式 `--replace`；替换走软删，旧条目进回收站可恢复，脚本还先备份数据库。

用法：
    backend/.venv/Scripts/python.exe scripts/import_profile_from_resume.py \
        backend/data/resume_forge.db 10 --replace
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.resume import ResumeRecord
from app.schemas.resume import ResumeContent
from app.services.profile import entry_store, profile_reader, workspace_bootstrap


def _text(value: object) -> str:
    return str(value or "").strip()


def _join_lines(values: list[str] | None) -> str:
    return "\n".join(str(item).strip() for item in (values or []) if str(item).strip())


def _basic(item: ResumeContent) -> dict[str, str]:
    values = {
        "basic_info.name": item.name,
        "basic_info.gender": item.gender,
        "basic_info.birth_month": item.birth_year,
        "basic_info.phone": item.phone,
        "basic_info.email": item.email,
        "basic_info.city": item.city,
        "basic_info.job_intention": item.job_intent,
        "basic_info.homepage": item.personal_website,
        "basic_info.github": item.github,
        "basic_info.photo": item.photo,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _items_from_resume(content: ResumeContent) -> list[dict]:
    items: list[dict] = []
    basic = _basic(content)
    if basic:
        items.append({"section_key": "basic_info", "values": basic})
    if content.summary.strip():
        items.append({"section_key": "summary", "values": {"summary.content": content.summary}})

    for row in content.education:
        values = {
            "educations.school": row.school,
            "educations.major": row.major,
            "educations.degree": row.degree,
            "educations.study_form": getattr(row, "study_form", ""),
            "educations.degree_type": getattr(row, "degree_type", ""),
            "educations.department": getattr(row, "department", ""),
            "educations.start_date": row.start_date,
            "educations.end_date": row.end_date,
            "educations.gpa": row.gpa,
            "educations.rank": getattr(row, "rank", ""),
            "educations.advisor": getattr(row, "advisor", ""),
            "educations.research_direction": getattr(row, "research_direction", ""),
            "educations.core_courses": _join_lines(row.courses),
            "educations.achievements": _join_lines(row.achievements),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "educations", "values": values})

    for row in content.experience:
        values = {
            "experiences.company": row.company,
            "experiences.title": row.role,
            "experiences.start_date": row.start_date,
            "experiences.end_date": row.end_date,
            "experiences.description": _join_lines(row.description),
            "experiences.team_size": getattr(row, "team_size", ""),
            "experiences.work_type": getattr(row, "experience_kind", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "experiences", "values": values})

    for row in content.projects:
        values = {
            "projects.name": row.name,
            "projects.role": row.role,
            "projects.start_date": row.start_date,
            "projects.end_date": row.end_date,
            "projects.tech_stack": "、".join(
                str(item).strip() for item in (row.tech_stack or []) if str(item).strip()
            ),
            "projects.description": _join_lines(row.description),
            "projects.highlights": _join_lines(row.highlights),
            "projects.project_size": getattr(row, "project_size", ""),
            "projects.public_url": getattr(row, "public_url", ""),
            "projects.outcome_type": getattr(row, "outcome_type", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "projects", "values": values})

    for row in content.skills:
        values = {
            "skills.name": row.name,
            "skills.level": getattr(row, "level", ""),
            "skills.category": getattr(row, "category", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "skills", "values": values})

    for row in content.campus_experience:
        values = {
            "campus_experiences.organization": row.organization,
            "campus_experiences.role": row.role,
            "campus_experiences.start_date": row.start_date,
            "campus_experiences.end_date": row.end_date,
            "campus_experiences.description": _join_lines(row.description),
            "campus_experiences.activity_type": getattr(row, "activity_type", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "campus_experiences", "values": values})

    for row in content.awards:
        values = {
            "awards.title": row.name,
            "awards.awarded_at": row.date,
            "awards.description": row.description,
            "awards.issuer": getattr(row, "issuer", ""),
            "awards.level": getattr(row, "level", ""),
            "awards.award_ratio": getattr(row, "ratio", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "awards", "values": values})

    for row in getattr(content, "languages", []):
        values = {
            "languages.language": getattr(row, "language", ""),
            "languages.level": getattr(row, "level", ""),
            "languages.certificate": getattr(row, "certificate", ""),
            "languages.score": getattr(row, "score", ""),
            "languages.obtained_at": getattr(row, "obtained_at", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "languages", "values": values})

    for row in getattr(content, "credentials", []):
        values = {
            "credentials.title": row.name,
            "credentials.credential_type": getattr(row, "credential_type", ""),
            "credentials.issuer": getattr(row, "issuer", ""),
            "credentials.issued_at": getattr(row, "issued_at", ""),
            "credentials.expires_at": getattr(row, "expires_at", ""),
            "credentials.status": getattr(row, "status", ""),
            "credentials.note": getattr(row, "note", ""),
            "credentials.credential_number": getattr(row, "credential_number", ""),
            "credentials.verify_url": getattr(row, "verify_url", ""),
        }
        values = {key: _text(value) for key, value in values.items() if _text(value)}
        if values:
            items.append({"section_key": "credentials", "values": values})
    return items


def _clear_existing(db: Session) -> int:
    removed = 0
    for row in entry_store.list_entries(db):
        entry_store.delete_entry(db, row.section_key, row.entry_id)
        removed += 1
    return removed


def import_from_resume(db: Session, resume_id: int, *, replace: bool) -> dict[str, int]:
    record = db.get(ResumeRecord, resume_id)
    if record is None or record.deleted_at is not None:
        raise SystemExit(f"简历不存在或在回收站：{resume_id}")
    content = ResumeContent.model_validate(record.content)
    workspace_bootstrap.ensure_workspace(db)
    has_entries = profile_reader.workspace_has_entry_values(db)
    if has_entries and not replace:
        raise SystemExit("新版资料已有内容；如确认要用这份简历覆盖，请加 --replace")
    removed = _clear_existing(db) if has_entries else 0
    items = _items_from_resume(content)
    entry_store.bulk_save_entries(db, items)
    return {"removed": removed, "total": len(items)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("resume_id", type=int)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    database = Path(args.database)
    if not database.is_file():
        print(f"[FAIL] 数据库不存在：{database}", file=sys.stderr)
        return 2
    backup = database.with_name(
        f"{database.name}.pre-resume-profile-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
    )
    shutil.copy2(database, backup)
    print(f"[1/3] 已备份：{backup}")

    engine = create_engine(f"sqlite:///{database.resolve().as_posix()}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with factory() as db:
            counts = import_from_resume(db, args.resume_id, replace=args.replace)
    finally:
        engine.dispose()
    print(f"[2/3] 已按简历 {args.resume_id} 写入资料：{counts}")
    print("[3/3] 打开「我的资料」并强制刷新即可查看；旧条目已进回收站。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
