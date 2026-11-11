// SPDX-License-Identifier: Apache-2.0
/** 备选岗位接口：暂存招聘信息、编辑、按批次挑选后导入岗位广场。 */
import type {
  CandidateCsvImportResult,
  CandidateCsvPreview,
  CandidateCsvRow,
  CandidateJob,
  CandidateJobDetail,
  CandidateJobImportResult,
  CandidateJobPayload,
  CandidateJobUpdatePayload,
} from "../types";
import type { Page } from "../types/common";
import { buildQuery, request, requestRaw } from "./client";

/** 备选岗位列表的排序键（与后端 `sort` 参数一一对应）。 */
export type CandidateJobSort = "created_desc" | "score_desc" | "score_asc";

export function listCandidateJobs(
  params: {
    status?: string;
    keyword?: string;
    /** 只看某一次采集采到的候选（「本次采集结果」）。 */
    collectTaskId?: number;
    /** 查看多条采集记录合并后的候选岗位。 */
    collectTaskIds?: number[];
    limit?: number;
    /** 排序：created_desc（默认）/ score_desc / score_asc（未评分的固定排最后）。 */
    sort?: CandidateJobSort;
  } = {},
): Promise<CandidateJob[]> {
  const { collectTaskId, collectTaskIds, ...rest } = params;
  return request(
    `/candidate-jobs${buildQuery({
      ...rest,
      ...(collectTaskId ? { collect_task_id: collectTaskId } : {}),
      ...(collectTaskIds?.length ? { collect_task_ids: collectTaskIds.join(",") } : {}),
    })}`,
  );
}

export function createCandidateJob(payload: CandidateJobPayload): Promise<CandidateJob> {
  return request("/candidate-jobs", { method: "POST", body: JSON.stringify(payload) });
}

/**
 * 分页列出备选岗位（RF-08）：过滤与排序与旧列表一致，但不受旧端点 300 条兜底上限约束，
 * 长期累积的历史候选仍然全部可达。响应是 `Page{items, total}`。
 */
export function listCandidateJobsPage(
  params: {
    status?: string;
    keyword?: string;
    /** 只看某一次采集采到的候选（「本次采集结果」）。 */
    collectTaskId?: number;
    /** 查看多条采集记录合并后的候选岗位。 */
    collectTaskIds?: number[];
    sort?: CandidateJobSort;
  } = {},
  page: number,
  pageSize: number,
): Promise<Page<CandidateJob>> {
  const { collectTaskId, collectTaskIds, ...rest } = params;
  return request(
    `/candidate-jobs/page${buildQuery({
      ...rest,
      ...(collectTaskId ? { collect_task_id: collectTaskId } : {}),
      ...(collectTaskIds?.length ? { collect_task_ids: collectTaskIds.join(",") } : {}),
      page,
      page_size: pageSize,
    })}`,
  );
}

/** 取单条候选的**完整**内容（含 JD）。列表不带正文，要正文就用它。 */
export function getCandidateJob(id: number): Promise<CandidateJobDetail> {
  return request(`/candidate-jobs/${id}`);
}

export function updateCandidateJob(
  id: number,
  payload: CandidateJobUpdatePayload,
): Promise<CandidateJob> {
  return request(`/candidate-jobs/${id}`, { method: "PUT", body: JSON.stringify(payload) });
}

/** 标记为已导入正式岗位（岗位本身仍走正式的岗位保存接口）。 */
export function markCandidateJobImported(id: number, jobId: number): Promise<CandidateJob> {
  return request(`/candidate-jobs/${id}/imported`, {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

/**
 * 批量导入岗位广场：服务端建岗位并回填关联，**逐条**返回结果。
 *
 * 一次请求而不是逐条调用：勾 10 条要 10 次往返，而且中途失败会留下"导入了一半"的状态。
 */
export function importCandidateJobs(candidateIds: number[]): Promise<CandidateJobImportResult> {
  return request("/candidate-jobs/import", {
    method: "POST",
    body: JSON.stringify({ candidate_ids: candidateIds }),
  });
}

export function deleteCandidateJob(id: number): Promise<void> {
  return request(`/candidate-jobs/${id}`, { method: "DELETE" });
}

/** 当前筛选下全部候选的 id（不分页）：抽屉「全选全部」用；上限由调用方裁决。 */
export function listCandidateJobIds(
  params: {
    status?: string;
    keyword?: string;
    collectTaskId?: number;
    collectTaskIds?: number[];
  } = {},
): Promise<number[]> {
  const { collectTaskId, collectTaskIds, ...rest } = params;
  return request(
    `/candidate-jobs/ids${buildQuery({
      ...rest,
      ...(collectTaskId ? { collect_task_id: collectTaskId } : {}),
      ...(collectTaskIds?.length ? { collect_task_ids: collectTaskIds.join(",") } : {}),
    })}`,
  );
}

/** 把勾选的候选导出成 CSV（返回原始 blob，调用方负责触发下载）。 */
export async function exportCandidatesCsv(candidateIds: number[]): Promise<Blob> {
  const response = await requestRaw("/candidate-jobs/csv/export", {
    method: "POST",
    // requestRaw 不补 Content-Type（见 api/jobs.exportJobsCsv 的注释）：JSON body 必须自带。
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: candidateIds }),
  });
  return response.blob();
}

/** 候选 CSV 第一步：上传文件解析预览（不落库）。 */
export function previewCandidateImport(file: File): Promise<CandidateCsvPreview> {
  const form = new FormData();
  form.append("file", file);
  // 文件上传走 upload 预算（10 分钟）：大 CSV 的传输时间不该挤 15s 的 default 预算。
  return request("/candidate-jobs/csv/import/preview", {
    method: "POST",
    body: form,
    budget: "upload",
  });
}

/** 候选 CSV 第二步：确认提交，逐行建候选并返回账目。 */
export function importCandidatesCsv(rows: CandidateCsvRow[]): Promise<CandidateCsvImportResult> {
  return request("/candidate-jobs/csv/import", { method: "POST", body: JSON.stringify({ rows }) });
}

/**
 * 备选岗位的语义评分任务快照（`/candidate-jobs/score/task`）。
 *
 * 与岗位评分不同：备选岗位在导入前没有 `job_id`，所以分数落在候选表上，任务快照也
 * 是独立的一套（存 AppSetting 单键），不与 `job_match_background_task` 共用。
 */
export interface CandidateScoreTask {
  /** 服务端没有任务时只返回 `{running: false}`，所以它可能缺其他字段。 */
  running: boolean;
  task_id?: string;
  status?: "running" | "completed" | "failed" | "cancelled";
  requested?: number;
  completed?: number;
  failed?: number;
  current_candidate_id?: number | null;
  current_title?: string;
  message?: string;
  error?: string;
  errors?: string[];
}

/** 发起一次后台评分（立刻返回任务快照，前端轮询 `getCandidateScoreTask`）。 */
export function startCandidateScore(payload: {
  candidateIds?: number[];
  force?: boolean;
  resumeId?: number;
}): Promise<CandidateScoreTask> {
  return request("/candidate-jobs/score", {
    method: "POST",
    body: JSON.stringify({
      candidate_ids: payload.candidateIds ?? [],
      force: payload.force ?? false,
      resume_id: payload.resumeId ?? null,
    }),
  });
}

export function getCandidateScoreTask(): Promise<CandidateScoreTask> {
  return request("/candidate-jobs/score/task");
}

export function cancelCandidateScoreTask(): Promise<{ ok: boolean }> {
  return request("/candidate-jobs/score/task/cancel", { method: "POST" });
}
