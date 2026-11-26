// SPDX-License-Identifier: Apache-2.0
/**
 * 「已导入」暂存记录：已经进过岗位广场、但记录本身还留在暂存区的候选。
 *
 * 为什么需要这一块：导入只把候选标成 imported，行仍在 `candidate_job` 表里，采集侧的去重
 * 因此一直把它当成"已存在"。原岗位被删掉之后，用户既在岗位广场看不到它，也采不回来——
 * 只有一个出口能修：把这些孤立记录移出暂存区（软删进回收站，可恢复）。
 *
 * **这里只删除候选，不碰正式岗位**：imported 只是"我导过它"，不能反过来当作"我可以删它"。
 */
import { LinkOutlined } from "@ant-design/icons";
import { Alert, App, Button, Space, Table, Tag, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { useState } from "react";
import { bulkDeleteCandidateJobs, listCandidateJobs } from "../../api/candidateJob";
import EmptyState from "../../components/common/EmptyState";
import PageSkeleton from "../../components/common/PageSkeleton";
import { useApi } from "../../hooks/useApi";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { CandidateJob } from "../../types";
import { formatDateTime } from "../../utils/format";

interface Props {
  /** 当前采集批次 id；批次切换时清空上一批的勾选（不做筛选）。 */
  taskId: number | null;
  /** 采集/投递正在跑时禁用清理。 */
  disabled?: boolean;
  /** 同一批次状态或完成时间变化时重新拉取。 */
  refreshKey?: string | number;
}

export default function CollectImportedPanel({ taskId, disabled = false, refreshKey = 0 }: Props) {
  // 本组件用模块级 t()：订阅语言变化，切语言后整块重渲染。
  useLocale();
  const { message } = App.useApp();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [deleting, setDeleting] = useState(false);

  const { data, loading, error, reload } = useApi<CandidateJob[]>(
    () => listCandidateJobs({ status: "imported", sort: "created_desc" }),
    [refreshKey],
    { refetchOnFocus: {} },
  );

  // 批次切换时清空勾选：跨批次保留会把上一批的 id 带进下一次清理。
  const [prevTaskId, setPrevTaskId] = useState(taskId);
  if (prevTaskId !== taskId) {
    setPrevTaskId(taskId);
    setSelectedIds([]);
  }

  const records = data ?? [];
  const orphanedIds = records.filter((row) => row.imported_job_missing).map((row) => row.id);

  const removeRecords = async (ids: number[]) => {
    if (ids.length === 0) return;
    setDeleting(true);
    try {
      const result = await bulkDeleteCandidateJobs(ids);
      message.success(t("collectResult.imported.deleteSuccess", { count: result.deleted }));
      setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)));
      await reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("collectResult.imported.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

  const columns: TableColumnsType<CandidateJob> = [
    {
      title: t("collectResult.column.title"),
      dataIndex: "title",
      render: (value: string, row) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{value || t("collectResult.row.unknownTitle")}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {row.company || t("collectResult.row.unknownCompany")}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: t("collectResult.column.location"),
      dataIndex: "location",
      width: 140,
      render: (value: string) => value || "—",
    },
    {
      title: t("collectResult.column.salary"),
      dataIndex: "salary",
      width: 130,
      render: (value: string) => value || "—",
    },
    {
      title: t("collectResult.column.collectedAt"),
      dataIndex: "collected_at",
      width: 130,
      render: (value: string | null | undefined) =>
        value ? formatDateTime(value) : t("collectResult.cell.manual"),
    },
    {
      title: t("collectResult.imported.column.jobStatus"),
      dataIndex: "imported_job_missing",
      width: 120,
      render: (missing: boolean | undefined) =>
        missing ? (
          <Tag color="warning">{t("collectResult.imported.status.orphaned")}</Tag>
        ) : (
          <Tag color="green">{t("collectResult.imported.status.live")}</Tag>
        ),
    },
    {
      title: t("collectResult.column.source"),
      dataIndex: "source_url",
      width: 90,
      render: (value: string) =>
        value && (
          <Typography.Link href={value} target="_blank" rel="noopener noreferrer">
            <LinkOutlined /> {t("collectResult.action.openSource")}
          </Typography.Link>
        ),
    },
  ];

  if (loading && !data) return <PageSkeleton rows={4} card={false} />;
  if (error) return <Alert type="error" showIcon title={error} />;

  return (
    <Space orientation="vertical" size={8} style={{ width: "100%" }}>
      {records.length === 0 ? (
        <EmptyState description={t("collectResult.imported.empty")} />
      ) : (
        <>
          <Table
            className="apply-collect-table"
            rowKey="id"
            size="small"
            columns={columns}
            dataSource={records}
            pagination={{ pageSize: 20, hideOnSinglePage: true, showSizeChanger: false }}
            rowSelection={{
              selectedRowKeys: selectedIds,
              onChange: (keys) => setSelectedIds(keys as number[]),
            }}
          />
          <Space size={8} wrap>
            <Button
              danger
              loading={deleting}
              disabled={disabled || deleting || selectedIds.length === 0 || undefined}
              onClick={() => void removeRecords(selectedIds)}
            >
              {selectedIds.length > 0
                ? t("collectResult.imported.deleteSelectedWithCount", {
                    count: selectedIds.length,
                  })
                : t("collectResult.imported.deleteSelected")}
            </Button>
            {orphanedIds.length > 0 && (
              <Button
                danger
                loading={deleting}
                disabled={disabled || deleting || undefined}
                onClick={() => void removeRecords(orphanedIds)}
              >
                {t("collectResult.imported.cleanOrphaned", { count: orphanedIds.length })}
              </Button>
            )}
            <Button
              disabled={disabled || deleting || undefined}
              onClick={() => setSelectedIds(records.map((row) => row.id))}
            >
              {t("collectResult.action.selectAll")}
            </Button>
            <Button
              disabled={disabled || deleting || selectedIds.length === 0 || undefined}
              onClick={() => setSelectedIds([])}
            >
              {t("collectResult.action.clearSelection")}
            </Button>
          </Space>
          <Typography.Text type="secondary">{t("collectResult.imported.footnote")}</Typography.Text>
        </>
      )}
    </Space>
  );
}
