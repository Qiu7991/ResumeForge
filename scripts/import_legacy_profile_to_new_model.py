"""把旧版六段式资料（user_profile + 子表）导入新版资料模型（profile_entry）。

上游 10-24 起资料页改用 profile_entry / 资料组模型，旧资料**不会自动显示**；本脚本
是一次性迁移工具：读取旧表，把内容映射成新版字段，写入默认组的条目。旧表不删，
可随时回滚（脚本会先复制一份数据库备份）。

用法（仓库根）：
    backend/.venv/Scripts/python.exe scripts/import_legacy_profile_to_new_model.py \
        backend/data/resume_forge.db
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.profile import (
    Award,
    CampusExperience,
    Education,
    Experience,
    ProfilePhoto,
    Project,
    Skill,
    UserProfile,
)
from app.services.profile import entry_store, profile_reader, workspace_bootstrap


def _text(value: object) -> str:
    return str(value or "").strip()


def _basic_values(profile: UserProfile, photo: str) -> dict[str, str]:
    values = {
        "basic_info.name": profile.name,
        "basic_info.gender": profile.gender,
        "basic_info.birth_month": profile.birth_date or profile.birth_year,
        "basic_info.phone": profile.phone,
        "basic_info.email": profile.email,
        "basic_info.city": profile.city,
        "basic_info.target_city": profile.target_city,
        "basic_info.job_intention": profile.job_intent,
        "basic_info.homepage": profile.personal_website,
        "basic_info.github": profile.github,
        "basic_info.photo": photo,
        "basic_info.political_status": profile.political_status,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _education_values(row: Education) -> dict[str, str]:
    values = {
        "educations.school": row.school,
        "educations.major": row.major,
        "educations.degree": row.degree,
        "educations.study_form": row.study_mode,
        "educations.degree_type": row.degree_type,
        "educations.department": row.department,
        "educations.start_date": row.start_date,
        "educations.end_date": row.end_date,
        "educations.gpa": row.gpa,
        "educations.core_courses": row.courses,
        "educations.achievements": row.achievements,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _experience_values(row: Experience) -> dict[str, str]:
    values = {
        "experiences.company": row.company,
        "experiences.title": row.role,
        "experiences.start_date": row.start_date,
        "experiences.end_date": row.end_date,
        "experiences.description": row.description,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _project_values(row: Project) -> dict[str, str]:
    values = {
        "projects.name": row.name,
        "projects.role": row.role,
        "projects.start_date": row.start_date,
        "projects.end_date": row.end_date,
        "projects.tech_stack": row.tech_stack,
        "projects.description": row.description,
        "projects.highlights": row.highlights,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _skill_values(row: Skill) -> dict[str, str]:
    values = {"skills.name": row.name, "skills.level": row.level}
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _campus_values(row: CampusExperience) -> dict[str, str]:
    values = {
        "campus_experiences.organization": row.organization,
        "campus_experiences.role": row.role,
        "campus_experiences.start_date": row.start_date,
        "campus_experiences.end_date": row.end_date,
        "campus_experiences.description": row.description,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _award_values(row: Award) -> dict[str, str]:
    values = {
        "awards.title": row.name,
        "awards.awarded_at": row.date,
        "awards.description": row.description,
    }
    return {key: _text(value) for key, value in values.items() if _text(value)}


def _language_values(educations: list[Education]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for education in educations:
        for certificate, score in (
            ("CET-4", education.cet4_score),
            ("CET-6", education.cet6_score),
        ):
            text = _text(score)
            if not text or (certificate, text) in seen:
                continue
            seen.add((certificate, text))
            rows.append(
                {
                    "languages.language": "英语",
                    "languages.certificate": certificate,
                    "languages.level": certificate,
                    "languages.score": text,
                }
            )
    return rows


def import_profile(db: Session) -> dict[str, int]:
    profile = db.query(UserProfile).order_by(UserProfile.id).first()
    if profile is None:
        return {"total": 0}

    workspace_bootstrap.ensure_workspace(db)
    if profile_reader.workspace_has_entry_values(db):
        raise SystemExit("新版资料已经有内容，未执行迁移（避免重复导入）。")

    photo = _text(profile.photo)
    if not photo:
        primary = (
            db.query(ProfilePhoto)
            .filter(ProfilePhoto.profile_id == profile.id, ProfilePhoto.is_primary.is_(True))
            .first()
        )
        photo = _text(primary.image if primary is not None else "")

    educations = db.query(Education).filter(Education.profile_id == profile.id).all()
    experiences = db.query(Experience).filter(Experience.profile_id == profile.id).all()
    projects = db.query(Project).filter(Project.profile_id == profile.id).all()
    skills = db.query(Skill).filter(Skill.profile_id == profile.id).all()
    campus = db.query(CampusExperience).filter(CampusExperience.profile_id == profile.id).all()
    awards = db.query(Award).filter(Award.profile_id == profile.id).all()

    items: list[dict] = []
    basic = _basic_values(profile, photo)
    if basic:
        items.append({"section_key": "basic_info", "values": basic})
    if _text(profile.summary):
        items.append({"section_key": "summary", "values": {"summary.content": profile.summary}})
    for row in educations:
        values = _education_values(row)
        if values:
            items.append({"section_key": "educations", "values": values})
    for row in experiences:
        values = _experience_values(row)
        if values:
            items.append({"section_key": "experiences", "values": values})
    for row in projects:
        values = _project_values(row)
        if values:
            items.append({"section_key": "projects", "values": values})
    for row in skills:
        values = _skill_values(row)
        if values:
            items.append({"section_key": "skills", "values": values})
    for row in campus:
        values = _campus_values(row)
        if values:
            items.append({"section_key": "campus_experiences", "values": values})
    for row in awards:
        values = _award_values(row)
        if values:
            items.append({"section_key": "awards", "values": values})
    for values in _language_values(educations):
        items.append({"section_key": "languages", "values": values})

    entry_store.bulk_save_entries(db, items)
    return {"total": len(items)}


def main(database: Path) -> int:
    if not database.is_file():
        print(f"[FAIL] 数据库不存在：{database}", file=sys.stderr)
        return 2
    backup = database.with_name(
        f"{database.name}.pre-profile-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
    )
    shutil.copy2(database, backup)
    print(f"[1/3] 已备份：{backup}")

    engine = create_engine(f"sqlite:///{database.resolve().as_posix()}")
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with session_factory() as db:
            counts = import_profile(db)
    finally:
        engine.dispose()
    print(f"[2/3] 旧资料迁移完成：{counts}")
    print("[3/3] 打开「我的资料」即可看到内容；旧表未删除，可用备份回滚。")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python scripts/import_legacy_profile_to_new_model.py <数据库路径>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
