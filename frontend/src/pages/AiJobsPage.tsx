// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职页（`/ai-jobs`）：按 `job_hunt_backend` 开关分发到两条实现。
 *
 * - `sidecar`（默认）：`LegacyAiJobsView` —— 调外部 BossHunter 引擎，原逻辑一行未改；
 * - `native`：`NativeJobHuntView` —— 工作通自研采集 + 复用投递台入队。
 *
 * 为什么在这一层分发、而不是在页面里到处写 if：
 * 两条路径的数据源、前置条件（引擎 vs 浏览器）、可用动作都不同，混在一起迟早互相踩。
 * 分发点只有这里一处，两个视图各自独立演进。
 */
import { useCallback } from "react";

import LegacyAiJobsView from "../components/ai-jobs/LegacyAiJobsView";
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

  return status.backend === "native" ? (
    <NativeJobHuntView status={status} />
  ) : (
    <LegacyAiJobsView />
  );
}
