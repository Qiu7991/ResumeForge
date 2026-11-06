// SPDX-License-Identifier: Apache-2.0
/** 引擎岗位状态徽标 + 多平台只读标识（P2-7：非 BOSS 明确"只读，不支持发送"）。 */
import { Tag } from "antd";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { EngineJobSummary } from "../../types/aiJobs";

const STATUS_LABEL_KEYS: Record<string, Parameters<typeof t>[0]> = {
  ready: "aiJobs.jobs.statusReady",
  approved: "aiJobs.jobs.statusApproved",
  scored: "aiJobs.jobs.statusScored",
  pending: "aiJobs.jobs.statusPending",
  filtered: "aiJobs.jobs.statusFiltered",
  sent: "aiJobs.jobs.statusSent",
  replied: "aiJobs.jobs.statusReplied",
  error: "aiJobs.jobs.statusError",
};

const STATUS_COLORS: Record<string, string> = {
  ready: "gold",
  approved: "blue",
  scored: "cyan",
  pending: "default",
  filtered: "default",
  sent: "success",
  replied: "success",
  error: "error",
};

export default function StatusBadge({
  job,
}: {
  job: Pick<EngineJobSummary, "status" | "source_platform" | "platform_label" | "platform_read_only">;
}) {
  useLocale();
  const labelKey = STATUS_LABEL_KEYS[job.status] ?? "aiJobs.jobs.statusOther";
  // 只读与展示名都由后端按 source_platform 派生（前端不写死站点 token）。
  const readOnly = job.platform_read_only ?? false;
  return (
    <span>
      <Tag color={STATUS_COLORS[job.status] ?? "default"}>{t(labelKey)}</Tag>
      {readOnly && (
        <Tag title={t("aiJobs.jobs.platformReadOnly")}>{t("aiJobs.jobs.platformReadOnly")}</Tag>
      )}
    </span>
  );
}
