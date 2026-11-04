# SPDX-License-Identifier: Apache-2.0
"""画像导入：dry-run 不写库、A/B 确认、C 不采用、entry_id 关联、重复导入幂等。"""

from __future__ import annotations

from app.models.claim import (
    CLAIM_CATEGORY_EXPERIENCE,
    CLAIM_CATEGORY_PROJECT,
    VERIFICATION_CONFIRMED,
    VERIFICATION_REJECTED,
    ClaimRecord,
    can_enter_final,
)
from app.models.profile_entry import ProfileEntry
from app.services.profile import entry_store
from app.services.profile.portrait_import import apply_portrait, plan_portrait

BUNDLE = {
    "projects": [
        {
            "name": "边缘 AI 跌倒检测",
            "role": "算法与部署",
            "start_date": "2025-03",
            "end_date": "2025-08",
            "tech_stack": ["YOLO", "ONNX", "树莓派"],
            "problem": "独居老人跌倒后无人及时发现。",
            "actions": ["训练轻量检测模型", "在树莓派上完成 ONNX 部署"],
            "decisions": ["选择剪枝后的 YOLO 而不是云端大模型"],
            "outcomes": ["端侧推理延迟从 800ms 降到 120ms"],
            "candidate_wording": ["把跌倒检测模型部署到树莓派，端侧延迟降到 120ms"],
            "evidence_grade": "A",
            "evidence_paths": ["03-P3-项目经历-主力两条.md"],
            "boundary": "数据采集由团队完成，本人负责模型训练与部署。",
            "responsibility_level": "负责模块",
            "transferable_capabilities": ["模型轻量化", "端侧部署"],
            "artifact_type": "个人项目",
        },
        {
            "name": "AIGC 内容生产流水线",
            "role": "参与",
            "tech_stack": ["ComfyUI"],
            "problem": "批量生成配图。",
            "actions": ["搭工作流"],
            "outcomes": [],
            "candidate_wording": [],
            "evidence_grade": "C",
            "evidence_paths": [],
            "boundary": "只有口头描述，没有可核对的产出。",
            "responsibility_level": "参与",
        },
    ],
    "education": [
        {
            "school": "哈尔滨信息工程学院",
            "major": "计算机科学与技术",
            "degree": "本科",
            "evidence_grade": "B",
        }
    ],
    "experiences": [
        {
            "company": "哈尔滨信息工程学院",
            "role": "本科 · 计算机科学与技术",
            "hard_facts": ["在读"],
            "evidence_grade": "B",
        },
        {
            "company": "广州某科技公司",
            "role": "AI 应用实习生",
            "start_date": "2025-07",
            "end_date": "2025-09",
            "hard_facts": ["维护提示词模板", "整理评测集"],
            "candidate_wording": ["维护 20+ 提示词模板并整理评测集"],
            "evidence_grade": "B",
            "evidence_paths": ["00-个人画像.md"],
            "boundary": "实习期团队共 4 人，本人负责提示词与评测。",
            "responsibility_level": "参与",
            "transferable_capabilities": ["提示词工程", "评测设计"],
        }
    ],
    "skills": [
        {"name": "Python", "level": "熟练", "category": "编程语言"},
        {"name": "ComfyUI", "level": "会用一点", "category": "AI 工具"},
    ],
    "notes": [],
}


def _entries(db, section: str) -> list[ProfileEntry]:
    return entry_store.list_entries(db, section_key=section)


def _claims(db) -> list[ClaimRecord]:
    return db.query(ClaimRecord).filter(ClaimRecord.deleted_at.is_(None)).all()


def test_plan_does_not_write(db_session):
    plan = plan_portrait(db_session, BUNDLE)

    assert plan["created"] == ["边缘 AI 跌倒检测", "AIGC 内容生产流水线", "广州某科技公司 · AI 应用实习生", "Python", "ComfyUI"]
    assert "哈尔滨信息工程学院" in plan["education_skipped"]
    assert len(plan["claims"]) == 3
    assert _entries(db_session, "projects") == []
    assert _entries(db_session, "experiences") == []
    assert _entries(db_session, "skills") == []
    assert _claims(db_session) == []


def test_apply_links_claims_and_applies_evidence_grades(db_session):
    result = apply_portrait(db_session, BUNDLE)

    assert result["entry_count"] == 5
    assert result["claim_count"] == 3
    projects = _entries(db_session, "projects")
    experiences = _entries(db_session, "experiences")
    skills = _entries(db_session, "skills")
    assert len(projects) == 2
    assert len(experiences) == 1
    assert len(skills) == 2

    claims = {claim.subject: claim for claim in _claims(db_session)}
    assert set(claims) == {"边缘 AI 跌倒检测", "AIGC 内容生产流水线", "广州某科技公司"}

    good = claims["边缘 AI 跌倒检测"]
    assert good.category == CLAIM_CATEGORY_PROJECT
    assert good.verification_status == VERIFICATION_CONFIRMED
    assert can_enter_final(good.verification_status)
    assert "端侧推理延迟" in good.source_fact
    assert good.boundary.startswith("数据采集由团队完成")
    project_ids = {row.entry_id for row in projects}
    assert project_ids & {source["location"] for source in good.sources}

    rejected = claims["AIGC 内容生产流水线"]
    assert rejected.verification_status == VERIFICATION_REJECTED
    assert not can_enter_final(rejected.verification_status)

    experience = claims["广州某科技公司"]
    assert experience.category == CLAIM_CATEGORY_EXPERIENCE
    assert experience.verification_status == VERIFICATION_CONFIRMED
    experience_ids = {row.entry_id for row in experiences}
    assert experience_ids & {source["location"] for source in experience.sources}


