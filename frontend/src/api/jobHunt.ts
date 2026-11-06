// SPDX-License-Identifier: Apache-2.0
/**
 * 自研求职采集接口（后端 `app/api/job_hunt.py`，prefix `/api/job-hunt`）。
 *
 * 与 `aiJobs.ts`（sidecar 旧路径）并存：status/config 两边语义对应，工作台等
 * 未在自研侧实现的能力继续走旧路径（E19：新老并存，不删旧代码）。
 */
import type { JobHuntConfig, JobHuntStatus } from "../types/jobHunt";
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
