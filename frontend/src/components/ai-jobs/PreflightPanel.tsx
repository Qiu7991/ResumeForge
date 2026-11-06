// SPDX-License-Identifier: Apache-2.0
/** 启动前检查面板：六类检查逐项展示（label/message 由后端给，前端只渲染）。 */
import { Alert, Button, List, Spin } from "antd";
import { CheckCircleFilled, CloseCircleFilled, ReloadOutlined } from "@ant-design/icons";
import type { AiPreflightResult } from "../../types/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

export default function PreflightPanel({
  result,
  loading,
  error,
  onRerun,
}: {
  result: AiPreflightResult | null;
  loading: boolean;
  error: string;
  onRerun: () => void;
}) {
  useLocale();
  return (
    <List
      size="small"
      header={
        <span>{t("aiJobs.preflight.title")}</span>
      }
      footer={
        <Button icon={<ReloadOutlined />} size="small" onClick={onRerun} loading={loading}>
          {t("aiJobs.preflight.rerun")}
        </Button>
      }
      dataSource={result?.checks ?? []}
      rowKey={(check) => check.key}
      renderItem={(check) => (
        <List.Item>
          <List.Item.Meta
            avatar={
              check.ok ? (
                <CheckCircleFilled style={{ color: "var(--rf-color-success, #52c41a)" }} />
              ) : (
                <CloseCircleFilled style={{ color: "var(--rf-color-error, #ff4d4f)" }} />
              )
            }
            title={check.label}
            description={check.message || undefined}
          />
        </List.Item>
      )}
      locale={{ emptyText: loading ? <Spin size="small" /> : error || t("aiJobs.preflight.title") }}
    />
  );
}

export function PreflightBlockedAlert({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return <Alert type="warning" showIcon title={t("aiJobs.preflight.blocked")} />;
}