def test_reapply_is_idempotent_and_skips_existing_claims(db_session):
    apply_portrait(db_session, BUNDLE)
    counts = (
        len(_entries(db_session, "projects")),
        len(_entries(db_session, "experiences")),
        len(_entries(db_session, "skills")),
        len(_claims(db_session)),
    )

    result = apply_portrait(db_session, BUNDLE)

    assert result["claim_count"] == 0
    assert result["skipped_claims"]
    assert counts == (
        len(_entries(db_session, "projects")),
        len(_entries(db_session, "experiences")),
        len(_entries(db_session, "skills")),
        len(_claims(db_session)),
    )


def test_long_fields_are_clipped_to_profile_limits(db_session):
    apply_portrait(
        db_session,
        {
            "projects": [
                {
                    "name": "长字段项目",
                    "tech_stack": [f"技能{i}" for i in range(80)],
                    "problem": "背景" * 1_500,
                    "actions": ["动作" * 1_500],
                    "evidence_grade": "B",
                }
            ],
            "experiences": [],
            "skills": [],
        },
    )

    row = _entries(db_session, "projects")[0]
    assert len(row.values["projects.tech_stack"]) <= 200
    assert len(row.values["projects.description"]) <= 2000
    assert len(row.values["projects.name"]) <= 200


def test_update_keeps_fields_the_portrait_does_not_provide(db_session):
    entry_store.bulk_save_entries(
        db_session,
        [
            {
                "section_key": "projects",
                "values": {
                    "projects.name": "边缘 AI 跌倒检测",
                    "projects.public_url": "https://example.com/fall-detection",
                },
            }
        ],
    )

    apply_portrait(db_session, BUNDLE)

    row = next(row for row in _entries(db_session, "projects") if row.values["projects.name"] == "边缘 AI 跌倒检测")
    assert row.values["projects.public_url"] == "https://example.com/fall-detection"
    assert row.values["projects.role"] == "算法与部署"


def test_overwrite_names_replaces_project_fields_instead_of_only_filling_blanks(db_session):
    """``overwrite_names`` 点名的项目要**整体覆盖**，不能只补空字段。

    场景：用户在画像里重写了某个项目（例如把零散的内容生产线合并重写成一条），
    此时旧的描述/要点已过时。若仍按"只补空字段"，新内容一个字都进不来 —— 导入
    表面成功（返回 200）却静默无效，是最难查的一类失败。
    """
    entry_store.bulk_save_entries(
        db_session,
        [
            {
                "section_key": "projects",
                "values": {
                    "projects.name": "边缘 AI 跌倒检测",
                    "projects.role": "算法与部署",
                    "projects.description": "旧描述：只有一句话。",
                },
            }
        ],
    )

    plan = plan_portrait(
        db_session, BUNDLE, overwrite_names=["边缘 AI 跌倒检测"]
    )
    project_item = next(
        item for item in plan["entry_items"] if item["section_key"] == "projects"
    )
    # 描述被新内容替换（不是保留旧的）
    assert "旧描述" not in project_item["values"]["projects.description"]
    assert project_item["values"]["projects.description"]


def test_overwrite_only_applies_to_named_projects(db_session):
    """没被点名的项目仍走"只补空字段"，用户手改的内容不会被覆盖。"""
    entry_store.bulk_save_entries(
        db_session,
        [
            {
                "section_key": "projects",
                "values": {
                    "projects.name": "边缘 AI 跌倒检测",
                    "projects.description": "用户手写的描述，不能被导入覆盖。",
                },
            }
        ],
    )

    plan = plan_portrait(db_session, BUNDLE)  # 不传 overwrite_names
    project_item = next(
        item for item in plan["entry_items"] if item["section_key"] == "projects"
    )
    assert project_item["values"]["projects.description"] == "用户手写的描述，不能被导入覆盖。"


def test_project_name_match_allows_contains_to_avoid_duplicates(db_session):
    """项目名只差修饰语时应视为同一条，不能重复建。

    真实事故：画像写「老年人居家康养异常行为检测系统」，资料库里已有
    「基于 ESP32-S3 的居家康养异常行为检测系统」——只按精确名匹配会建出第二条。
    """
    entry_store.bulk_save_entries(
        db_session,
        [
            {
                "section_key": "projects",
                "values": {
                    "projects.name": "基于 ESP32-S3 的居家康养异常行为检测系统",
                    "projects.role": "个人项目",
                },
            }
        ],
    )
    bundle = {
        "projects": [
            {
                "name": "老年人居家康养异常行为检测系统",
                "role": "毕业设计",
                "outcomes": ["10,429 行固件"],
            }
        ]
    }

    plan = plan_portrait(db_session, bundle)
    created = [
        item
        for item in plan["entry_items"]
        if item["section_key"] == "projects" and not item.get("entry_id")
    ]
    assert created == [], f"不应新建条目，实际新建了 {len(created)} 条"


def test_import_does_not_write_project_size(db_session):
    """画像导入**不写** ``projects.project_size``（用户明确要求简历里不要「项目规模」行）。

    字段本身保留在 schema / 编辑器里（用户想手填仍可填），但导入链路不写它 ——
    否则每次重新导入都会把「20 个 API 路由、5 张数据表」这类规模罗列塞回简历，
    纸面上像凑数，也不是用户要展示的东西。
    """
    bundle = {
        "projects": [
            {
                "name": "边缘 AI 跌倒检测",
                "role": "算法与部署",
                "outcomes": ["推理延迟 32ms"],
                "project_size": "12 个 API 路由、3 张表、8000 行代码",
            }
        ]
    }

    apply_portrait(db_session, bundle)

    row = next(
        row
        for row in _entries(db_session, "projects")
        if row.values["projects.name"] == "边缘 AI 跌倒检测"
    )
    assert not str(row.values.get("projects.project_size") or "").strip()
