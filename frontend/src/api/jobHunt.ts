// SPDX-License-Identifier: Apache-2.0
/**
 * 自研求职采集接口（后端 `app/api/job_hunt.py`，prefix `/api/job-hunt`）。
 *
 * 与 `aiJobs.ts`（sidecar 旧路径）并存：status/config 两边语义对应，工作台等
 * 未在自研侧实现的能力继续走旧路径（E19：新老并存，不删旧代码）。
 */
import type {
  JobHuntCollectRequest,
  JobHuntCollectResult,
  JobHuntConfig,
  JobHuntStatus,
  SemanticScore,
} from "../types/jobHunt";
import { request } from "./client";

/** 开关状态 + 已注册平台清单（设置页切换项的数据源）。 */
export function getJobHuntStatus(signal?: AbortSignal): Promise<JobHuntStatus> {
  return request<JobHuntStatus>("/job-hunt/status", { signal });
}

export function getJobHuntConfig(): Promise<JobHuntConfig> {
  return request<JobHuntConfig>("/job-hunt/config");
}

export function saveJobHuntConfig(config: JobHuntConfig): Promise<JobHuntConfig> {
  return request<JobHuntConfig>("/job-hunt/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

/** 执行一次自研采集（落库 + 可选分析）。耗时较长（抓页面），超时放宽。 */
export function runJobHuntCollect(
  payload: JobHuntCollectRequest,
  signal?: AbortSignal,
): Promise<JobHuntCollectResult> {
  return request<JobHuntCollectResult>("/job-hunt/collect", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
    // 采集要真开页面翻页，15s 默认预算必然误超时；用 analysis 档（180s）。
    budget: "analysis",
  });
}

/** 对单个岗位做语义评分（五维 + 封顶）。需要岗位已有 JD 正文。 */
export function scoreJob(jobId: number, force = false): Promise<SemanticScore & { job_id: number; cached: boolean }> {
  return request(`/job-hunt/jobs/${jobId}/score${force ? "?force=true" : ""}`, {
    method: "POST",
    // 评分要调模型，用 analysis 档（180s）。
    budget: "analysis",
  });
}

/** 读已落库的语义评分（未评分时 ok=false）。 */
export function getJobScore(jobId: number): Promise<SemanticScore & { job_id: number }> {
  return request(`/job-hunt/jobs/${jobId}/score`);
}
