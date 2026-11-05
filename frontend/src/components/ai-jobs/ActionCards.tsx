// SPDX-License-Identifier: Apache-2.0
/** 动作卡：全流程 / 单独采集 / 单独监测。启动必须预检通过（后端还有第二道）。 */
import { App, Button, Card, Col, Row, Typography } from "antd";
import { useState } from "react";
import { startAiTask } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

type AiMode = "full" | "collect" | "monitor";

const MODE_META: Record<
  AiMode,
  { titleKey: Parameters<typeof t>[0]; descKey: Parameters<typeof t>[0]; startKey: Parameters<typeof t>[0]; primary: boolean }
> = {
  full: { titleKey: "aiJobs.action.full", descKey: "aiJobs.action.fullDesc", startKey: "aiJobs.action.startFull", primary: true },
  collect: { titleKey: "aiJobs.action.collect", descKey: "aiJobs.action.collectDesc", startKey: "aiJobs.action.startCollect", primary: false },
  monitor: { titleKey: "aiJobs.action.monitor", descKey: "aiJobs.action.monitorDesc", startKey: "aiJobs.action.startMonitor", primary: false },
};

export default function ActionCards({
  disabled,
  onStarted,
}: {
  /** 任务在跑 / sidecar 未连接 / 预检未过 → 置灰。 */
  disabled: boolean;
  onStarted: () => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const [starting, setStarting] = useState<AiMode | null>(null);

  const handleStart = async (mode: AiMode) => {
    setStarting(mode);
    try {
      await startAiTask(mode, true);
      void message.success(t("aiJobs.action.started"));
      onStarted();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.action.startFailed"));
    } finally {
      setStarting(null);
    }
  };

  return (
    <Row gutter={[12, 12]}>
      {(Object.keys(MODE_META) as AiMode[]).map((mode) => {
        const meta = MODE_META[mode];
        return (
          <Col xs={24} md={8} key={mode}>
            <Card
              size="small"
              title={t(meta.titleKey)}
              actions={[
                <Button
                  key="start"
                  type={meta.primary ? "primary" : "default"}
                  disabled={disabled || undefined}
                  loading={starting === mode}
                  onClick={() => void handleStart(mode)}
                >
                  {t(MODE_META[mode].startKey)}
                </Button>,
              ]}
            >
              <Typography.Text type="secondary">{t(meta.descKey)}</Typography.Text>
            </Card>
          </Col>
        );
      })}
    </Row>
  );
}
