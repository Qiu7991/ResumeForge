// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职接口（后端 `app/api/ai_jobs.py`，prefix `/api/ai-jobs`）。
 *
 * 前端不直接访问 sidecar：全部经简历通后端代理，错误文案与降级口径由后端统一。
 */
import type { AiJobsConfig, AiJobsStatus, EngineStartResult, EngineStopResult } from "../types/aiJobs";
import { request } from "./client";

/** 聚合连接状态（引擎配置/sidecar 健康/进程归属）。 */
export function getAiJobsStatus(signal?: AbortSignal): Promise<AiJobsStatus> {
  return request<AiJobsStatus>("/ai-jobs/status", { signal });
}

export function getAiJobsConfig(): Promise<AiJobsConfig> {
  return request<AiJobsConfig>("/ai-jobs/config");
}

export function saveAiJobsConfig(config: AiJobsConfig): Promise<AiJobsConfig> {
  return request<AiJobsConfig>("/ai-jobs/config", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

/** 启动 sidecar（只启动简历通自己拥有的进程）；422 = 可修复的前置条件未满足。 */
export function startEngine(): Promise<EngineStartResult> {
  return request<EngineStartResult>("/ai-jobs/engine/start", { method: "POST", budget: "task" });
}

/** 停止自己启动的 sidecar；幂等。 */
export function stopEngine(): Promise<EngineStopResult> {
  return request<EngineStopResult>("/ai-jobs/engine/stop", { method: "POST", budget: "task" });
}

import type {
  AiConfirmationPayload,
  AiDeliverResult,
  AiJobsWorkbenchState,
  AiPreflightResult,
  EngineJobSummary,
} from "../types/aiJobs";

/** 引擎工作台聚合状态（轮询入口：当前任务/待确认/配额/漏斗）。 */
export function getAiJobsWorkbench(signal?: AbortSignal): Promise<AiJobsWorkbenchState> {
  return request<AiJobsWorkbenchState>("/ai-jobs/workbench", { signal, budget: "task" });
}

/** 启动前聚合检查（六类）；单项失败不拖垮整体。 */
export function runAiPreflight(): Promise<AiPreflightResult> {
  return request<AiPreflightResult>("/ai-jobs/preflight", { method: "POST", budget: "task" });
}

/** 启动 full/collect/monitor 任务；confirm 必填。 */
export function startAiTask(mode: "full" | "collect" | "monitor", confirm: boolean): Promise<unknown> {
  return request("/ai-jobs/tasks", {
    method: "POST",
    body: JSON.stringify({ mode, confirm }),
    budget: "task",
  });
}

/** 停止任务（幂等）。 */
export function stopAiTask(taskId: string): Promise<unknown> {
  return request(`/ai-jobs/tasks/${encodeURIComponent(taskId)}/stop`, {
    method: "POST",
    budget: "task",
  });
}

/** 待确认投递列表 + 发送配额。 */
export function getAiConfirmation(signal?: AbortSignal): Promise<AiConfirmationPayload> {
  return request<AiConfirmationPayload>("/ai-jobs/confirmation", { signal });
}

/** 人工确认后投递；后端二次校验白名单与互斥。 */
export function deliverAiJobs(jobIds: string[]): Promise<AiDeliverResult> {
  return request<AiDeliverResult>("/ai-jobs/deliver", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds, confirm: true }),
    budget: "task",
  });
}

/** 拒绝选中岗位。 */
export function rejectAiJobs(jobIds: string[]): Promise<{ result: unknown }> {
  return request("/ai-jobs/reject", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds }),
    budget: "task",
  });
}

/** 手动全量同步：引擎已发送岗位写回求职进度（幂等）。 */
export function syncAiJobsTracker(): Promise<{ tracker_synced: number }> {
  return request("/ai-jobs/sync", { method: "POST", budget: "task" });
}

import type { ScoreTrace } from "../types/aiJobs";

/** 引擎岗位列表（分页/回收站筛选）。 */
export function getEngineJobs(params: {
  deleted?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}): Promise<{ jobs: EngineJobSummary[]; total: number }> {
  const query = new URLSearchParams({
    deleted: params.deleted ?? "active",
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  return request(`/ai-jobs/engine-jobs?${query.toString()}`, { signal: params.signal });
}

/** 引擎岗位详情。 */
export function getEngineJobDetail(engineJobId: string): Promise<EngineJobSummary> {
  return request<EngineJobSummary>(`/ai-jobs/engine-jobs/${encodeURIComponent(engineJobId)}`);
}

/** 导入引擎岗位到岗位池（可选只导入选中 ids）。 */
export function importEngineJobs(engineJobIds: string[] = []): Promise<{ created: number; linked_existing: number; skipped_unimportable: number }> {
  return request("/ai-jobs/jobs/import", {
    method: "POST",
    body: JSON.stringify({ engine_job_ids: engineJobIds }),
    budget: "task",
  });
}

/** 五维评分 trace。 */
export function getEngineScoreTrace(engineJobId: string): Promise<ScoreTrace> {
  return request<ScoreTrace>(`/ai-jobs/engine-jobs/${encodeURIComponent(engineJobId)}/score-trace`);
}

export function getEngineGreeting(engineJobId: string): Promise<{ greeting: string; greeting_confirmed: boolean }> {
  return request(`/ai-jobs/engine-jobs/${encodeURIComponent(engineJobId)}/greeting`);
}

export function saveEngineGreeting(engineJobId: string, greeting: string): Promise<{ greeting: string; greeting_confirmed: boolean }> {
  return request(`/ai-jobs/engine-jobs/${encodeURIComponent(engineJobId)}/greeting`, {
    method: "POST",
    body: JSON.stringify({ greeting }),
    budget: "task",
  });
}

export function confirmEngineGreeting(engineJobId: string): Promise<{ greeting_confirmed: boolean }> {
  return request(`/ai-jobs/engine-jobs/${encodeURIComponent(engineJobId)}/greeting/confirm`, {
    method: "POST",
    budget: "task",
  });
}

/** 上传最新通用简历给引擎（哈希缓存）。 */
export function syncResumeToEngine(): Promise<{ uploaded: boolean; reason: string }> {
  return request("/ai-jobs/resume/sync", { method: "POST", budget: "task" });
}


/** 回复监测列表（未处理回复 + 会话）。 */
export function getAiReplies(signal?: AbortSignal): Promise<{
  items: Record<string, unknown>[];
  unresolved_count: number;
}> {
  return request("/ai-jobs/replies", { signal, budget: "task" });
}

function replyAction(historyId: string, action: "open-chat" | "prepare-reply" | "reply" | "dismiss", content = ""): Promise<unknown> {
  return request(`/ai-jobs/replies/${encodeURIComponent(historyId)}/${action}`, {
    method: "POST",
    body: JSON.stringify({ content }),
    budget: "task",
  });
}

export const openReplyChat = (historyId: string) => replyAction(historyId, "open-chat");
export const prepareReply = (historyId: string) => replyAction(historyId, "prepare-reply");
export const recordReply = (historyId: string, content: string) => replyAction(historyId, "reply", content);
export const dismissReply = (historyId: string) => replyAction(historyId, "dismiss");

/** 把简历通全局 LLM Profile 同步给引擎。 */
export function syncLlmToEngine(): Promise<{ synced: boolean; model: string; service: string }> {
  return request("/ai-jobs/config/sync-llm", { method: "POST", budget: "task" });
}

/** 引擎历史记录（采集/评分/任务/投递）。 */
export function getAiHistory(signal?: AbortSignal): Promise<Record<string, unknown>[]> {
  return request("/ai-jobs/history", { signal, budget: "task" });
}
