// SPDX-License-Identifier: Apache-2.0
/**
 * Data-flow funnel for the native (self-hosted) job-hunt backend.
 *
 * Why a dedicated hook: the page should only do "pick a data source -> render". Every
 * decision about which payload to send, how to refresh after a run, and how to enqueue
 * lives here instead of being scattered across components as ad-hoc ifs.
 *
 * Three actions:
 * 1. `collect()`: calls `/api/job-hunt/collect` (persist + optional analysis), then
 *    refreshes the job pool;
 * 2. `enqueue()`: adds the selected jobs to the **apply queue** (reuses `addToQueue`);
 *    greetings are edited on the apply desk -- this page does not re-implement that;
 * 3. `jobs`: the pool reads the job library (`listJobs`), the same data the apply desk
 *    and the jobs page use.
 */
import { useCallback, useEffect, useState } from "react";

import { addToQueue } from "../api/apply";
import { runJobHuntCollect } from "../api/jobHunt";
import { listJobs } from "../api/jobs";
import type { JobHuntCollectRequest, JobHuntCollectResult, JobHuntStub, JobHuntStatus } from "../types/jobHunt";
import type { JobList } from "../types/job";

export interface NativeJobHuntState {
  lastResult: JobHuntCollectResult | null;
  /** Job pool (sourced from the job library). */
  jobs: JobList[];
  loadingJobs: boolean;
  collecting: boolean;
  enqueueing: boolean;
  error: string;
}

const INITIAL: NativeJobHuntState = {
  lastResult: null,
  jobs: [],
  loadingJobs: false,
  collecting: false,
  enqueueing: false,
  error: "",
};

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useJobHuntNative(status: JobHuntStatus | null) {
  const [state, setState] = useState<NativeJobHuntState>(INITIAL);
  const isNative = status?.backend === "native";

  const loadJobs = useCallback(async () => {
    if (!isNative) return;
    setState((prev) => ({ ...prev, loadingJobs: true, error: "" }));
    try {
      const page = await listJobs({ page_size: 50 });
      setState((prev) => ({ ...prev, jobs: page.items, loadingJobs: false }));
    } catch (error) {
      setState((prev) => ({ ...prev, loadingJobs: false, error: toMessage(error) }));
    }
  }, [isNative]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const collect = useCallback(
    async (payload: JobHuntCollectRequest): Promise<JobHuntCollectResult> => {
      setState((prev) => ({ ...prev, collecting: true, error: "" }));
      try {
        const result = await runJobHuntCollect({ persist: true, analyze: true, ...payload });
        setState((prev) => ({ ...prev, collecting: false, lastResult: result }));
        // Refresh the pool after persisting: collected jobs must show up immediately.
        await loadJobs();
        return result;
      } catch (error) {
        setState((prev) => ({ ...prev, collecting: false, error: toMessage(error) }));
        throw error;
      }
    },
    [loadJobs],
  );

  const enqueue = useCallback(async (jobIds: number[]): Promise<number> => {
    setState((prev) => ({ ...prev, enqueueing: true, error: "" }));
    try {
      await addToQueue(jobIds.map((job_id) => ({ job_id })));
      setState((prev) => ({ ...prev, enqueueing: false }));
      return jobIds.length;
    } catch (error) {
      setState((prev) => ({ ...prev, enqueueing: false, error: toMessage(error) }));
      throw error;
    }
  }, []);

  return { state, collect, enqueue, reload: loadJobs, isNative };
}

export type { JobHuntStub };
