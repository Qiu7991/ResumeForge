/**
 * 批量导出简历：选格式 → 后端打包 zip → 一次下载。
 *
 * 为什么不做「逐份下载」：浏览器会拦截连续多次自动下载，用户还得在下载列表里翻。
 * 批量导出的交付物就是一个 zip，文件名由后端带时间戳生成。
 */
import { Alert, App, Button, Modal, Select, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  MAX_BATCH_EXPORT,
  batchExportResumes,
} from "../../api/resumeBatchExport";
import type { ExportFormat } from "../../types/export";
import { downloadBlob } from "../../utils/download";

interface Props {
  open: boolean;
  resumeIds: number[];
  onClose: () => void;
}

const FORMAT_OPTIONS: { value: ExportFormat; label: string }[] = [
  { value: "pdf", label: "PDF（投递用）" },
  { value: "docx", label: "Word（.docx）" },
  { value: "html", label: "HTML" },
  { value: "txt", label: "纯文本（.txt）" },
  { value: "md", label: "Markdown（.md）" },
  { value: "json", label: "JSON（结构化数据）" },
];

export default function BatchExportModal({ open, resumeIds, onClose }: Props) {
  const { message } = App.useApp();
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 每次打开都回到默认格式：上一次的「Word」不该悄悄影响下一次批量导出。
  useEffect(() => {
    if (open) {
      setFormat("pdf");
      setError("");
    }
  }, [open]);

  const count = resumeIds.length;
  const tooMany = count > MAX_BATCH_EXPORT;
  const canSubmit = count > 0 && !tooMany && !loading;

  const submit = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    try {
      const result = await batchExportResumes(resumeIds, format);
      downloadBlob(result.blob, result.filename);
      if (result.skipped > 0) {
        message.warning(
          `已导出 ${result.exported} 份，跳过 ${result.skipped} 份：${result.skippedDetail}`,
          8,
        );
      } else {
        message.success(`已导出 ${result.exported} 份简历`);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量导出失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="批量导出简历"
      open={open}
      onCancel={loading ? undefined : onClose}
      closable={!loading}
      mask={{ closable: !loading }}
      keyboard={!loading}
      destroyOnHidden
      width={520}
      footer={
        <Space>
          <Button onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button type="primary" loading={loading} disabled={!canSubmit} onClick={() => void submit()}>
            {loading ? "正在打包…" : `导出 ${count} 份`}
          </Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        选中的简历会打成一个 zip，一次下载。每份的字号、页数、版式沿用这份简历自己的记录；
        这里只统一选择文件格式。
      </Typography.Paragraph>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Typography.Text>文件格式</Typography.Text>
        <Select
          aria-label="批量导出文件格式"
          style={{ width: 240 }}
          value={format}
          onChange={setFormat}
          options={FORMAT_OPTIONS}
          disabled={loading}
        />
        <Typography.Text type="secondary">
          已选 {count} 份{count > 0 ? `，上限 ${MAX_BATCH_EXPORT} 份` : ""}
        </Typography.Text>
      </Space>
      {tooMany && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          title={`一次最多导出 ${MAX_BATCH_EXPORT} 份，请减少选择后再试`}
        />
      )}
      {loading && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 12 }}
          title={`正在逐份渲染并打包 ${count} 份简历，PDF 可能需要几分钟，请不要关闭窗口…`}
        />
      )}
      {error && <Alert type="error" showIcon style={{ marginTop: 12 }} title={error} />}
    </Modal>
  );
}
