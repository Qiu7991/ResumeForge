// SPDX-License-Identifier: Apache-2.0
/**
 * AI jobs page -- native (self-hosted) mode view.
 *
 * Sits beside `LegacyAiJobsView` (the sidecar path); `AiJobsPage` picks one based on
 * the `job_hunt_backend` setting. The two have different data sources:
 *
 * - legacy: calls the external BossHunter engine (`/api/ai-jobs/*`), requires the engine;
 * - this view: WorkTong collects by itself (`/api/job-hunt/collect`) -> persists into the
 *   job library -> enqueues through the existing apply desk.
 *
 * Deliberately NOT done here:
 * - no greeting editing (the apply desk's editor + gate is the single entry point);
 * - no delivery execution (the apply desk owns batches, breakers, failure classes);
 * - no scoring UI (the job library's match analysis is the same result set).
 */
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import { useJobHuntNative } from "../../hooks/useJobHuntNative";
import ScorePanel from "./ScorePanel";
import BlocklistCard from "./BlocklistCard";
import PipelineStrip, { buildSteps } from "./PipelineStrip";
import { useCollectTask } from "../../hooks/useCollectTask";
import type { JobHuntStatus } from "../../types/jobHunt";
import type { JobList } from "../../types/job";
import { useCandidates } from "../../hooks/useCandidates";
import CollectResultPanel from "../apply/CollectResultPanel";

const { Text, Title } = Typography;

interface Props {
  status: JobHuntStatus;
}

