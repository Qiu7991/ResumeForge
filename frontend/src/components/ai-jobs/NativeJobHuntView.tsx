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
import { Alert, Button, Card, Empty, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import { useJobHuntNative } from "../../hooks/useJobHuntNative";
import ScorePanel from "./ScorePanel";
import type { JobHuntStatus } from "../../types/jobHunt";
import type { JobList } from "../../types/job";

const { Text, Title } = Typography;

interface Props {
  status: JobHuntStatus;
}

export default function NativeJobHuntView({ status }: Props) {
  const navigate = useNavigate();
  // Subscribe to locale changes: module-level t() does not re-render on its own.
  useLocale();
  const { state, collect, enqueue, reload } = useJobHuntNative(status);

  const [siteKey, setSiteKey] = useState(status.platforms[0]?.key ?? "boss");
  const [keywords, setKeywords] = useState("AI");
  const [city, setCity] = useState(t("aiJobs.native.defaultCity"));
  const [maxPages, setMaxPages] = useState(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [queued, setQueued] = useState(0);

  const onCollect = async () => {
    try {
      await collect({
        site_key: siteKey,
        keywords,
        city,
        max_pages: maxPages,
      });
      setQueued(0);
      // Results surface in collectSummary / the error alert below; no blocking alert.
    } catch {
      // The error already lands in state.error and shows in the alert at the top.
    }
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

  const result = state.lastResult;

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
          <Button type="primary" loading={state.collecting} onClick={() => void onCollect()}>
            {t("aiJobs.native.collect")}
          </Button>
          <Button onClick={() => void reload()} loading={state.loadingJobs}>
            {t("aiJobs.native.refresh")}
          </Button>
        </Space>

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
            {result.analyze_task_id && (
              <Alert
                style={{ marginTop: 8 }}
                type="info"
                showIcon
                message={t("aiJobs.native.analyzeStarted")}
              />
            )}
          </div>
        )}
      </Card>

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
