// SPDX-License-Identifier: Apache-2.0
/** 引擎岗位池表格（P2-6）：搜索/平台筛选/分页、批量导入、行点击进详情。 */
import { App, Button, Empty, Input, Space, Table } from "antd";
import type { TableColumnsType } from "antd";
import { useMemo, useState } from "react";
import { importEngineJobs } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { EngineJobSummary } from "../../types/aiJobs";
import StatusBadge from "./StatusBadge";

export default function JobResultsTable({
  jobs,
  total,
  loading,
  error,
  onReload,
  onOpenDetail,
}: {
  jobs: EngineJobSummary[];
  total: number;
  loading: boolean;
  error: string;
  onReload: () => void;
  onOpenDetail: (engineJobId: string) => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [keyword, setKeyword] = useState("");
  const [importing, setImporting] = useState(false);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return jobs;
    return jobs.filter(
      (job) =>
        job.title.toLowerCase().includes(kw) ||
        job.company.toLowerCase().includes(kw) ||
        (job.source_platform ?? "").toLowerCase().includes(kw),
    );
  }, [jobs, keyword]);

  const columns: TableColumnsType<EngineJobSummary> = [
    { title: t("aiJobs.job.company"), dataIndex: "company", key: "company", width: 140, ellipsis: true },
    { title: t("aiJobs.job.title"), dataIndex: "title", key: "title", ellipsis: true },
    { title: t("aiJobs.job.status"), key: "status", width: 180, render: (_, job) => <StatusBadge job={job} /> },
    { title: t("aiJobs.job.score"), dataIndex: "score", key: "score", width: 70 },
  ];

  const handleImport = async () => {
    setImporting(true);
    try {
      const summary = await importEngineJobs(selectedIds);
      void message.success(
        t("aiJobs.jobs.imported", { created: summary.created, linked: summary.linked_existing }),
      );
      setSelectedIds([]);
      onReload();
    } catch (err) {
      void message.error(err instanceof Error ? err.message : t("aiJobs.jobs.importFailed"));
    } finally {
      setImporting(false);
    }
  };

  return (
    <Space direction="vertical" size="small" style={{ width: "100%" }}>
      <Space wrap>
        <Input.Search
          allowClear
          placeholder={t("aiJobs.jobs.search")}
          onSearch={setKeyword}
          style={{ width: 220 }}
        />
        <Button onClick={onReload} loading={loading}>
          {t("aiJobs.jobs.sync")}
        </Button>
        <Button
          type="primary"
          disabled={selectedIds.length === 0 || undefined}
          loading={importing}
          onClick={() => void handleImport()}
        >
          {t("aiJobs.jobs.importSelected")}
        </Button>
      </Space>
      {error && <TypographyError text={error} onRetry={onReload} />}
      <Table<EngineJobSummary>
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        loading={loading}
        pagination={{ pageSize: 15, total, showSizeChanger: false }}
        rowSelection={{ selectedRowKeys: selectedIds, onChange: (keys) => setSelectedIds(keys as string[]) }}
        onRow={(job) => ({
          onClick: () => onOpenDetail(job.id),
          style: { cursor: "pointer" },
        })}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("aiJobs.jobs.empty")} /> }}
      />
    </Space>
  );
}

function TypographyError({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div role="alert" style={{ color: "var(--rf-color-error, #ff4d4f)" }}>
      {text}
      <Button type="link" size="small" onClick={onRetry}>
        {t("aiJobs.preflight.rerun")}
      </Button>
    </div>
  );
}
