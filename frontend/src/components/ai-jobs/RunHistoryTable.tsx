// SPDX-License-Identifier: Apache-2.0
/** 运行记录（P3-3）：引擎 history 的采集/评分/任务/投递记录，轻量只读表。 */
import { Button, Empty, Space, Table, Tag, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { useCallback, useEffect, useState } from "react";
import { getAiHistory } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

interface HistoryItem {
  id: number | string;
  action?: string;
  title?: string;
  company?: string;
  detail?: string;
  created_at?: string;
}

const ACTION_TONES: Record<string, string> = {
  collected: "default",
  scored: "cyan",
  ready: "gold",
  approved: "blue",
  sent: "success",
  replied: "success",
  rejected: "error",
  error: "error",
  filtered: "default",
};

export default function RunHistoryTable() {
  useLocale();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(((await getAiHistory()) as unknown[]) as HistoryItem[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: TableColumnsType<HistoryItem> = [
    {
      title: t("aiJobs.history.action"),
      dataIndex: "action",
      key: "action",
      width: 110,
      render: (action: string) => <Tag color={ACTION_TONES[action] ?? "default"}>{action || "-"}</Tag>,
    },
    { title: t("aiJobs.job.company"), dataIndex: "company", key: "company", width: 140, ellipsis: true },
    { title: t("aiJobs.job.title"), dataIndex: "title", key: "title", ellipsis: true },
    { title: t("aiJobs.history.detail"), dataIndex: "detail", key: "detail", ellipsis: true },
    { title: t("aiJobs.history.time"), dataIndex: "created_at", key: "created_at", width: 160 },
  ];

  return (
    <Space direction="vertical" size="small" style={{ width: "100%" }}>
      <Space>
        <Button size="small" onClick={() => void load()} loading={loading}>
          {t("aiJobs.jobs.sync")}
        </Button>
      </Space>
      {error && (
        <Typography.Text type="danger" role="alert">
          {error}
        </Typography.Text>
      )}
      <Table<HistoryItem>
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{ pageSize: 15, showSizeChanger: false }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("aiJobs.history.empty")} /> }}
      />
    </Space>
  );
}
