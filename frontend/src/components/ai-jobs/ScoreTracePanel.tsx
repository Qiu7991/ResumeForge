// SPDX-License-Identifier: Apache-2.0
/** 五维评分面板（P2-3）：维度分 + 证据 + 封顶/硬缺口 + 理由；legacy 缺失给"无详情"状态。 */
import { Empty, Space, Tag, Typography } from "antd";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { ScoreTrace } from "../../types/aiJobs";

const DIMENSION_LABEL_KEYS: Record<string, Parameters<typeof t>[0]> = {
  core_duties: "aiJobs.score.dimCoreDuties",
  transferable_evidence: "aiJobs.score.dimTransferable",
  hard_requirements: "aiJobs.score.dimHardRequirements",
  tools_industry: "aiJobs.score.dimTools",
  practical_fit: "aiJobs.score.dimPracticalFit",
};

export default function ScoreTracePanel({ trace }: { trace: ScoreTrace | null }) {
  useLocale();
  if (!trace || trace.missing || (!trace.dimensions && trace.score === undefined)) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("aiJobs.score.missing")} />;
  }
  const dimensions = Object.entries(trace.dimensions ?? {});
  const caps = trace.caps ?? [];
  const hardGaps = trace.hard_gaps ?? [];
  return (
    <Space direction="vertical" size="small" style={{ width: "100%" }}>
      {trace.score !== undefined && (
        <Typography.Title level={5} style={{ margin: 0 }}>
          {t("aiJobs.score.title")}: {trace.score}
        </Typography.Title>
      )}
      {dimensions.length > 0 && (
        <div style={{ display: "grid", gap: 8 }}>
          {dimensions.map(([key, dimension]) => {
            const labelKey = DIMENSION_LABEL_KEYS[key];
            return (
              <div key={key}>
                <Space size="small">
                  <Typography.Text strong>{labelKey ? t(labelKey) : key}</Typography.Text>
                  {typeof dimension.score === "number" && <Tag>{dimension.score}</Tag>}
                </Space>
                {dimension.evidence && (
                  <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
                    {dimension.evidence}
                  </Typography.Paragraph>
                )}
              </div>
            );
          })}
        </div>
      )}
      {caps.length > 0 && (
        <div>
          <Typography.Text type="secondary">{t("aiJobs.score.caps")}：</Typography.Text>
          {caps.map((cap) => (
            <Tag key={cap} color="orange">
              {cap}
            </Tag>
          ))}
        </div>
      )}
      {hardGaps.length > 0 && (
        <div>
          <Typography.Text type="secondary">{t("aiJobs.score.hardGaps")}：</Typography.Text>
          {hardGaps.map((gap) => (
            <Tag key={gap} color="red">
              {gap}
            </Tag>
          ))}
        </div>
      )}
      {trace.reason && (
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          <Typography.Text type="secondary">{t("aiJobs.score.reason")}：</Typography.Text>
          {trace.reason}
        </Typography.Paragraph>
      )}
    </Space>
  );
}
