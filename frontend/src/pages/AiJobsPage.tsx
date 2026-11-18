// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职页（`/ai-jobs`）：自研采集工作台。
 *
 * 2026-11-19 之前这里按 `job_hunt_backend` 开关分发到两条实现：`sidecar`（遥控外部
 * BossHunter 引擎）与 `native`（自研采集）。自研那套跑稳之后旧路径已删除，
 * 现在是单向的——只剩 native，不再需要分发层。
 *
 * 保留这一层薄壳而不是把页面直接挂到 `NativeJobHuntView`：`/ai-jobs` 的加载态与
 * 错误态（状态接口拉不到时给「重试」）属于**页面职责**，视图只管渲染成功的状态。
 */
import { useCallback } from "react";

import NativeJobHuntView from "../components/ai-jobs/NativeJobHuntView";
import ErrorState from "../components/common/ErrorState";
import PageSkeleton from "../components/common/PageSkeleton";
import { getJobHuntStatus } from "../api/jobHunt";
import { useApi } from "../hooks/useApi";

export default function AiJobsPage() {
  const statusState = useApi(getJobHuntStatus);
  const reload = useCallback(() => void statusState.reload(), [statusState]);

  if (statusState.loading && !statusState.data) {
    return <PageSkeleton rows={4} />;
  }
  if (statusState.error) {
    return <ErrorState description={statusState.error} onRetry={reload} />;
  }

  const status = statusState.data;
  if (!status) return <PageSkeleton rows={4} />;

  return <NativeJobHuntView status={status} />;
}
