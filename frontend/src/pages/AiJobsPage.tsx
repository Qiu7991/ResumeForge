// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职页（`/ai-jobs`）：BossHunter sidecar 工作台的简历通原生外壳。
 *
 * P1：工作台页签（连接卡 + 预检 + 动作 + 任务进度 + 待确认投递）。
 * `?tab=` 维持 URL 状态（沿用 ApplyPage 的模式）；岗位池/监测/记录页签随 P2/P3 加。
 */
import { Card, Tabs } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ConnectionCard from "../components/ai-jobs/ConnectionCard";
import JobDetailDrawer from "../components/ai-jobs/JobDetailDrawer";
import JobHuntBackendCard from "../components/ai-jobs/JobHuntBackendCard";
import JobResultsTable from "../components/ai-jobs/JobResultsTable";
import ReplyInbox from "../components/ai-jobs/ReplyInbox";
import RunHistoryTable from "../components/ai-jobs/RunHistoryTable";
import SettingsForm from "../components/ai-jobs/SettingsForm";
import PreflightPanel, { PreflightBlockedAlert } from "../components/ai-jobs/PreflightPanel";
import ActionCards from "../components/ai-jobs/ActionCards";
import TaskProgress from "../components/ai-jobs/TaskProgress";
import ConfirmationTable from "../components/ai-jobs/ConfirmationTable";
import ErrorState from "../components/common/ErrorState";
import PageSkeleton from "../components/common/PageSkeleton";
import {
  getAiConfirmation,
  getAiJobsStatus,
  getAiJobsWorkbench,
  getEngineJobs,
  runAiPreflight,
} from "../api/aiJobs";
import { useApi } from "../hooks/useApi";
import { useAiJobsPolling } from "../hooks/useAiJobsPolling";
import { t } from "../i18n";
import { useLocale } from "../i18n/i18nContext";
import { isAiTaskActive } from "../types/aiJobs";
import type { AiJobsWorkbenchState, AiPreflightResult, EngineJobSummary, SendQuota } from "../types/aiJobs";

/** 页签 key：URL ?tab= 的合法值域（监测/记录随 P3 补）。 */
const TABS = ["workbench", "jobs", "monitor", "records", "settings"] as const;

