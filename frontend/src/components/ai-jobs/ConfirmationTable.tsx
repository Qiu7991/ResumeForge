// SPDX-License-Identifier: Apache-2.0
/**
 * 待确认投递表 + 确认弹窗（§8.4）：选中数量/平台/评分/招呼语、发送窗口与剩余额度、
 * 不可撤回提示、二次勾选。没有「全部自动发送」，没有「跳过确认」。
 */
import { App, Alert, Button, Checkbox, Modal, Space, Table, Tag, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { useMemo, useState } from "react";
import { deliverAiJobs, rejectAiJobs } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { EngineJobSummary, SendQuota } from "../../types/aiJobs";

function ConfirmDeliveryModal({
  open,
  selected,
  quota,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  selected: EngineJobSummary[];
  quota: SendQuota | null;
  submitting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  // 关闭时复位勾选：下次打开必须重新确认。
  const close = () => {
    setAcknowledged(false);
    onCancel();
  };
  const exhausted = quota?.exhausted ?? false;
  return (
    <Modal
      title={t("aiJobs.confirm.title")}
      open={open}
      onCancel={close}
      mask={{ closable: false }}
      footer={
        <Space>
          <Button onClick={close}>{t("aiJobs.confirm.cancel")}</Button>
          <Button
            type="primary"
            danger
            disabled={!acknowledged || selected.length === 0 || exhausted || undefined}
            loading={submitting}
            onClick={() => {
              onConfirm();
              setAcknowledged(false);
            }}
          >
            {t("aiJobs.confirm.action")}
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" style={{ width: "100%" }} size="small">
        <Typography.Text>{t("aiJobs.confirm.selected", { count: selected.length })}</Typography.Text>
        {quota && (
          <Typography.Text type={exhausted ? "danger" : "secondary"}>
            {t(
              exhausted ? "aiJobs.confirm.quotaExhausted" : "aiJobs.confirm.quota",
              exhausted ? {} : { sent: quota.sent, daily_limit: quota.daily_limit, remaining: quota.remaining },
            )}
          </Typography.Text>
        )}
        <Alert type="warning" showIcon title={t("aiJobs.confirm.warning")} />
        <Checkbox checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)}>
          {t("aiJobs.confirm.checkbox")}
        </Checkbox>
      </Space>
    </Modal>
  );
}

export default function ConfirmationTable({
  jobs,
  quota,
  onChanged,
}: {
  jobs: EngineJobSummary[];
  quota: SendQuota | null;
  onChanged: () => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const selectedJobs = useMemo(
    () => jobs.filter((job) => selectedIds.includes(job.id)),
    [jobs, selectedIds],
  );

  const columns: TableColumnsType<EngineJobSummary> = [
    { title: t("aiJobs.job.company"), dataIndex: "company", key: "company" },
    { title: t("aiJobs.job.title"), dataIndex: "title", key: "title" },
    {
      title: t("aiJobs.job.platform"),
      dataIndex: "source_platform",
      key: "platform",
      width: 120,
      render: (_: unknown, job: EngineJobSummary) => (
        <Tag>{job.platform_label ?? job.source_platform}</Tag>
      ),
    },
    { title: t("aiJobs.job.score"), dataIndex: "score", key: "score", width: 80 },
    {
      title: t("aiJobs.job.greeting"),
      dataIndex: "greeting",
      key: "greeting",
      render: (greeting: string | null) =>
        greeting ? (
          <Typography.Text ellipsis style={{ maxWidth: 260 }}>
            {greeting}
          </Typography.Text>
        ) : (
          <Tag color="warning">{t("aiJobs.confirm.greetingMissing")}</Tag>
        ),
    },
  ];

  const handleConfirm = async () => {
    setSubmitting(true);
    try {
      await deliverAiJobs(selectedIds);
      void message.success(t("aiJobs.confirm.delivered"));
      setModalOpen(false);
      setSelectedIds([]);
      onChanged();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.confirm.delivered"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (selectedIds.length === 0) return;
    setSubmitting(true);
    try {
      await rejectAiJobs(selectedIds);
      void message.success(t("aiJobs.confirm.rejected"));
      setSelectedIds([]);
      onChanged();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.confirm.rejected"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Space orientation="vertical" style={{ width: "100%" }} size="small">
      <Table<EngineJobSummary>
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={jobs}
        pagination={{ pageSize: 10, showSizeChanger: false }}
        rowSelection={{ selectedRowKeys: selectedIds, onChange: (keys) => setSelectedIds(keys as string[]) }}
        locale={{ emptyText: t("aiJobs.confirm.empty") }}
      />
      <Space>
        <Button
          type="primary"
          disabled={selectedIds.length === 0 || undefined}
          onClick={() => setModalOpen(true)}
        >
          {t("aiJobs.confirm.title")}
        </Button>
        <Button danger disabled={selectedIds.length === 0 || undefined} onClick={() => void handleReject()}>
          {t("aiJobs.confirm.reject")}
        </Button>
      </Space>
      <ConfirmDeliveryModal
        open={modalOpen}
        selected={selectedJobs}
        quota={quota}
        submitting={submitting}
        onCancel={() => setModalOpen(false)}
        onConfirm={() => void handleConfirm()}
      />
    </Space>
  );
}
