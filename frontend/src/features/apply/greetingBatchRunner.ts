// SPDX-License-Identifier: Apache-2.0
/**
 * 投递台的「批量按岗位生成招呼语」执行器：一次只跑一个条目，跑完再跑下一个。
 *
 * 为什么串行：每个条目都是一次真实模型调用（20–60 秒），并发发出去时本地模型往往只能
 * 排队，用户看到的是"全都卡住"，失败也分不清是哪一条。串行还能中途停：当前条目跑完
 * 就不再取下一条。
 *
 * 为什么状态放在模块级：用户切到别的页面再回来，进度还在；跑完统一弹通知。与
 * `features/jobs/jobBulkAiRunner` 同一套形态，只是对象从岗位换成队列条目。
 *
 * shortcut: 循环跑在前端进程里，关掉整个浏览器标签页会中断（已生成的已落库，未跑的不动）；
 * 需要"关页面也继续"时再迁到后端 ai_task。
 */
import { useSyncExternalStore } from "react";
import { previewGreeting, updateQueueItem } from "../../api/apply";
import { t } from "../../i18n";
import type { ApplyQueueItem } from "../../types";
import { notifyTaskDone } from "../../utils/taskNotify";

export interface GreetingBatchState {
  running: boolean;
  total: number;
  done: number;
  failed: number;
  currentTitle: string;
  /** 已请求停止：当前条目跑完就收尾。 */
  stopRequested: boolean;
}

const IDLE: GreetingBatchState = Object.freeze({
  running: false,
  total: 0,
  done: 0,
  failed: 0,
  currentTitle: "",
  stopRequested: false,
});

let state: GreetingBatchState = IDLE;
let stopped = false;
const listeners = new Set<() => void>();

function emit(next: Partial<GreetingBatchState>): void {
  state = { ...state, ...next };
  for (const listener of listeners) listener();
}

export function subscribeGreetingBatch(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getGreetingBatchState(): GreetingBatchState {
  return state;
}

export function useGreetingBatchState(): GreetingBatchState {
  return useSyncExternalStore(subscribeGreetingBatch, getGreetingBatchState);
}

export function stopGreetingBatch(): void {
  if (!state.running) return;
  stopped = true;
  emit({ stopRequested: true });
}

/** 生成并落库一条；返回是否真的拿到了模型生成结果。 */
async function generateFor(item: ApplyQueueItem): Promise<boolean> {
  if (item.job_id === null) return false;
  const preview = await previewGreeting({ job_id: item.job_id, item_id: item.id });
  // 未配置模型 / 模型失败时后端会退回默认招呼语（source=default）。把它当成功保存，
  // 就变成了用户明确要避免的"默认话术群发"——这里必须当成失败。
  if (preview.source !== "generated" || !preview.greeting.trim()) return false;
  await updateQueueItem(item.id, { greeting: preview.greeting, confirm_greeting: false });
  return true;
}

async function run(items: ApplyQueueItem[]): Promise<void> {
  stopped = false;
  emit({
    running: true,
    total: items.length,
    done: 0,
    failed: 0,
    currentTitle: items[0]?.job_title ?? "",
    stopRequested: false,
  });
  let ok = 0;
  let failed = 0;
  for (const item of items) {
    if (stopped) break;
    emit({ currentTitle: item.job_title });
    try {
      if (await generateFor(item)) {
        ok += 1;
      } else {
        failed += 1;
      }
    } catch {
      failed += 1;
    }
    emit({ done: ok + failed, failed });
  }
  const skipped = items.length - (ok + failed);
  emit({ running: false, currentTitle: "", stopRequested: false });
  notifyTaskDone({
    kind: failed > 0 ? "warning" : "success",
    title: t("applyQueue.greeting.batchDoneTitle", { ok, failed }),
    description:
      skipped > 0 ? t("applyQueue.greeting.batchSkipped", { count: skipped }) : undefined,
  });
}

/** 启动一批；已有任务在跑时返回 false（调用方据此说明"本批未自动生成"）。 */
export function startGreetingBatch(items: ApplyQueueItem[]): boolean {
  if (state.running || items.length === 0) return false;
  void run(items);
  return true;
}
