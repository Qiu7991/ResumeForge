/**
 * 通用 AI 任务的模块级登记表（后端 `ai_task` 表）。
 *
 * 与 `utils/backgroundTasks`（简历生成专用）并列：这里只追踪通用 AI 任务，不替换既有
 * 登记表。为什么需要它：任务一建起来就与 HTTP 连接无关（后端在独立线程里跑），前端必须
 * 有一处**不随组件卸载而停**的轮询，否则"关掉弹窗后完成会提醒"又是一句空话。
 *
 * 轮询期间提供可订阅列表（页头任务入口），终态时统一弹通知并调用调用方的收尾回调。
 */
import { ApiError } from "../api/client";
import { cancelAiTask, createAiTask, getAiTask, listActiveAiTasks } from "../api/aiTasks";
import type { AiTaskSnapshot, AiTaskStatus } from "../types/aiTask";
import { notifyTaskDone } from "./taskNotify";

export interface AiTaskView {
  id: number;
  kind: string;
  label: string;
  status: AiTaskStatus;
  progress: number;
  message: string;
  error: string;
}

type Listener = (tasks: AiTaskView[]) => void;

export const AI_TASK_POLL_INTERVAL_MS = 1500;

const tasks = new Map<number, AiTaskView>();
const finishHandlers = new Map<number, (task: AiTaskView) => void>();
const listeners = new Set<Listener>();
let timer: number | null = null;

let cached: AiTaskView[] = [];
let cacheDirty = true;

function snapshot(): AiTaskView[] {
  if (cacheDirty) {
    cached = [...tasks.values()];
    cacheDirty = false;
  }
  return cached;
}

function emit(): void {
  cacheDirty = true;
  const current = snapshot();
  for (const listener of listeners) listener(current);
}

function toView(task: AiTaskSnapshot, fallbackLabel: string): AiTaskView {
  return {
    id: task.id,
    kind: task.kind,
    label: task.label || fallbackLabel,
    status: task.status,
    progress: task.progress,
    message: task.message,
    error: task.error,
  };
}

function isTerminal(status: AiTaskStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "canceled";
}

function stopPollingIfIdle(): void {
  if (tasks.size > 0 || timer === null) return;
  window.clearInterval(timer);
  timer = null;
}

function ensurePolling(): void {
  if (timer !== null || typeof window === "undefined") return;
  timer = window.setInterval(() => void tick(), AI_TASK_POLL_INTERVAL_MS);
}

async function tick(): Promise<void> {
  if (tasks.size === 0) {
    stopPollingIfIdle();
    return;
  }
  await Promise.all(
    [...tasks.keys()].map(async (id) => {
      try {
        applyUpdate(id, await getAiTask(id));
      } catch (error) {
        // 404 = 任务记录被清理（换数据集/恢复备份）：移除条目，避免页头永久转圈。
        if (error instanceof ApiError && error.status === 404) {
          removeTask(id);
        }
        // 其它错误（后端短暂不可用）下一轮继续。
      }
    }),
  );
}

function applyUpdate(id: number, latest: AiTaskSnapshot): void {
  const existing = tasks.get(id);
  if (!existing) return;
  const next = toView(latest, existing.label);
  if (isTerminal(next.status)) {
    finish(id, next);
    return;
  }
  tasks.set(id, next);
  emit();
}

function finish(id: number, task: AiTaskView): void {
  // 先取回调再移除：removeTask 会清掉 finishHandlers。
  const handler = finishHandlers.get(id);
  removeTask(id);
  if (task.status === "succeeded") {
    notifyTaskDone({
      title: `${task.label}完成`,
      description:
        task.kind === "job_match"
          ? "匹配结论已保存，回到岗位详情点「匹配度分析」即可查看。"
          : "任务已完成，相关结果已保存。",
    });
  } else if (task.status === "failed") {
    notifyTaskDone({
      kind: "error",
      title: `${task.label}失败`,
      description: task.error || "请稍后重试。",
    });
  } else {
    notifyTaskDone({ kind: "warning", title: `${task.label}已取消` });
  }
  handler?.(task);
}

function removeTask(id: number): void {
  tasks.delete(id);
  finishHandlers.delete(id);
  stopPollingIfIdle();
  emit();
}

/** 登记并启动一个 AI 任务；返回初始快照。 */
export async function startAiTask(input: {
  kind: string;
  payload: Record<string, unknown>;
  label: string;
  onFinished?: (task: AiTaskView) => void;
}): Promise<AiTaskSnapshot> {
  const task = await createAiTask({
    kind: input.kind,
    payload: input.payload,
    label: input.label,
  });
  tasks.set(task.id, toView(task, input.label));
  if (input.onFinished) finishHandlers.set(task.id, input.onFinished);
  ensurePolling();
  emit();
  void tick();
  return task;
}

export async function cancelAiTaskEntry(id: number): Promise<AiTaskSnapshot> {
  return cancelAiTask(id);
}

/** 刷新后恢复仍在跑的任务（页头入口与轮询一起接上）。 */
export async function restoreActiveAiTasks(): Promise<void> {
  try {
    const active = await listActiveAiTasks();
    for (const task of active) {
      if (!tasks.has(task.id)) tasks.set(task.id, toView(task, "AI 任务"));
    }
    if (tasks.size > 0) {
      ensurePolling();
      emit();
    }
  } catch {
    // 后端不可用/没有任务：保持空表，不影响页面。
  }
}

/** 手动推进一轮轮询（测试用，避免等真实计时器）。 */
export async function tickAiTasks(): Promise<void> {
  await tick();
}

export function getAiTasks(): AiTaskView[] {
  return snapshot();
}

export function subscribeAiTasks(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 仅供测试：清空登记表与计时器。 */
export function resetAiTasks(): void {
  tasks.clear();
  finishHandlers.clear();
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
  emit();
}
