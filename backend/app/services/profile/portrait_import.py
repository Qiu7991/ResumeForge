# SPDX-License-Identifier: Apache-2.0
"""个人画像 → 资料库项目/经历 + 事实台账。

画像里的「做了什么 / 关键技术决策 / 结果 / 证据等级 / 边界 / 可迁移能力」不是资料库
13 个字段能完整容纳的：资料库只保留简历纸面可见的规范字段，深度事实进 ``ClaimRecord``。
本模块只负责"把已经抽取好的 JSON 写进去"，不在这里调模型；抽取由
``scripts/import_portrait.py --extract`` 完成，便于先预览、再落库。

关键约束：
- 只更新资料库的规范字段，不覆盖用户自定义字段；
- 事实条目 A/B 级 → 已确认，C 级 → 不采用，没写等级 → 待确认；
- 已存在的事实条目默认**跳过**（用户可能改过口径），不静默覆盖；
- 每条事实都把 ``sources[].location`` 写成关联项目的 ``entry_id``，这样生成时的
  事实基线才会把它带入。
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ...models.claim import (
    CLAIM_CATEGORY_EXPERIENCE,
    CLAIM_CATEGORY_PROJECT,
    RESPONSIBILITY_LEVELS,
    VERIFICATION_CONFIRMED,
    VERIFICATION_PENDING,
    VERIFICATION_REJECTED,
    ClaimRecord,
)
from . import entry_store, workspace_bootstrap

MAX_SOURCE_FACT_CHARS = 8_000
MAX_CANDIDATE_WORDING_CHARS = 8_000
MAX_BOUNDARY_CHARS = 1_000
MAX_SINGLE_LINE_CHARS = 200
MAX_MULTI_LINE_CHARS = 2_000
_SKILL_LEVELS = {"精通", "熟练", "掌握", "了解"}
_SKILL_CATEGORIES = {"编程语言", "框架与库", "工具与平台", "软技能", "其他"}
_OUTCOME_TYPES = {"个人项目", "团队项目", "课程项目", "开源项目", "作品集"}
_EDUCATION_ORG_HINTS = ("大学", "学院", "学校", "中学")
_EDUCATION_ROLE_HINTS = ("本科", "专科", "硕士", "博士", "研究生", "在读", "学历")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _text(value)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _norm(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _clip(value: Any, limit: int) -> str:
    """按字段长度截断；优先在分隔符处断开，不把句子切在中间。"""
    text = _text(value)
    if len(text) <= limit:
        return text
    head = text[:limit]
    for separator in ("\n", "；", "。", "、", ",", " "):
        index = head.rfind(separator)
        if index >= limit // 2:
            return head[:index].rstrip()
    return head


def _display_name(value: Any) -> str:
    """写进资料库的名字：去掉括号注释，保留原文主体。

    例如「AI 简历工作台（v1 + v2）」→「AI 简历工作台」。括号里的版本/技术说明
    留在描述与事实台账里，不占简历标题。
    """
    text = _text(value)
    stripped = re.sub(r"\s*[（(][^）)]*[）)]\s*", " ", text).strip()
    return stripped or text


def _base_key(value: Any) -> str:
    """匹配用的名字：忽略括号注释、空格与常见分隔符。

    模型两次抽取可能把「AI 简历工作台」写成「AI 简历工作台（v1 + v2）」；括号里
    是补充说明，不是另一个项目。只影响匹配，不改变最终写入的名字。
    """
    text = _norm(value)
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return re.sub(r"[\s·\-—_/]+", "", text).strip()


def _choice(value: Any, allowed: set[str]) -> str:
    text = _text(value)
    return text if text in allowed else ""


def _looks_like_education(company: str, role: str) -> bool:
    """防止把“学校 + 本科”抽成一段实习；教育经历不进 experiences。"""
    return any(hint in company for hint in _EDUCATION_ORG_HINTS) and any(
        hint in role for hint in _EDUCATION_ROLE_HINTS
    )


def _responsibility(value: Any) -> str:
    text = _text(value)
    return text if text in RESPONSIBILITY_LEVELS else "参与"


def _verification(grade: Any) -> str:
    text = _text(grade).upper()
    if text in {"A", "B"}:
        return VERIFICATION_CONFIRMED
    if text == "C":
        return VERIFICATION_REJECTED
    return VERIFICATION_PENDING


def _project_values(project: dict[str, Any]) -> dict[str, str]:
    problem = _text(project.get("problem"))
    actions = _lines(project.get("actions"))
    outcomes = _lines(project.get("outcomes"))
    wording = _lines(project.get("candidate_wording"))
    values = {
        "projects.name": _clip(_display_name(project.get("name")), MAX_SINGLE_LINE_CHARS),
        "projects.role": _clip(project.get("role"), MAX_SINGLE_LINE_CHARS),
        "projects.start_date": _clip(project.get("start_date"), MAX_SINGLE_LINE_CHARS),
        "projects.end_date": _clip(project.get("end_date"), MAX_SINGLE_LINE_CHARS),
        "projects.tech_stack": _clip(
            "、".join(_lines(project.get("tech_stack"))), MAX_SINGLE_LINE_CHARS
        ),
        "projects.description": _clip(
            "\n".join([part for part in (problem, *actions[:3]) if part]), MAX_MULTI_LINE_CHARS
        ),
        "projects.highlights": _clip(
            "\n".join([*(wording or outcomes)]), MAX_MULTI_LINE_CHARS
        ),
        "projects.project_size": _clip(project.get("project_size"), MAX_SINGLE_LINE_CHARS),
        "projects.public_url": _clip(project.get("public_url"), MAX_SINGLE_LINE_CHARS),
        "projects.outcome_type": _choice(project.get("artifact_type"), _OUTCOME_TYPES),
    }
    return {key: value for key, value in values.items() if value}


def _experience_values(experience: dict[str, Any]) -> dict[str, str]:
    facts = _lines(experience.get("hard_facts"))
    wording = _lines(experience.get("candidate_wording"))
    values = {
        "experiences.company": _clip(
            _display_name(experience.get("company")), MAX_SINGLE_LINE_CHARS
        ),
        "experiences.title": _clip(experience.get("role"), MAX_SINGLE_LINE_CHARS),
        "experiences.start_date": _clip(experience.get("start_date"), MAX_SINGLE_LINE_CHARS),
        "experiences.end_date": _clip(experience.get("end_date"), MAX_SINGLE_LINE_CHARS),
        "experiences.description": _clip(
            "\n".join([*facts, *wording]), MAX_MULTI_LINE_CHARS
        ),
    }
    return {key: value for key, value in values.items() if value}


def _skill_values(skill: dict[str, Any]) -> dict[str, str]:
    values = {
        "skills.name": _clip(_display_name(skill.get("name")), MAX_SINGLE_LINE_CHARS),
        "skills.level": _choice(skill.get("level"), _SKILL_LEVELS),
        "skills.category": _choice(skill.get("category"), _SKILL_CATEGORIES),
    }
    return {key: value for key, value in values.items() if value}


def _claim_fact(
    *,
    subject: str,
    category: str,
    problem: str,
    actions: list[str],
    decisions: list[str],
    outcomes: list[str],
    tech: list[str],
    wording: list[str],
    grade: str,
    evidence_paths: list[str],
    boundary: str,
    responsibility: str,
    transferable: list[str],
    source_label: str,
) -> dict[str, Any]:
    fact_parts = [
        f"问题/背景：{problem}" if problem else "",
        "动作：" + "；".join(actions) if actions else "",
        "关键决策：" + "；".join(decisions) if decisions else "",
        "结果：" + "；".join(outcomes) if outcomes else "",
        "技术栈：" + "、".join(tech) if tech else "",
        "可迁移能力：" + "、".join(transferable) if transferable else "",
    ]
    safe_subject = _clip(subject, 200)
    source_fact = "\n".join(part for part in fact_parts if part)[:MAX_SOURCE_FACT_CHARS]
    candidate = "\n".join(wording or outcomes)[:MAX_CANDIDATE_WORDING_CHARS]
    risk = [f"证据等级：{grade or '未标注'}"] if grade else []
    sources = [
        {
            "type": "document",
            "location": source_label,
            "public": False,
            "note": "画像导入；原始文件在个人画像目录",
        },
        *(
            {
                "type": "reference",
                "location": path,
                "public": False,
                "note": "画像证据路径",
            }
            for path in evidence_paths[:6]
        ),
    ]
    return {
        "title": _clip(
            f"{safe_subject} · {'项目' if category == CLAIM_CATEGORY_PROJECT else '经历'}事实",
            200,
        ),
        "category": category,
        "subject": safe_subject,
        "source_fact": source_fact,
        "candidate_wording": candidate,
        "sources": sources,
        "responsibility_level": _responsibility(responsibility),
        "verification_status": _verification(grade),
        "allowed_uses": [],
        "interview_details": {
            "decisions": decisions[:20],
            "difficulties": [],
            "verification": evidence_paths[:20],
            "result": "\n".join(outcomes) or None,
        },
        "boundary": _text(boundary)[:MAX_BOUNDARY_CHARS],
        "risk_notes": risk,
        "last_verified": "",
    }


def _existing_entries(db: Session) -> dict[str, dict[str, Any]]:
    rows = entry_store.list_entries(
        db, section_keys={"projects", "experiences", "skills"}
    )
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        values = row.values or {}
        if row.section_key == "projects":
            key = "project:" + _base_key(values.get("projects.name"))
        elif row.section_key == "experiences":
            # 公司是稳定键；同一家公司的岗位名可能被模型写成不同口径。
            key = "experience:" + _base_key(values.get("experiences.company"))
        else:
            key = "skill:" + _base_key(values.get("skills.name"))
        index[key] = {"entry_id": row.entry_id, "values": values}
    return index


def _find_entry(
    index: dict[str, dict[str, Any]], prefix: str, value: Any, *, allow_contains: bool = False
) -> str | None:
    base = _base_key(value)
    if not base:
        return None
    exact = prefix + ":" + base
    if exact in index:
        return exact
    if allow_contains and len(base) >= 4:
        for key in index:
            if not key.startswith(prefix + ":"):
                continue
            other = key.split(":", 1)[1]
            if len(other) >= 4 and (base in other or other in base):
                return key
    return None


def plan_portrait(
    db: Session, bundle: dict[str, Any], *, source_label: str = "个人画像"
) -> dict[str, Any]:
    """只计算计划，不写库。返回条目/事实的 create/update/skip 明细。"""
    workspace_bootstrap.ensure_workspace(db)
    existing = _existing_entries(db)
    entry_items: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    skipped_claims: list[str] = []
    education_skipped: list[str] = []
    created: list[str] = []
    updated: list[str] = []

    def add_entry(
        section: str,
        match_value: Any,
        values: dict[str, str],
        label: str,
        *,
        allow_contains: bool = False,
    ) -> int:
        prefix = {"projects": "project", "experiences": "experience", "skills": "skill"}[
            section
        ]
        match_key = _find_entry(existing, prefix, match_value, allow_contains=allow_contains)
        current = existing.get(match_key) if match_key is not None else None
        if current is not None:
            # 已有条目只补空字段：名字/标题/描述等用户可能已经改过，导入不覆盖。
            merged = dict(current["values"])
            for field, value in values.items():
                if not merged.get(field):
                    merged[field] = value
            values = merged
            entry_items.append(
                {
                    "section_key": section,
                    "entry_id": current["entry_id"],
                    "values": values,
                }
            )
            updated.append(label)
        else:
            entry_items.append({"section_key": section, "values": values})
            created.append(label)
        return len(entry_items) - 1

    for project in bundle.get("projects") or []:
        if not isinstance(project, dict) or not _text(project.get("name")):
            continue
        name = _display_name(project.get("name"))
        entry_index = add_entry("projects", name, _project_values(project), name)
        claims.append(
            {
                **_claim_fact(
                    subject=name,
                    category=CLAIM_CATEGORY_PROJECT,
                    problem=_text(project.get("problem")),
                    actions=_lines(project.get("actions")),
                    decisions=_lines(project.get("decisions")),
                    outcomes=_lines(project.get("outcomes")),
                    tech=_lines(project.get("tech_stack")),
                    wording=_lines(project.get("candidate_wording")),
                    grade=_text(project.get("evidence_grade")),
                    evidence_paths=_lines(project.get("evidence_paths")),
                    boundary=_text(project.get("boundary")),
                    responsibility=_text(project.get("responsibility_level")),
                    transferable=_lines(project.get("transferable_capabilities")),
                    source_label=source_label,
                ),
                "_entry_index": entry_index,
            }
        )

    for education in bundle.get("education") or []:
        if not isinstance(education, dict):
            continue
        school = _text(education.get("school"))
        if school:
            education_skipped.append(school)

    for experience in bundle.get("experiences") or []:
        if not isinstance(experience, dict) or not _text(experience.get("company")):
            continue
        company = _display_name(experience.get("company"))
        role = _text(experience.get("role"))
        if _looks_like_education(company, role):
            education_skipped.append(company)
            continue
        entry_index = add_entry(
            "experiences",
            company,
            _experience_values(experience),
            f"{company} · {role}".strip(" ·"),
        )
        claims.append(
            {
                **_claim_fact(
                    subject=company,
                    category=CLAIM_CATEGORY_EXPERIENCE,
                    problem="",
                    actions=_lines(experience.get("hard_facts")),
                    decisions=[],
                    outcomes=_lines(experience.get("candidate_wording")),
                    tech=[],
                    wording=_lines(experience.get("candidate_wording")),
                    grade=_text(experience.get("evidence_grade")),
                    evidence_paths=_lines(experience.get("evidence_paths")),
                    boundary=_text(experience.get("boundary")),
                    responsibility=_text(experience.get("responsibility_level")),
                    transferable=_lines(experience.get("transferable_capabilities")),
                    source_label=source_label,
                ),
                "_entry_index": entry_index,
            }
        )

    for skill in bundle.get("skills") or []:
        if not isinstance(skill, dict) or not _text(skill.get("name")):
            continue
        add_entry(
            "skills",
            skill.get("name"),
            _skill_values(skill),
            _display_name(skill.get("name")),
            allow_contains=True,
        )

    # 已存在的事实不覆盖：用户可能已经改过口径。按 category+subject+title 判重。
    existing_claims = {
        (row.category, _norm(row.subject), _norm(row.title)): row
        for row in db.query(ClaimRecord).filter(ClaimRecord.deleted_at.is_(None)).all()
    }
    new_claims: list[dict[str, Any]] = []
    for claim in claims:
        key = (claim["category"], _norm(claim["subject"]), _norm(claim["title"]))
        if key in existing_claims:
            skipped_claims.append(claim["title"])
        else:
            new_claims.append(claim)
    return {
        "entry_items": entry_items,
        "claims": new_claims,
        "skipped_claims": skipped_claims,
        "education_skipped": education_skipped,
        "created": created,
        "updated": updated,
    }


def apply_portrait(
    db: Session, bundle: dict[str, Any], *, source_label: str = "个人画像"
) -> dict[str, Any]:
    """按计划写库：先写资料库条目，拿到 entry_id 后再写事实台账。"""
    plan = plan_portrait(db, bundle, source_label=source_label)
    if not plan["entry_items"]:
        return {**plan, "applied": True, "entry_count": 0, "claim_count": 0}

    saved = entry_store.bulk_save_entries(db, plan["entry_items"])
    # 计划与保存结果同序：bulk_save_entries 按输入顺序返回。
    saved_by_index = {index: row for index, row in enumerate(saved)}

    for claim in plan["claims"]:
        entry_index = claim.pop("_entry_index", None)
        row = saved_by_index.get(entry_index) if isinstance(entry_index, int) else None
        entry_id = row.entry_id if row is not None else None
        if entry_id:
            claim["sources"] = [
                *claim.get("sources", []),
                {
                    "type": "reference",
                    "location": entry_id,
                    "public": False,
                    "note": "关联资料库条目（生成基线用）",
                },
            ]
        db.add(ClaimRecord(**claim))
    db.commit()
    return {
        **plan,
        "applied": True,
        "entry_count": len(saved),
        "claim_count": len(plan["claims"]),
    }


def bundle_summary(bundle: dict[str, Any]) -> str:
    """给 CLI dry-run 用的一行人话摘要。"""
    return json.dumps(
        {
            "projects": len(bundle.get("projects") or []),
            "experiences": len(bundle.get("experiences") or []),
            "skills": len(bundle.get("skills") or []),
        },
        ensure_ascii=False,
    )


__all__ = ["apply_portrait", "bundle_summary", "plan_portrait"]
