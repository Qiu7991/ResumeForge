// SPDX-License-Identifier: Apache-2.0
/** 岗位生成计划：JD 要求 → 直接/可迁移证据 → 覆盖与缺口（与后端 schemas/generation_plan.py 对齐）。 */

export type PlanRequirementType = "hard_skill" | "responsibility" | "domain" | "soft";
export type PlanMatch = "direct" | "transferable" | "none";
export type PlanRefType = "project" | "experience" | "education" | "claim";

export interface GenerationPlanRequirement {
  id: string;
  text: string;
  type: PlanRequirementType;
  weight: number;
  keywords: string[];
}

export interface GenerationPlanEvidence {
  id: string;
  requirement_id: string;
  ref_type: PlanRefType;
  ref_id: string;
  ref_name: string;
  match: PlanMatch;
  rationale: string;
  fact_quotes: string[];
  selected: boolean;
}

export interface GenerationPlanCoverage {
  direct: number;
  transferable: number;
  gaps: string[];
  by_requirement: Record<
    string,
    { status: "direct" | "transferable" | "gap"; direct: number; transferable: number }
  >;
}

export interface GenerationPlan {
  id: number;
  job_id: number | null;
  base_resume_id: number | null;
  resume_id: number | null;
  requirements: GenerationPlanRequirement[];
  evidence: GenerationPlanEvidence[];
  coverage: GenerationPlanCoverage;
  warnings: string[];
  model: string;
  status: string;
  error: string;
  created_at: string | null;
  updated_at: string | null;
}
