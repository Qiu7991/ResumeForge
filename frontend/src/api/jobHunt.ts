// SPDX-License-Identifier: Apache-2.0
/**
 * 自研求职采集接口（后端 `app/api/job_hunt.py`，prefix `/api/job-hunt`）。
 *
 * 与 `aiJobs.ts`（sidecar 旧路径）并存：status/config 两边语义对应，工作台等
 * 未在自研侧实现的能力继续走旧路径（E19：新老并存，不删旧代码）。
 */
import type {
  CollectTaskResult,
  CollectTaskSnapshot,
  JobHuntBlocklist,
  JobHuntCollectRequest,
  JobHuntCollectResult,
  JobHuntConfig,
  JobHuntPersistLedger,
  JobHuntStatus,
  JobHuntStub,
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
export function scoreJob(
  jobId: number,
  force = false,
  resumeId?: number | null,
): Promise<SemanticScore & { job_id: number; cached: boolean }> {
  const params = new URLSearchParams();
  if (force) params.set("force", "true");
  if (resumeId != null) params.set("resume_id", String(resumeId));
  const query = params.toString();
  return request(`/job-hunt/jobs/${jobId}/score${query ? `?${query}` : ""}`, {
    method: "POST",
    // 评分要调模型，用 analysis 档（180s）。
    budget: "analysis",
  });
}

/** 读已落库的语义评分（未评分时 ok=false）。 */
export function getJobScore(jobId: number): Promise<SemanticScore & { job_id: number }> {
  return request(`/job-hunt/jobs/${jobId}/score`);
}

/** 把预览里勾选的卡片导入岗位广场（只导勾中的）。 */
export function importSelectedJobs(payload: {
  site_key: string;
  stubs: JobHuntStub[];
  backfill_jd?: boolean;
}): Promise<{ persisted: JobHuntPersistLedger; imported_ids: number[]; origin_source: string }> {
  return request("/job-hunt/import", {
    method: "POST",
    body: JSON.stringify(payload),
    budget: "analysis",
  });
}

export function getBlocklist(): Promise<JobHuntBlocklist> {
  return request<JobHuntBlocklist>("/job-hunt/blocklist");
}

export function saveBlocklist(config: JobHuntBlocklist): Promise<JobHuntBlocklist> {
  return request<JobHuntBlocklist>("/job-hunt/blocklist", {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

/** 启动后台采集任务（可暂停/停止/看进度）。 */
export function startCollectTask(payload: {
  site_key: string;
  keywords?: string;
  city?: string;
  max_pages?: number;
  city_code?: string;
  /**
   * 采集结果是否落进备选岗位暂存区。**服务端默认 true**（方案 3：采完自动入库、
   * 补 JD、评分，用户按分数决定导入哪些）。传 false 只用于"只要一轮列表、不留痕"。
   */
  persist?: boolean;
  /** 落库后是否自动补 JD + 评分。关掉 = 只入库不评分。 */
  auto_score?: boolean;
  /** 用哪份简历评分；不传走设置里的默认简历。 */
  resume_id?: number | null;
  /**
   * 多关键词：每个词各自翻到 `max_pages`（与 BossHunter 的笛卡尔积语义一致）。
   *
   * 单关键词翻到底就那十几条，第二轮开始全是重复；多个相关词能显著扩大采集面。
   * 传了它 `keywords` 就被忽略。
   */
  keyword_list?: string[];
  /** 站点筛选：`{分组: [中文标签]}`，如 `{experience: ["应届生"], degree: ["本科"]}`。 */
  filters?: Record<string, string[]>;
  /** 最新优先（BOSS 的 `sortType=2`）。不加它每次翻到的都是默认排序里的同一批。 */
  sort?: "newest" | "default";
}): Promise<CollectTaskSnapshot> {
  return request<CollectTaskSnapshot>("/job-hunt/collect/task", {
    method: "POST",
    body: JSON.stringify(payload),
    budget: "task",
  });
}

/**
 * 当前还没结束的采集任务（没有则 `{active:false}`）。
 *
 * 用途只有一个：**页面刷新后把进度接回来**。任务快照原本只在前端内存里，
 * 刷一下页面就 null——但采集/补 JD/评分在后台还在跑，用户只看到进度凭空消失。
 */
export function getActiveCollectTask(): Promise<{ active: boolean } & Partial<CollectTaskSnapshot>> {
  return request("/job-hunt/collect/active");
}

export function getCollectTask(taskId: string): Promise<CollectTaskSnapshot> {
  return request<CollectTaskSnapshot>(`/job-hunt/collect/task/${taskId}`, { budget: "default" });
}

export function getCollectTaskResult(taskId: string): Promise<CollectTaskResult> {
  return request<CollectTaskResult>(`/job-hunt/collect/task/${taskId}/result`, {
    budget: "default",
  });
}

export function controlCollectTask(
  taskId: string,
  action: "pause" | "resume" | "stop",
): Promise<CollectTaskSnapshot> {
  return request<CollectTaskSnapshot>(`/job-hunt/collect/task/${taskId}/${action}`, {
    method: "POST",
    budget: "default",
  });
}
