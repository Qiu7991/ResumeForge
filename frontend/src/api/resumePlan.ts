// SPDX-License-Identifier: Apache-2.0
/** 岗位生成计划：先分析 JD 与资料匹配，再带 plan_id 生成。 */
import type { GenerationPlan } from "../types/generationPlan";
import { request } from "./client";

export interface CreateGenerationPlanPayload {
  job_id: number;
  base_resume_id?: number | null;
  custom_instruction?: string;
}

export function createGenerationPlan(
  payload: CreateGenerationPlanPayload,
): Promise<GenerationPlan> {
  return request("/resumes/generation-plan", {
    method: "POST",
    body: JSON.stringify(payload),
    budget: "analysis",
  });
}

export function getGenerationPlan(planId: number): Promise<GenerationPlan> {
  return request(`/resumes/generation-plan/${planId}`);
}

export function updateGenerationPlan(
  planId: number,
  selectedEvidenceIds: string[],
): Promise<GenerationPlan> {
  return request(`/resumes/generation-plan/${planId}`, {
    method: "PATCH",
    body: JSON.stringify({ selected_evidence_ids: selectedEvidenceIds }),
  });
}
