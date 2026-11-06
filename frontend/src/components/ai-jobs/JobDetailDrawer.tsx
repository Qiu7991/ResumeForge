// SPDX-License-Identifier: Apache-2.0
/**
 * 岗位详情抽屉（P2-6）：视图切换（列表 → 详情），不叠层。含五维评分、招呼语、
 * 定制简历下载、在引擎中打开。只读查看：footer=null，关闭走右上 ×。
 */
import { Button, Drawer, Space, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { getEngineJobDetail, getEngineScoreTrace } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { EngineJobSummary, ScoreTrace } from "../../types/aiJobs";
import GreetingEditor from "./GreetingEditor";
import ScoreTracePanel from "./ScoreTracePanel";
import StatusBadge from "./StatusBadge";

export default function JobDetailDrawer({
  engineJobId,
  open,
  onClose,
  onChanged,
}: {
  engineJobId: string | null;
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  useLocale();
  const [job, setJob] = useState<EngineJobSummary | null>(null);
  const [trace, setTrace] = useState<ScoreTrace | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !engineJobId) return;
    setLoading(true);
    let cancelled = false;
    Promise.all([getEngineJobDetail(engineJobId), getEngineScoreTrace(engineJobId)])
      .then(([detail, scoreTrace]) => {
        if (cancelled) return;
        setJob(detail);
        setTrace(scoreTrace);
      })
      .catch(() => {
        if (!cancelled) setTrace({ missing: true });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, engineJobId]);

  return (
    <Drawer
      title={t("aiJobs.jobs.detail")}
      open={open}
      onClose={onClose}
      size="small"
      footer={null}
    >
      {loading && <Spin />}
      {!loading && job && (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Space direction="vertical" size={4} style={{ width: "100%" }}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {job.title}
            </Typography.Title>
            <Space size="small" wrap>
              <Typography.Text type="secondary">{job.company}</Typography.Text>
              <StatusBadge job={job} />
            </Space>
          </Space>
          {job.score !== undefined && job.score !== null && (
            <Typography.Text strong>
              {t("aiJobs.job.score")}: {job.score}
            </Typography.Text>
          )}
          <ScoreTracePanel trace={trace} />
          <GreetingEditor engineJobId={engineJobId ?? ""} onChanged={onChanged} />
          {job.url && (
            <Button size="small" href={job.url} target="_blank" rel="noreferrer">
              {t("aiJobs.jobs.openInEngine")}
            </Button>
          )}
          <Button size="small" href={`/api/ai-jobs/engine-jobs/${encodeURIComponent(engineJobId ?? "")}/resume/download`}>
            {t("aiJobs.resume.download")}
          </Button>
        </Space>
      )}
      {!loading && !job && <Typography.Text type="secondary">-</Typography.Text>}
    </Drawer>
  );
}
