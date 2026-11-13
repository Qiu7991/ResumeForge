// SPDX-License-Identifier: Apache-2.0
/**
 * Semantic score panel: pick a resume, then see total + five dimensions + skill comparison.
 *
 * Why the resume picker lives here: the same job reads very differently through a
 * general resume versus a job-specific one. Switching resumes and re-scoring is exactly
 * how a user checks "does this resume cover what the JD asks for".
 *
 * Why a standalone component: the same block will be needed on the apply desk later.
 */
import { Alert, Button, Card, Empty, Progress, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

import { listResumes } from "../../api/resumes";
import { scoreJob } from "../../api/jobHunt";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { ResumeBrief } from "../../types/resume";
import type { SemanticScore, SkillMatch } from "../../types/jobHunt";

const { Text } = Typography;

interface Props {
  jobId: number;
  /** Pre-loaded score (from the jobs list); undefined = not scored yet. */
  initial?: SemanticScore | null;
  /** Called after a successful (re)score so the parent can refresh its row. */
  onScored?: (score: SemanticScore) => void;
}

/** Cap code -> existing i18n key. Explicit map so the message key type stays checkable. */
const CAP_LABEL_KEY: Record<string, Parameters<typeof t>[0]> = {
  technical_required: "aiJobs.score.capTechnicalRequired",
  sales_acquisition_core: "aiJobs.score.capSalesAcquisition",
  weak_core_transfer: "aiJobs.score.capWeakCoreTransfer",
};

const SKILL_STATUS_KEY: Record<string, Parameters<typeof t>[0]> = {
  matched: "aiJobs.score.skill.matched",
  partial: "aiJobs.score.skill.partial",
  missing: "aiJobs.score.skill.missing",
};

const STATUS_COLOR: Record<string, string> = {
  matched: "green",
  partial: "gold",
  missing: "red",
};

export default function ScorePanel({ jobId, initial, onScored }: Props) {
  useLocale();
  const [score, setScore] = useState<SemanticScore | null>(initial ?? null);
  const [resumes, setResumes] = useState<ResumeBrief[]>([]);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load the resume list once: it is the same list the apply desk uses.
  useEffect(() => {
    let cancelled = false;
    listResumes({ page_size: 100 })
      .then((page) => {
        if (!cancelled) setResumes(page.items);
      })
      .catch(() => {
        // A failed resume list must not block scoring: the backend falls back to
        // "job-specific -> default resume" when no resume_id is passed.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const run = useCallback(
    async (force: boolean, chosen: number | null) => {
      setLoading(true);
      setError("");
      try {
        const result = await scoreJob(jobId, force, chosen);
        setScore(result);
        onScored?.(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [jobId, onScored],
  );

  const skillColumns: ColumnsType<SkillMatch> = [
    { title: t("aiJobs.score.skill.name"), dataIndex: "skill", width: 180, ellipsis: true },
    {
      title: t("aiJobs.score.skill.status"),
      dataIndex: "status",
      width: 96,
      render: (status: string) => (
        <Tag color={STATUS_COLOR[status] ?? "default"}>
          {t(SKILL_STATUS_KEY[status] ?? "aiJobs.score.skill.missing")}
        </Tag>
      ),
    },
    { title: t("aiJobs.score.skill.evidence"), dataIndex: "resume_evidence", ellipsis: true },
  ];

  return (
    <Card
      size="small"
      title={t("aiJobs.score.title")}
      extra={
        <Space>
          {score?.resume_title && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("aiJobs.score.usedResume", { title: score.resume_title })}
            </Text>
          )}
          <Button size="small" loading={loading} onClick={() => void run(!!score, resumeId)}>
            {score ? t("aiJobs.score.rescore") : t("aiJobs.score.run")}
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Text type="secondary">{t("aiJobs.score.pickResume")}</Text>
          <Select
            allowClear
            style={{ minWidth: 280 }}
            placeholder={t("aiJobs.score.resumeAuto")}
            value={resumeId ?? undefined}
            onChange={(value?: number) => setResumeId(value ?? null)}
            options={resumes.map((item) => ({ value: item.id, label: item.title }))}
            showSearch
            optionFilterProp="label"
          />
        </Space>

        {error && <Alert type="error" showIcon title={error} />}

        {!score ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("aiJobs.score.empty")} />
        ) : (
          <>
            <Space align="center" size={16}>
              <Progress
                type="circle"
                percent={score.total}
                size={72}
                format={(p) => <span style={{ fontSize: 18 }}>{p}</span>}
              />
              <div>
                {score.role_summary && (
                  <div>
                    <Text strong>{score.role_summary}</Text>
                  </div>
                )}
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

            {score.skill_compare.length > 0 && (
              <Card size="small" title={t("aiJobs.score.skill.title")} type="inner">
                <Table<SkillMatch>
                  rowKey={(row) => `${row.skill}-${row.status}`}
                  size="small"
                  pagination={false}
                  columns={skillColumns}
                  dataSource={score.skill_compare}
                />
                <Space size={12} style={{ marginTop: 8 }}>
                  {(["matched", "partial", "missing"] as const).map((status) => (
                    <Text key={status} type="secondary" style={{ fontSize: 12 }}>
                      {t(SKILL_STATUS_KEY[status])}:{" "}
                      {score.skill_compare.filter((s) => s.status === status).length}
                    </Text>
                  ))}
                </Space>
              </Card>
            )}

            {score.hard_gaps.length > 0 && (
              <Alert
                type="warning"
                showIcon
                title={t("aiJobs.score.hardGaps")}
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
              <Text type="secondary">{t("aiJobs.score.missingLabel", { text: score.missing })}</Text>
            )}
          </>
        )}
      </Space>
    </Card>
  );
}
