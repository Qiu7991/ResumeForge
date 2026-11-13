// SPDX-License-Identifier: Apache-2.0
/**
 * Pipeline strip: shows where the collect -> score flow currently stands.
 *
 * Why a dedicated strip: the previous UI spread these steps across pages, so the user
 * had to remember "did I already import these? are they scored?". A single row that
 * marks done / running / pending removes that bookkeeping.
 *
 * Only the pre-apply half is modelled here. Greeting and delivery live on the apply
 * desk, which owns its own progress UI - duplicating them here would create two
 * competing sources of truth.
 */
import { Space, Tag, Typography } from "antd";
import { CheckCircleFilled, ClockCircleOutlined, MinusCircleOutlined } from "@ant-design/icons";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

const { Text } = Typography;

export type StepState = "done" | "running" | "pending" | "skipped";

export interface PipelineStep {
  key: string;
  label: string;
  state: StepState;
  /** Short detail under the label, e.g. "第 1/3 页 · 12 条". */
  detail?: string;
}

const ICONS: Record<StepState, React.ReactNode> = {
  done: <CheckCircleFilled style={{ color: "var(--rf-accent-green)" }} />,
  running: <ClockCircleOutlined style={{ color: "var(--rf-info)" }} />,
  pending: <MinusCircleOutlined style={{ color: "var(--rf-text-secondary)" }} />,
  skipped: <MinusCircleOutlined style={{ color: "var(--rf-text-secondary)" }} />,
};

interface Props {
  steps: PipelineStep[];
}

export default function PipelineStrip({ steps }: Props) {
  // Subscribe to locale changes: module-level t() does not re-render on its own.
  useLocale();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "stretch",
        gap: 8,
        flexWrap: "wrap",
        padding: "12px 16px",
        borderRadius: 8,
        background: "var(--rf-fill-quaternary)",
        border: "1px solid var(--rf-fill-secondary)",
      }}
    >
      {steps.map((step, index) => (
        <div key={step.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Space direction="vertical" size={0} style={{ minWidth: 96 }}>
            <Space size={6}>
              {ICONS[step.state]}
              <Text strong={step.state === "running"} type={step.state === "pending" ? "secondary" : undefined}>
                {step.label}
              </Text>
            </Space>
            {step.detail && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {step.detail}
              </Text>
            )}
          </Space>
          {index < steps.length - 1 && (
            <Tag bordered={false} color="default" style={{ margin: 0 }}>
              →
            </Tag>
          )}
        </div>
      ))}
    </div>
  );
}

/** Build the four pre-apply steps from raw counters. */
export function buildSteps(input: {
  collecting: boolean;
  collected: number;
  currentPage: number;
  maxPages: number;
  imported: number;
  scored: number;
  inQueue: number;
  paused: boolean;
}): PipelineStep[] {
  const { collecting, collected, currentPage, maxPages, imported, scored, inQueue, paused } = input;

  const collectDetail = collecting
    ? t("aiJobs.pipeline.collectRunning", { page: currentPage, pages: maxPages, count: collected })
    : collected > 0
      ? t("aiJobs.pipeline.collectDone", { count: collected })
      : undefined;

  return [
    {
      key: "collect",
      label: t("aiJobs.pipeline.collect"),
      state: collecting ? "running" : collected > 0 ? "done" : "pending",
      detail: paused && collecting ? t("aiJobs.pipeline.paused") : collectDetail,
    },
    {
      key: "import",
      label: t("aiJobs.pipeline.import"),
      state: imported > 0 ? "done" : collected > 0 ? "running" : "pending",
      detail: imported > 0 ? t("aiJobs.pipeline.importDone", { count: imported }) : undefined,
    },
    {
      key: "score",
      label: t("aiJobs.pipeline.score"),
      state: scored > 0 ? "done" : imported > 0 ? "running" : "pending",
      detail: scored > 0 ? t("aiJobs.pipeline.scoreDone", { count: scored }) : undefined,
    },
    {
      key: "queue",
      label: t("aiJobs.pipeline.queue"),
      state: inQueue > 0 ? "done" : scored > 0 ? "running" : "pending",
      detail: inQueue > 0 ? t("aiJobs.pipeline.queueDone", { count: inQueue }) : undefined,
    },
  ];
}
