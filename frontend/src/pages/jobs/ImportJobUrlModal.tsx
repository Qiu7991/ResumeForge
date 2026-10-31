// SPDX-License-Identifier: Apache-2.0
/** 按招聘网站链接导入岗位：粘贴岗位详情页链接，后端用专用浏览器抓 JD 落库。 */
import { Alert, App, Button, Input, Modal, Space, Typography } from "antd";
import { useState } from "react";
import { importJobFromUrl } from "../../api/jobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { Job } from "../../types";

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (job: Job) => void;
}

export default function ImportJobUrlModal({ open, onClose, onImported }: Props) {
  useLocale();
  const { message } = App.useApp();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    const target = url.trim();
    if (!target || loading) return;
    setLoading(true);
    setError("");
    try {
      const job = await importJobFromUrl(target);
      message.success(t("jobsPage.importUrl.success", { title: job.title }));
      setUrl("");
      onImported(job);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("jobsPage.importUrl.failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={t("jobsPage.importUrl.title")}
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">{t("jobsPage.importUrl.intro")}</Typography.Paragraph>
      <Input
        aria-label={t("jobsPage.importUrl.urlAria")}
        placeholder={t("jobsPage.importUrl.placeholder")}
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        onPressEnter={() => void submit()}
        allowClear
      />
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8 }}>
        {t("jobsPage.importUrl.hint")}
      </Typography.Paragraph>
      {error && <Alert type="error" showIcon title={error} style={{ marginTop: 12 }} />}
      <div style={{ marginTop: 16, textAlign: "right" }}>
        <Space>
          <Button onClick={onClose}>{t("common.action.cancel")}</Button>
          <Button type="primary" loading={loading} disabled={!url.trim()} onClick={() => void submit()}>
            {t("jobsPage.importUrl.submit")}
          </Button>
        </Space>
      </div>
    </Modal>
  );
}
