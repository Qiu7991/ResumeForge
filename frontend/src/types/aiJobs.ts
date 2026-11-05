// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职（BossHunter sidecar，后端 `app/api/ai_jobs.py`）的前端类型。
 *
 * 字段名与后端 Pydantic 模型保持 snake_case（与 `types/aiTask.ts` 同一口径）。
 * 类型层不出现任何 Key/Token 字段——凭据只存在于后端，前端只拿只读引用。
 */

/** sidecar 健康检查（`GET /api/ai-jobs/status` 里的 `sidecar` 段）。 */
export interface SidecarHealth {
  reachable: boolean;
  status: string;
  version: string;
  version_ok: boolean;
  reason: string;
}

/** `ai_jobs_config`（按数据集隔离的连接配置）。 */
export interface AiJobsConfig {
  enabled: boolean;
  engine_python: string;
  engine_repo: string;
  engine_port: number;
  proxy_port: number;
  browser_port: number;
  auto_start: boolean;
  use_resumeforge_llm: boolean;
  auto_import_ready_jobs: boolean;
  last_dataset_id: string;
  engine_version: string;
}

/** `GET /api/ai-jobs/status` 的响应：连接态三问一次答全。 */
export interface AiJobsStatus {
  dataset_id: string;
  config: AiJobsConfig;
  engine_configured: boolean;
  engine_error: string;
  sidecar: SidecarHealth;
  owned_running: boolean;
  port: number;
}

export interface EngineStartResult {
  ok: boolean;
  port: number;
  pid: number | null;
  owned: boolean;
  health: SidecarHealth | null;
}

export interface EngineStopResult {
  ok: boolean;
  stopped: boolean;
}

/** 引擎任务快照（BossHunter `WorkbenchTask.snapshot()` 的对前端投影）。 */
export interface AiWorkbenchTask {
  id: string;
  mode: string;
  label: string;
  status: AiJobTaskStatus;
  logs: string[];
  error: string | null;
  created_at: string;
  updated_at: string;
  deadline_at: string | null;
  stop_reason: string | null;
  stop_requested?: boolean;
  metrics: Record<string, number>;
  progress: Record<string, unknown>;
}

/**
 * AI 任务状态（后端 `normalize_task_status` 归一化后的值域）。
 * 未知引擎状态会被归一成 running，前端不需要兜底分支。
 */
export type AiJobTaskStatus =
  | "running"
  | "stopping"
  | "waiting_confirmation"
  | "paused"
  | "completed"
  | "stopped"
  | "failed";

/** 仍在推进（或需要用户回来处理）的任务状态：轮询与互斥提示据此判断。 */
export const AI_TASK_ACTIVE_STATUSES: readonly AiJobTaskStatus[] = [
  "running",
  "stopping",
  "waiting_confirmation",
  "paused",
];

export function isAiTaskActive(status: string | undefined | null): boolean {
  return !!status && (AI_TASK_ACTIVE_STATUSES as readonly string[]).includes(status);
}

/** 引擎岗位摘要（待确认列表/岗位池共用的工作台内投影）。 */
export interface EngineJobSummary {
  id: string;
  title: string;
  company: string;
  status: string;
  score?: number | null;
  greeting?: string | null;
  source_platform: string;
  /** 后端派生的平台展示名（前端不写死站点 token）。 */
  platform_label?: string;
  /** 后端派生：该平台是否只读（引擎不支持发送）。 */
  platform_read_only?: boolean;
  url?: string | null;
}

export interface SendQuota {
  daily_limit: number;
  sent: number;
  remaining: number;
  exhausted: boolean;
}

/** `GET /api/ai-jobs/workbench` 的响应（透传引擎 `/api/workbench`）。 */
export interface AiJobsWorkbenchState {
  pending_confirmation: EngineJobSummary[];
  pending_greetings: EngineJobSummary[];
  send_errors: EngineJobSummary[];
  needs_resume: EngineJobSummary[];
  send_quota: SendQuota;
  task: AiWorkbenchTask | null;
  last_task: AiWorkbenchTask | null;
}

/** `POST /api/ai-jobs/preflight` 的一条检查结果。 */
export interface AiPreflightCheck {
  key: string;
  label: string;
  ok: boolean;
  message: string;
}

export interface AiPreflightResult {
  checks: AiPreflightCheck[];
  all_ok: boolean;
}

export interface AiConfirmationPayload {
  pending_confirmation: EngineJobSummary[];
  send_quota: SendQuota;
  task: AiWorkbenchTask | Record<string, never>;
}

export interface AiDeliverResult {
  result: AiWorkbenchTask | Record<string, never>;
  tracker_synced: number;
}

/** 五维评分 trace（引擎 `GET /api/jobs/<id>/score-trace` 的对前端投影）。 */
export interface ScoreDimension {
  evidence?: string;
  score?: number;
}

export interface ScoreTrace {
  engine_job_id?: string;
  score?: number;
  dimensions?: Record<string, ScoreDimension> | null;
  caps?: string[];
  hard_gaps?: string[];
  reason?: string;
  /** legacy 引擎没有 trace 时为 true：面板显示"该岗位没有评分详情"。 */
  missing?: boolean;
}

/** 引擎岗位的岗位池映射信息。 */
export interface AiJobLinkInfo {
  job_id: number;
  engine_job_id: string;
}