export default function NativeJobHuntView({ status }: Props) {
  const navigate = useNavigate();
  // Subscribe to locale changes: module-level t() does not re-render on its own.
  useLocale();
  const { state, enqueue, reload } = useJobHuntNative(status);
  const collectTask = useCollectTask();
  const task = collectTask.state.task;
  const collecting = task?.status === "running" || task?.status === "paused";
  const result = state.lastResult;

  const [siteKey, setSiteKey] = useState(status.platforms[0]?.key ?? "boss");
  const [keywords, setKeywords] = useState("AI");
  const [city, setCity] = useState(t("aiJobs.native.defaultCity"));
  const [maxPages, setMaxPages] = useState(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [queued, setQueued] = useState(0);
  // 采集即评分（默认开）。关掉 = 只落备选区不评分，分数列显示「未评分」。
  const [autoScore, setAutoScore] = useState(true);

  // 备选岗位列表：既是「导入/已评分」两个计数的来源，也是下面候选面板的数据源。
  // 采集任务进入终态时自动重拉一次（`task?.status`），评分任务结束也重拉一次。
  const {
    data: candidates,
    refresh: refreshCandidates,
    watchScoreTask,
  } = useCandidates();

  // 采集链路的「落库 → 补 JD → 评分」都在后台线程里跑完；任务快照里
  // `score_started` 为真时评分任务才真的起来了，这时开始轮询分数。
  useEffect(() => {
    if (task?.score_started) watchScoreTask();
  }, [task?.score_started, watchScoreTask]);

  // 流程条要的是「这一批里」的进度，不是全库累计：
  // - imported：已导入岗位广场的条数
  // - scored：已评出分数的条数
  const importedCandidates = candidates.filter((row) => row.status === "imported").length;
  const scoredCandidates = candidates.filter(
    (row) => row.score_total !== null && row.score_total !== undefined,
  ).length;

  const onCollect = async () => {
    setQueued(0);
    await collectTask.start({
      site_key: siteKey,
      keywords,
      city,
      max_pages: maxPages,
      // 默认都开：采完自动落备选区 + 补 JD + 评分，用户按分数挑——这正是
      // 「采集评分后再决定导入」那条链路。关掉 auto_score 就是只入库不评分。
      persist: true,
      auto_score: autoScore,
    });
  };

  const onEnqueue = async () => {
    if (!selected.length) return;
    try {
      const count = await enqueue(selected);
      setQueued(count);
      setSelected([]);
    } catch {
      // Same as above.
    }
  };

  const columns: ColumnsType<JobList> = [
    { title: t("aiJobs.native.col.title"), dataIndex: "title", ellipsis: true, width: 240 },
    { title: t("aiJobs.native.col.company"), dataIndex: "company", ellipsis: true, width: 160 },
    { title: t("aiJobs.native.col.location"), dataIndex: "location", ellipsis: true, width: 150 },
    {
      title: t("aiJobs.native.col.salary"),
      dataIndex: "salary",
      width: 120,
      render: (value: string) => value || <Text type="secondary">—</Text>,
    },
    {
      title: t("aiJobs.native.col.status"),
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{value}</Tag>,
    },
  ];



  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {state.error && <Alert type="error" showIcon message={state.error} />}

      {queued > 0 && (
        <Alert
          type="success"
          showIcon
          message={t("aiJobs.native.queuedHint", { count: queued })}
          action={
            <Button size="small" type="primary" onClick={() => navigate("/apply")}>
              {t("aiJobs.native.goApply")}
            </Button>
          }
        />
      )}

      <PipelineStrip
        steps={buildSteps({
          collecting,
          collected: task?.collected ?? candidates.length,
          currentPage: task?.current_page ?? 0,
          maxPages: task?.max_pages ?? maxPages,
          // 这三个数都来自候选列表本身（服务端下发），不再是 useState(0) 那种
          // 「刷新就归零」的临时值，也不再是写死的 scored: 0。
          imported: importedCandidates,
          scored: scoredCandidates,
          inQueue: queued,
          paused: task?.status === "paused",
        })}
      />

      <Card title={t("aiJobs.native.collectTitle")} size="small">
        <Space wrap>
          <Select
            value={siteKey}
            onChange={setSiteKey}
            style={{ width: 140 }}
            options={status.platforms.map((platform) => ({ value: platform.key, label: platform.name }))}
          />
          <Input
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder={t("aiJobs.native.keywords")}
            style={{ width: 180 }}
          />
          <Input
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder={t("aiJobs.native.city")}
            style={{ width: 120 }}
          />
          <Select
            value={maxPages}
            onChange={setMaxPages}
            style={{ width: 110 }}
            options={[1, 2, 3, 5].map((n) => ({
              value: n,
              label: t("aiJobs.native.pages", { n }),
            }))}
          />
          <Tooltip title={t("aiJobs.native.autoScoreHint")}>
            <Checkbox checked={autoScore} onChange={(e) => setAutoScore(e.target.checked)}>
              {t("aiJobs.native.autoScore")}
            </Checkbox>
          </Tooltip>
          <Button
            type="primary"
            loading={collectTask.state.starting || collecting}
            disabled={collecting}
            onClick={() => void onCollect()}
          >
            {t("aiJobs.native.collect")}
          </Button>
          {collecting && (
            <>
              {task?.status === "paused" ? (
                <Button onClick={() => void collectTask.control("resume")}>
                  {t("aiJobs.pipeline.resume")}
                </Button>
              ) : (
                <Button onClick={() => void collectTask.control("pause")}>
                  {t("aiJobs.pipeline.pause")}
                </Button>
              )}
              <Button danger onClick={() => void collectTask.control("stop")}>
                {t("aiJobs.pipeline.stop")}
              </Button>
            </>
          )}
          <Button onClick={() => void reload()} loading={state.loadingJobs}>
            {t("aiJobs.native.refresh")}
          </Button>
        </Space>

        {task && (
          <div style={{ marginTop: 12 }}>
            <Space wrap>
              <Tag color={task.status === "running" ? "processing" : task.status === "paused" ? "warning" : task.status === "failed" ? "error" : "success"}>
                {t(`aiJobs.pipeline.status.${task.status}`)}
              </Tag>
              <Text type="secondary">{task.message}</Text>
              {task.blocked > 0 && (
                <Text type="secondary">{t("aiJobs.native.blockedCount", { count: task.blocked })}</Text>
              )}
            </Space>
            {task.error && <Alert style={{ marginTop: 8 }} type="error" showIcon message={task.error} />}
          </div>
        )}

        {result && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary">
              {t("aiJobs.native.collectSummary", {
                inserted: result.persisted.inserted,
                skipped: result.persisted.skipped_duplicate,
                pages: result.pages_fetched,
              })}
            </Text>
            {result.persisted.errors.length > 0 && (
              <Alert
                style={{ marginTop: 8 }}
                type="warning"
                showIcon
                message={t("aiJobs.native.persistErrors", {
                  count: result.persisted.errors.length,
                })}
                description={result.persisted.errors.slice(0, 5).join(t("aiJobs.native.errorSeparator"))}
              />
            )}
          </div>
        )}

      </Card>

      {/* 备选岗位（采集结果）——采集 → 评分 → 我决定导入的全部动作都在这一块。
          taskId 传 null：这里列的是**所有批次**的候选，不只最后一轮（与投递台
          采集面板同一取舍，省得用户再去采集记录里翻）。 */}
      <Card
        size="small"
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              {t("aiJobs.native.candidateTitle")}
            </Title>
            <Text type="secondary">{candidates.length}</Text>
          </Space>
        }
        extra={
          <Button size="small" onClick={() => void refreshCandidates()} loading={state.loadingJobs}>
            {t("aiJobs.native.refresh")}
          </Button>
        }
      >
        <CollectResultPanel
          taskId={null}
          disabled={collecting}
          refreshKey={`${candidates.length}-${scoredCandidates}-${importedCandidates}`}
          onImported={() => {
            void refreshCandidates();
            void reload();
          }}
        />
      </Card>

      <BlocklistCard />

      <Card
        title={
          <Space>
            <Title level={5} style={{ margin: 0 }}>
              {t("aiJobs.native.poolTitle")}
            </Title>
            <Text type="secondary">{state.jobs.length}</Text>
          </Space>
        }
        size="small"
        extra={
          <Space>
            <Text type="secondary">
              {t("aiJobs.native.selected", { n: selected.length })}
            </Text>
            <Button
              type="primary"
              disabled={!selected.length}
              loading={state.enqueueing}
              onClick={() => void onEnqueue()}
            >
              {t("aiJobs.native.enqueue")}
            </Button>
          </Space>
        }
      >
        <Table<JobList>
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={state.jobs}
          loading={state.loadingJobs}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          rowSelection={{
            selectedRowKeys: selected,
            onChange: (keys) => setSelected(keys as number[]),
          }}
          locale={{ emptyText: <Empty description={t("aiJobs.native.empty")} /> }}
        />
      </Card>

      {selected.length === 1 && <ScorePanel jobId={selected[0]} />}
      {selected.length > 1 && (
        <Alert
          type="info"
          showIcon
          message={t("aiJobs.native.scoreHintMulti", { count: selected.length })}
        />
      )}

      <Alert type="info" showIcon message={t("aiJobs.native.replyNotAvailable")} />
    </div>
  );
}
