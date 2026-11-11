// SPDX-License-Identifier: Apache-2.0
/**
 * 备选岗位列表 + 评分任务轮询（AI 求职页专用）。
 *
 * 为什么单独一个 hook：这里有两件互相牵动的事——
 *
 * 1. **候选列表**是「导入 / 已评分」两个真实计数的来源，也是候选面板的数据源；
 * 2. **评分任务**在后台跑，跑完（或进度推进）要重拉列表才能看到分数出现。
 *
 * 放在组件里各写一遍 `useEffect` 会漏掉"任务刚结束就重拉"这类衔接。收在一处，
 * 轮询只在任务真的在跑时才启动，空闲时一次请求都不发。
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getCandidateScoreTask, listCandidateJobs } from "../api/candidateJob";
import type { CandidateJobSort } from "../api/candidateJob";
import type { CandidateScoreTask } from "../api/candidateJob";
import type { CandidateJob } from "../types";

/** 评分任务轮询间隔（与投递台其它轮询同量级，1.5s 足够且不吵）。 */
const SCORE_POLL_MS = 1500;

export interface CandidatesState {
  data: CandidateJob[];
  loading: boolean;
  error: string;
  /** 当前评分任务快照；没有任务时为 null。 */
  scoreTask: CandidateScoreTask | null;
}

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useCandidates(sort: CandidateJobSort = "created_desc") {
  const [state, setState] = useState<CandidatesState>({
    data: [],
    loading: false,
    error: "",
    scoreTask: null,
  });
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async (): Promise<CandidateJob[]> => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      const rows = await listCandidateJobs({ status: "pending", sort });
      setState((prev) => ({ ...prev, data: rows, loading: false }));
      return rows;
    } catch (error) {
      setState((prev) => ({ ...prev, loading: false, error: toMessage(error) }));
      return [];
    }
  }, [sort]);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const pollScoreTask = useCallback(async () => {
    try {
      const task = await getCandidateScoreTask();
      setState((prev) => ({ ...prev, scoreTask: task }));
      if (task.running) return;
      // 任务收敛：停轮询并重拉一次列表——分数是这一轮才写进去的。
      stopPolling();
      await refresh();
    } catch {
      // 轮询失败不该让页面报错：下一次 tick 再试，或由用户手动刷新。
    }
  }, [refresh, stopPolling]);

  /** 开始轮询评分任务（采集后自动评分，或用户手动点评分时调用）。 */
  const watchScoreTask = useCallback(() => {
    if (timer.current !== null) return;
    timer.current = window.setInterval(() => void pollScoreTask(), SCORE_POLL_MS);
    void pollScoreTask();
  }, [pollScoreTask]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => stopPolling, [stopPolling]);

  return { ...state, refresh, watchScoreTask, stopPolling };
}
