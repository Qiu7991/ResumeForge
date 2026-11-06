// SPDX-License-Identifier: Apache-2.0
/** 任务进度卡：状态、进度、可展开日志、停止（幂等）。 */
import { App, Button, Card, Collapse, Progress, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { stopAiTask } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { AiWorkbenchTask } from "../../types/aiJobs";

const STATUS_TONES: Record<string, { color: string; labelKey: Parameters<typeof t>[0] }> = {
  running: { color: "processing", labelKey: "aiJobs.task.statusRunning" },
  stopping: { color: "warning", labelKey: "aiJobs.task.statusStopping" },
  waiting_confirmation: { color: "gold", labelKey: "aiJobs.task.statusWaiting" },
  paused: { color: "default", labelKey: "aiJobs.task.statusPaused" },
  completed: { color: "success", labelKey: "aiJobs.task.statusCompleted" },
  stopped: { color: "default", labelKey: "aiJobs.task.statusStopped" },
  failed: { color: "error", labelKey: "aiJobs.task.statusFailed" },
};

export default function TaskProgress({
  task,
  onStopped,
}: {
  task: AiWorkbenchTask;
  onStopped: () => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const [stopping, setStopping] = useState(false);
  const tone = STATUS_TONES[task.status] ?? { color: "default", labelKey: "aiJobs.task.statusRunning" as const };
  const progressPercent = typeof task.progress?.percent === "number" ? task.progress.percent : undefined;

  const handleStop = async () => {
    setStopping(true);
    try {
      await stopAiTask(task.id);
      void message.success(t("aiJobs.task.stopSuccess"));
      onStopped();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.task.stopSuccess"));
    } finally {
      setStopping(false);
    }
  };

  return (
    <Card
      title={t("aiJobs.task.title")}
      extra={
        <Button
          danger
          size="small"
          loading={stopping}
          onClick={() => void handleStop()}
          disabled={task.status === "completed" || task.status === "failed" || task.status === "stopped" || undefined}
        >
          {t("aiJobs.task.stop")}
        </Button>
      }
    >
      <Space orientation="vertical" style={{ width: "100%" }} size="small">
        <Space wrap>
          <Tag color={tone.color}>{t(tone.labelKey)}</Tag>
          <Typography.Text>{task.label || task.mode}</Typography.Text>
          {task.deadline_at && (
            <Typography.Text type="secondary">
              {t("aiJobs.task.deadline")} {task.deadline_at}
            </Typography.Text>
          )}
        </Space>
        {typeof progressPercent === "number" && <Progress percent={progressPercent} size="small" />}
        {task.error && (
          <Typography.Text type="danger" role="alert">
            {task.error}
          </Typography.Text>
        )}
        {task.stop_reason && <Typography.Text type="secondary">{task.stop_reason}</Typography.Text>}
        {task.logs.length > 0 && (
          <Collapse
            size="small"
            items={[
              {
                key: "logs",
                label: t("aiJobs.task.logs"),
                children: (
                  <div style={{ maxHeight: 200, overflow: "auto" }}>
                    {task.logs.slice(-100).map((line, index) => (
                      <div key={index} style={{ whiteSpace: "pre-wrap" }}>
                        {line}
                      </div>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Space>
    </Card>
  );
}
