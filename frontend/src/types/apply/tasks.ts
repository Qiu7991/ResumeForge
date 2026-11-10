// SPDX-License-Identifier: Apache-2.0
// ===== ② 任务状态机 =====
export type TaskKind = "collect" | "apply";
export type TaskStatus =
  "pending" | "running" | "paused" | "breaker_paused" | "completed" | "stopped" | "failed";
export type TaskItemStatus = "pending" | "running" | "success" | "failed" | "skipped";
/**
 * 队列条目状态。
 *
 * `failed`（2026-11-10）：投递**失败**。与 `skipped` 的区别是用户能不能不管——
 * `skipped` 是"刻意没投"（岗位已关闭 / 招呼语缺失 / 同公司本批已投），不用管；
 * `failed` 是"投了但没成"（页面结构变化等），值得重试。
 */
export type QueueStatus = "pending" | "skipped" | "done" | "failed";
export type BrowserState = "stopped" | "starting" | "running" | "unknown";

export const TASK_STATUS_META: Record<TaskStatus, { label: string; color: string }> = {
  pending: { label: "等待中", color: "default" },
  running: { label: "进行中", color: "processing" },
  paused: { label: "已暂停", color: "warning" },
  breaker_paused: { label: "连续失败过多，已自动暂停", color: "error" },
  completed: { label: "已完成", color: "success" },
  stopped: { label: "已停止", color: "default" },
  failed: { label: "失败", color: "error" },
};

export const TASK_ITEM_STATUS_META: Record<TaskItemStatus, { label: string; color: string }> = {
  pending: { label: "待投递", color: "default" },
  running: { label: "进行中", color: "processing" },
  success: { label: "成功", color: "success" },
  failed: { label: "失败", color: "error" },
  skipped: { label: "已跳过", color: "default" },
};

export const QUEUE_STATUS_META: Record<QueueStatus, { label: string; color: string }> = {
  pending: { label: "待投递", color: "default" },
  skipped: { label: "已跳过", color: "default" },
  done: { label: "已投递", color: "success" },
  // i18n-ok: label 字段是死代码（界面走 QUEUE_STATUS_LABEL_KEYS），保留只为与其它三项同形。
  failed: { label: "", color: "error" },
};

export const BROWSER_STATE_META: Record<BrowserState, { label: string; color: string }> = {
  stopped: { label: "未启动", color: "default" },
  starting: { label: "启动中", color: "processing" },
  running: { label: "运行中", color: "success" },
  unknown: { label: "状态未知", color: "warning" },
};
