// SPDX-License-Identifier: Apache-2.0
/**
 * Semantic score panel: total + five weighted dimensions + caps/gaps.
 *
 * Why a standalone component: the same block is needed in the job pool row detail and
 * (later) in the apply desk. Keeping it here means the "how a score reads" logic exists
 * once.
 */
import { Alert, Button, Card, Empty, Progress, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { scoreJob } from "../../api/jobHunt";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { SemanticScore } from "../../types/jobHunt";

const { Text } = Typography;

/** Cap code -> existing i18n key. Explicit map so the message key type stays checkable. */
const CAP_LABEL_KEY: Record<string, Parameters<typeof t>[0]> = {
  technical_required: "aiJobs.score.capTechnicalRequired",
  sales_acquisition_core: "aiJobs.score.capSalesAcquisition",
  weak_core_transfer: "aiJobs.score.capWeakCoreTransfer",
};

interface Props {
  jobId: number;
  /** Pre-loaded score (from the jobs list); undefined = not scored yet. */
  initial?: SemanticScore | null;
  /** Called after a successful (re)score so the parent can refresh its row. */
  onScored?: (score: SemanticScore) => void;
}

export default function ScorePanel({ jobId, initial, onScored }: Props) {
  useLocale();
  const [score, setScore] = useState<SemanticScore | null>(initial ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async (force: boolean) => {
    setLoading(true);
    setError("");
    try {
      const result = await scoreJob(jobId, force);
      setScore(result);
      onScored?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card
      size="small"
      title={t("aiJobs.score.title")}
      extra={
        <Button size="small" loading={loading} onClick={() => void run(!!score)}>
          {score ? t("aiJobs.score.rescore") : t("aiJobs.score.run")}
        </Button>
      }
    >
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}

      {!score ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("aiJobs.score.empty")}
        />
      ) : (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space align="center" size={16}>
            <Progress
              type="circle"
              percent={score.total}
              size={72}
              format={(p) => <span style={{ fontSize: 18 }}>{p}</span>}
            />
            <div>
              {score.role_summary && <div><Text strong>{score.role_summary}</Text></div>}
              {score.reason && <Text type="secondary">{score.reason}</Text>}
              {score.raw_total !== score.total && (
                <div>
                  <Text type="warning">
                    {t("aiJobs.score.cappedFrom", { raw: score.raw_total, total: score.total })}
                  </Text>
                </div>
              )}
            </div>
          </Space>

          {score.caps.length > 0 && (
            <Space wrap size={4}>
              <Text type="secondary">{t("aiJobs.score.caps")}</Text>
              {score.caps.map((cap) => (
                <Tag color="orange" key={cap}>
                  {t(CAP_LABEL_KEY[cap] ?? "aiJobs.score.caps")}
                </Tag>
              ))}
            </Space>
          )}

          {score.components.map((component) => (
            <div key={component.key}>
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <Text>{component.label}</Text>
                <Text type="secondary">
                  {component.score} / {component.limit}
                </Text>
              </Space>
              <Progress
                percent={(component.score / component.limit) * 100}
                showInfo={false}
                size="small"
                status={component.score / component.limit < 0.4 ? "exception" : "normal"}
              />
              {component.evidence && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {component.evidence}
                </Text>
              )}
            </div>
          ))}

          {score.hard_gaps.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={t("aiJobs.score.hardGaps")}
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {score.hard_gaps.map((gap, index) => (
                    <li key={index}>{gap}</li>
                  ))}
                </ul>
              }
            />
          )}

          {score.missing && (
            <Text type="secondary">
              {t("aiJobs.score.missingLabel", { text: score.missing })}
            </Text>
          )}
        </Space>
      )}
    </Card>
  );
}