export default function AiJobsPage() {
  useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab") ?? "workbench";
  const tab = (TABS as readonly string[]).includes(tabParam) ? tabParam : "workbench";

  const statusState = useApi(getAiJobsStatus);
  const preflightState = useApi(runAiPreflight);
  const [confirmationJobs, setConfirmationJobs] = useState<EngineJobSummary[]>([]);
  const [quota, setQuota] = useState<SendQuota | null>(null);
  const [confirmationError, setConfirmationError] = useState("");
  const [workbenchState, setWorkbenchState] = useState<AiJobsWorkbenchState | null>(null);

  const status = statusState.data ?? null;
  const sidecarConnected = !!status?.sidecar.reachable && status.sidecar.version_ok;

  // 任务在跑（或还没拿到过一次状态）时轮询工作台；拿到"无活动任务"的快照即停，
  // 之后靠手动刷新与动作后的 reloadAll。
  const workbenchFetcher = useCallback(async (signal?: AbortSignal) => getAiJobsWorkbench(signal), []);
  const pollEnabled = sidecarConnected && (workbenchState === null || isAiTaskActive(workbenchState.task?.status));
  const workbench = useAiJobsPolling(workbenchFetcher, pollEnabled);
  useEffect(() => {
    if (workbench.data) setWorkbenchState(workbench.data);
  }, [workbench.data]);

  // 连接可用后取一次待确认列表 + 配额（任务结束后遗留的待确认岗位也要能看到）。
  useEffect(() => {
    if (!sidecarConnected) return;
    const controller = new AbortController();
    getAiConfirmation(controller.signal)
      .then((data) => {
        setConfirmationJobs(data.pending_confirmation ?? []);
        setQuota(data.send_quota ?? null);
        setConfirmationError("");
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setConfirmationError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => controller.abort();
  }, [sidecarConnected, workbenchState?.task?.status]);

  const reloadAll = useCallback(() => {
    void statusState.reload();
    void preflightState.reload();
    void workbench.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusState.data, preflightState.data]);

  // ===== 岗位池页签（P2-6）：引擎岗位列表 + 详情抽屉 =====
  const [engineJobs, setEngineJobs] = useState<EngineJobSummary[]>([]);
  const [engineTotal, setEngineTotal] = useState(0);
  const [engineLoading, setEngineLoading] = useState(false);
  const [engineError, setEngineError] = useState("");
  const [detailJobId, setDetailJobId] = useState<string | null>(null);

  const loadEngineJobs = useCallback(async () => {
    if (!sidecarConnected) return;
    setEngineLoading(true);
    setEngineError("");
    try {
      const data = await getEngineJobs({ limit: 100 });
      setEngineJobs(data.jobs ?? []);
      setEngineTotal(data.total ?? 0);
    } catch (error) {
      setEngineError(error instanceof Error ? error.message : String(error));
    } finally {
      setEngineLoading(false);
    }
  }, [sidecarConnected]);

  useEffect(() => {
    if (tab === "jobs" && sidecarConnected) void loadEngineJobs();
  }, [tab, sidecarConnected, loadEngineJobs]);

  const activeTask = workbenchState?.task ?? null;
  const taskActive = isAiTaskActive(activeTask?.status);
  const preflightResult: AiPreflightResult | null = preflightState.data ?? null;
  // BOSS 登录是人工确认项，不阻断动作按钮（其余检查未过才置灰）。
  const preflightBlocking = preflightResult?.checks.some((check) => !check.ok && check.key !== "boss_page") ?? false;

  const workbenchTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {statusState.loading && <PageSkeleton rows={4} />}
      {statusState.error && <ErrorState description={statusState.error} onRetry={() => void statusState.reload()} />}
      {status && <ConnectionCard status={status} onReload={() => void statusState.reload()} />}
      {status?.engine_configured && (
        <Card title={t("aiJobs.preflight.title")} size="small">
          <PreflightPanel
            result={preflightResult}
            loading={preflightState.loading}
            error={preflightState.error}
            onRerun={() => void preflightState.reload()}
          />
          <PreflightBlockedAlert visible={!preflightState.loading && preflightBlocking} />
        </Card>
      )}
      <ActionCards disabled={!sidecarConnected || taskActive || preflightBlocking} onStarted={reloadAll} />
      {activeTask && <TaskProgress task={activeTask} onStopped={reloadAll} />}
      <Card title={t("aiJobs.confirm.title")} size="small">
        {confirmationError && <ErrorState description={confirmationError} onRetry={reloadAll} />}
        <ConfirmationTable jobs={confirmationJobs} quota={quota} onChanged={reloadAll} />
      </Card>
    </div>
  );

  const jobsTab = (
    <JobResultsTable
      jobs={engineJobs}
      total={engineTotal}
      loading={engineLoading}
      error={engineError}
      onReload={() => void loadEngineJobs()}
      onOpenDetail={setDetailJobId}
    />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Tabs
        activeKey={tab}
        onChange={(key) => setSearchParams(key === "workbench" ? {} : { tab: key })}
        items={[
          { key: "workbench", label: t("aiJobs.workbench.tab"), children: workbenchTab },
          { key: "jobs", label: t("aiJobs.jobs.tab"), children: jobsTab },
          { key: "monitor", label: t("aiJobs.monitor.tab"), children: <ReplyInbox /> },
          { key: "records", label: t("aiJobs.records.tab"), children: <RunHistoryTable /> },
          { key: "settings", label: t("aiJobs.settings.tab"), children: (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* J9：自研后端开关（默认 sidecar）；下面的表单仍是 sidecar 引擎配置 */}
              <JobHuntBackendCard onSaved={reloadAll} />
              <SettingsForm onSaved={reloadAll} />
            </div>
          ) },
        ]}
      />
      <JobDetailDrawer
        engineJobId={detailJobId}
        open={detailJobId !== null}
        onClose={() => setDetailJobId(null)}
        onChanged={() => void loadEngineJobs()}
      />
    </div>
  );
}
