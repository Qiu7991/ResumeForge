# SPDX-License-Identifier: Apache-2.0
"""岗位生成计划 Schema：JD 要求、证据映射与覆盖结论。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RequirementType = Literal["hard_skill", "responsibility", "domain", "soft"]
MatchType = Literal["direct", "transferable", "none"]
RefType = Literal["project", "experience", "claim"]


class PlanRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=16)
    text: str = Field(min_length=1, max_length=500)
    type: RequirementType = "responsibility"
    weight: int = Field(default=3, ge=1, le=5)
    keywords: list[str] = Field(default_factory=list, max_length=20)


class PlanEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="", max_length=160)
    requirement_id: str = Field(default="", max_length=16)
    ref_type: RefType = "claim"
    ref_id: str = Field(default="", max_length=64)
    ref_name: str = Field(default="", max_length=200)
    match: MatchType = "none"
    rationale: str = Field(default="", max_length=1000)
    fact_quotes: list[str] = Field(default_factory=list, max_length=4)
    # 计划确认时附带的规范资料原文（项目描述/技术栈/日期），让「底稿 + 证据补全」
    # 不只知道一句 quote，还能把新项目按资料库的字段补进简历。不对外展示。
    source_text: str = Field(default="", max_length=1200)
    selected: bool = False


class GenerationPlanCreate(BaseModel):
    job_id: int = Field(ge=1)
    base_resume_id: int | None = Field(default=None, ge=1)
    custom_instruction: str = Field(default="", max_length=2000)


class GenerationPlanSelection(BaseModel):
    """人工换项目：只允许在计划已给出的候选里改 selected。"""

    selected_evidence_ids: list[str] = Field(default_factory=list, max_length=200)


class GenerationPlanOut(BaseModel):
    id: int
    job_id: int | None = None
    base_resume_id: int | None = None
    resume_id: int | None = None
    requirements: list[PlanRequirement] = Field(default_factory=list)
    evidence: list[PlanEvidence] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    model: str = ""
    status: str = "ready"
    error: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "GenerationPlanCreate",
    "GenerationPlanOut",
    "GenerationPlanSelection",
    "MatchType",
    "PlanEvidence",
    "PlanRequirement",
    "RefType",
    "RequirementType",
]
