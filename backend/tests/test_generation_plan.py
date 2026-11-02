# SPDX-License-Identifier: Apache-2.0
"""生成计划：证据引用必须可核对、缺口不硬凑、人工换项目只改 selected。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app.models.claim import (
    CLAIM_CATEGORY_PROJECT,
    VERIFICATION_CONFIRMED,
    ClaimRecord,
)
from app.models.generation_plan import ResumeGenerationPlan
from app.schemas.generation_plan import (
    GenerationPlanSelection,
    PlanEvidence,
    PlanRequirement,
)
from app.services.profile import entry_store
from app.services.resume.generate_snapshot import freeze_generation_snapshot
from app.services.resume.generation_plan import (
    apply_selection,
    build_candidates,
    build_plan_block,
    create_plan,
    validate_plan,
)


def _seed(db):
    project = entry_store.bulk_save_entries(
        db,
        [
            {
                "section_key": "projects",
                "values": {
                    "projects.name": "边缘 AI 跌倒检测",
                    "projects.role": "算法与部署",
                    "projects.tech_stack": "YOLO、ONNX、树莓派",
                    "projects.description": "把跌倒检测模型部署到树莓派，端侧推理延迟 120ms。",
                },
            },
            {
                "section_key": "experiences",
                "values": {
                    "experiences.company": "广州某科技公司",
                    "experiences.title": "AI 应用实习生",
                    "experiences.description": "维护提示词模板并整理评测集。",
                },
            },
            {
                "section_key": "educations",
                "values": {
                    "educations.school": "哈尔滨信息工程学院",
                    "educations.major": "计算机科学与技术",
                    "educations.degree": "本科",
                },
            },
            {
                "section_key": "skills",
                "values": {"skills.name": "Python", "skills.level": "熟练"},
            },
        ],
    )
    by_section = {row.section_key: row for row in project}
    claim = ClaimRecord(
        title="边缘 AI 跌倒检测 · 项目事实",
        category=CLAIM_CATEGORY_PROJECT,
        subject="边缘 AI 跌倒检测",
        source_fact="把剪枝后的 YOLO 转成 ONNX 部署到树莓派，端侧推理延迟从 800ms 降到 120ms。",
        candidate_wording="端侧推理延迟从 800ms 降到 120ms。",
        sources=[
            {
                "type": "reference",
                "location": by_section["projects"].entry_id,
                "public": False,
            }
        ],
        verification_status=VERIFICATION_CONFIRMED,
        responsibility_level="负责模块",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return by_section, claim


def test_candidates_include_entries_skills_and_linked_claims(db_session):
    by_section, claim = _seed(db_session)
    consumed = freeze_generation_snapshot(db_session).consumed

    candidates = build_candidates(db_session, consumed)
    refs = {(item["ref_type"], item["ref_id"]) for item in candidates}

    assert ("project", by_section["projects"].entry_id) in refs
    assert ("experience", by_section["experiences"].entry_id) in refs
    assert ("claim", str(claim.id)) in refs
    assert ("education", by_section["educations"].entry_id) in refs
    assert ("claim", f"skill:{by_section['skills'].entry_id}") in refs
    claim_candidate = next(item for item in candidates if item["ref_id"] == str(claim.id))
    assert "树莓派" in claim_candidate["source_text"]


def test_validate_plan_drops_fabricated_quote_and_keeps_gap(db_session):
    by_section, claim = _seed(db_session)
    consumed = freeze_generation_snapshot(db_session).consumed
    candidates = build_candidates(db_session, consumed)
    project_id = by_section["projects"].entry_id

    requirements = [
        PlanRequirement(
            id="R1", text="端侧模型部署", type="hard_skill", weight=5, keywords=["ONNX"]
        ),
        PlanRequirement(
            id="R2", text="Kubernetes 集群运维", type="hard_skill", weight=5, keywords=["K8s"]
        ),
    ]
    evidence = [
        PlanEvidence(
            requirement_id="R1",
            ref_type="project",
            ref_id=project_id,
            match="direct",
            fact_quotes=["把跌倒检测模型部署到树莓派，端侧推理延迟 120ms。"],
            selected=True,
        ),
        PlanEvidence(
            requirement_id="R2",
            ref_type="claim",
            ref_id=str(claim.id),
            match="none",
            rationale="没有 K8s 经历",
            fact_quotes=[],
            selected=False,
        ),
        PlanEvidence(
            requirement_id="R1",
            ref_type="project",
            ref_id="missing",
            match="direct",
            fact_quotes=["伪造"],
        ),
    ]

    cleaned_requirements, cleaned_evidence, coverage, warnings = validate_plan(
        requirements, evidence, candidates
    )

    assert [item.id for item in cleaned_requirements] == ["R1", "R2"]
    assert len(cleaned_evidence) == 2
    assert cleaned_evidence[0].selected is True
    assert cleaned_evidence[0].fact_quotes
    assert cleaned_evidence[1].match == "none"
    assert coverage["gaps"] == ["R2"]
    assert any("不存在" in warning for warning in warnings)


def test_validate_plan_replaces_paraphrased_quote_with_source_snippet(db_session):
    by_section, _ = _seed(db_session)
    consumed = freeze_generation_snapshot(db_session).consumed
    candidates = build_candidates(db_session, consumed)

    requirements = [
        PlanRequirement(
            id="R1", text="端侧模型部署", type="hard_skill", weight=5, keywords=["树莓派"]
        )
    ]
    evidence = [
        PlanEvidence(
            requirement_id="R1",
            ref_type="project",
            ref_id=by_section["projects"].entry_id,
            match="direct",
            fact_quotes=["我独立把模型部署到了树莓派"],
        )
    ]

    _, cleaned, coverage, warnings = validate_plan(requirements, evidence, candidates)

    assert cleaned[0].fact_quotes
    assert cleaned[0].fact_quotes[0] in candidates[0]["source_text"]
    assert coverage["by_requirement"]["R1"]["status"] == "direct"
    assert any("换成原文" in warning for warning in warnings)


def test_plan_block_is_explicit_about_transferable_and_gaps():
    plan = ResumeGenerationPlan(
        requirements=[
            PlanRequirement(
                id="R1", text="嵌入式部署", type="hard_skill", weight=5
            ).model_dump(),
            PlanRequirement(
                id="R2", text="Kubernetes", type="hard_skill", weight=4
            ).model_dump(),
        ],
        evidence=[
            PlanEvidence(
                id="R1:project:p1",
                requirement_id="R1",
                ref_type="project",
                ref_id="p1",
                ref_name="边缘 AI 跌倒检测",
                match="transferable",
                fact_quotes=["端侧推理延迟从 800ms 降到 120ms"],
                selected=True,
            ).model_dump(),
            PlanEvidence(
                id="R2:claim:c1",
                requirement_id="R2",
                ref_type="claim",
                ref_id="c1",
                ref_name="某经历",
                match="direct",
                fact_quotes=["不应出现"],
                selected=False,
            ).model_dump(),
        ],
    )

    block = build_plan_block(plan)

    assert "可迁移" in block
    assert "不能升格" in block
    assert "缺口" in block
    assert "不应出现" not in block


def test_apply_selection_caps_two_per_requirement_and_recomputes_coverage():
    plan = ResumeGenerationPlan(
        requirements=[
            PlanRequirement(id="R1", text="A", type="hard_skill", weight=5).model_dump()
        ],
        evidence=[
            PlanEvidence(
                id="R1:project:a",
                requirement_id="R1",
                ref_type="project",
                ref_id="a",
                ref_name="A",
                match="transferable",
                fact_quotes=["quote a"],
            ).model_dump(),
            PlanEvidence(
                id="R1:project:b",
                requirement_id="R1",
                ref_type="project",
                ref_id="b",
                ref_name="B",
                match="direct",
                fact_quotes=["quote b"],
            ).model_dump(),
            PlanEvidence(
                id="R1:project:c",
                requirement_id="R1",
                ref_type="project",
                ref_id="c",
                ref_name="C",
                match="direct",
                fact_quotes=["quote c"],
            ).model_dump(),
        ],
        coverage={},
    )

    apply_selection(
        plan,
        GenerationPlanSelection(
            selected_evidence_ids=["R1:project:a", "R1:project:b", "R1:project:c"]
        ),
    )

    selected = [item for item in plan.evidence if item["selected"]]
    assert len(selected) == 2
    assert {item["ref_id"] for item in selected} == {"b", "c"}
    assert plan.coverage["direct"] == 2


class FakeProvider:
    def __init__(self, response: dict):
        self.config = SimpleNamespace(model="fake-plan-model")
        self.response = response

    async def chat(self, messages, *, thinking=False):  # noqa: ARG002
        return json.dumps(self.response, ensure_ascii=False)


@pytest.mark.asyncio
async def test_create_plan_persists_validated_plan(db_session):
    by_section, _ = _seed(db_session)
    consumed = freeze_generation_snapshot(db_session).consumed
    project_id = by_section["projects"].entry_id
    provider = FakeProvider(
        {
            "requirements": [
                {
                    "id": "R1",
                    "text": "端侧模型部署",
                    "type": "hard_skill",
                    "weight": 5,
                    "keywords": ["树莓派"],
                }
            ],
            "evidence": [
                {
                    "requirement_id": "R1",
                    "ref_type": "project",
                    "ref_id": project_id,
                    "match": "direct",
                    "rationale": "项目里有树莓派部署",
                    "fact_quotes": ["把跌倒检测模型部署到树莓派，端侧推理延迟 120ms。"],
                    "selected": True,
                }
            ],
            "notes": ["没有 K8s 经历"],
        }
    )
    # Job 只需要 build_job_prompt_text 读取的字段；用真实模型太笨重。
    from app.models.job import Job

    real_job = Job(
        id=1,
        title="嵌入式 AI 工程师",
        company="示例公司",
        location="广州",
        job_type="校招",
        description="负责端侧模型部署",
        requirements="熟悉 ONNX / 树莓派",
    )
    db_session.add(real_job)
    db_session.commit()

    plan = await create_plan(
        db_session,
        job=real_job,
        base_resume_id=None,
        custom_instruction="",
        provider=provider,
        consumed=consumed,
    )

    assert plan.id is not None
    assert plan.model == "fake-plan-model"
    assert plan.requirements[0]["id"] == "R1"
    assert plan.evidence[0]["selected"] is True
    assert plan.coverage["by_requirement"]["R1"]["status"] == "direct"
    assert any("模型提示" in item for item in plan.warnings)
    assert db_session.get(ResumeGenerationPlan, plan.id) is not None


def test_plan_coverage_note_lists_selected_projects_not_written():
    from app.models.generation_plan import ResumeGenerationPlan
    from app.services.resume.generation_plan import build_plan_coverage_note

    plan = ResumeGenerationPlan(
        evidence=[
            PlanEvidence(
                id="R1:project:p1",
                requirement_id="R1",
                ref_type="project",
                ref_id="p1",
                ref_name="民生消费类内容账号",
                match="direct",
                fact_quotes=["17 篇长文"],
                selected=True,
            ).model_dump(),
            PlanEvidence(
                id="R2:project:p2",
                requirement_id="R2",
                ref_type="project",
                ref_id="p2",
                ref_name="AI 简历工作台",
                match="direct",
                fact_quotes=["20 个 API 路由"],
                selected=True,
            ).model_dump(),
        ]
    )

    note = build_plan_coverage_note(
        plan, {"summary": "AI 简历工作台", "projects": [{"name": "AI 简历工作台"}]}
    )

    assert note is not None
    assert note["section"] == "job_plan"
    assert note["names"] == ["民生消费类内容账号"]
