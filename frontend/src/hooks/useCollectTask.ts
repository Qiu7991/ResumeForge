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
    async (payload: { site_key: string; keywords?: string; city?: string; max_pages?: number }) => {
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

  return { state, start, control, clear };
}
