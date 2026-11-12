// SPDX-License-Identifier: Apache-2.0
/**
 * Collect-task driver: start a background collect job, poll progress, pause/resume/stop.
 *
 * Why polling instead of SSE: a collect run lasts seconds to a couple of minutes and the
 * page already polls other things. A 1s interval is cheap and survives page reloads of
 * the panel; streaming would add a second transport for no real gain.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  controlCollectTask,
  getActiveCollectTask,
  getCollectTask,
  getCollectTaskResult,
  startCollectTask,
} from "../api/jobHunt";
import type { CollectTaskSnapshot, JobHuntStub } from "../types/jobHunt";

const POLL_MS = 1000;

export interface CollectRunState {
  task: CollectTaskSnapshot | null;
  stubs: JobHuntStub[];
  error: string;
  starting: boolean;
}

const INITIAL: CollectRunState = { task: null, stubs: [], error: "", starting: false };

export function useCollectTask() {
  const [state, setState] = useState<CollectRunState>(INITIAL);
  const timer = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const poll = useCallback(
    async (taskId: string) => {
      try {
        const snapshot = await getCollectTask(taskId);
        setState((prev) => ({ ...prev, task: snapshot, error: "" }));
        if (snapshot.finished) {
          stopPolling();
          // Pull the full result once it is finished (rows are only returned then).
          const result = await getCollectTaskResult(taskId);
          setState((prev) => ({ ...prev, task: snapshot, stubs: result.stubs }));
        }
      } catch (err) {
        stopPolling();
        setState((prev) => ({ ...prev, error: err instanceof Error ? err.message : String(err) }));
      }
    },
    [stopPolling],
  );

  const start = useCallback(
    // 参数类型直接取自 API 层：这里再列一遍字段，新增一个（如 persist/auto_score）
    // 就会出现"页面传了、hook 类型不认"的编译错误——本来是一处改动的活变成两处。
    async (payload: Parameters<typeof startCollectTask>[0]) => {
      stopPolling();
      setState({ ...INITIAL, starting: true });
      try {
        const task = await startCollectTask(payload);
        setState({ task, stubs: [], error: "", starting: false });
        timer.current = window.setInterval(() => void poll(task.task_id), POLL_MS);
      } catch (err) {
        setState((prev) => ({
          ...prev,
          starting: false,
          error: err instanceof Error ? err.message : String(err),
        }));
      }
    },
    [poll, stopPolling],
  );

  const control = useCallback(
    async (action: "pause" | "resume" | "stop") => {
      const taskId = state.task?.task_id;
      if (!taskId) return;
      try {
        const snapshot = await controlCollectTask(taskId, action);
        setState((prev) => ({ ...prev, task: snapshot, error: "" }));
        // Stopping ends the run: fetch whatever was collected so far.
        if (action === "stop") {
          stopPolling();
          const result = await getCollectTaskResult(taskId);
          setState((prev) => ({ ...prev, task: snapshot, stubs: result.stubs }));
        }
      } catch (err) {
        setState((prev) => ({ ...prev, error: err instanceof Error ? err.message : String(err) }));
      }
    },
    [state.task?.task_id, stopPolling],
  );

  const clear = useCallback(() => {
    stopPolling();
    setState(INITIAL);
  }, [stopPolling]);

  /**
   * 挂载时把后台还在跑的任务接回来（2026-11-12）。
   *
   * 任务快照原本只活在前端内存：用户刷一下页面，采集/补 JD/评分还在后台跑，界面上
   * 却什么都没有——正好是"进度显示不明显"的一半原因。这里问一次后台有没有活跃任务，
   * 有就填进 state 并续上轮询。
   *
   * **只在没有任务时执行**：用户正盯着一个刚启动的任务时，不能被这次恢复覆盖掉。
   */
  const restored = useRef(false);
  const restore = useCallback(async () => {
    if (restored.current) return;
    restored.current = true;
    if (state.task !== null) return;
    try {
      const active = await getActiveCollectTask();
      if (!active.active || !active.task_id) return;
      const snapshot = active as CollectTaskSnapshot;
      setState({ task: snapshot, stubs: [], error: "", starting: false });
      // 接上轮询：这些任务可能正处于补 JD / 评分阶段，进度还在动。
      timer.current = window.setInterval(() => void poll(snapshot.task_id), POLL_MS);
    } catch {
      // 恢复失败无所谓：用户随时可以自己再点一次采集。
    }
  }, [poll, state.task]);

  return { state, start, control, clear, restore };
}
