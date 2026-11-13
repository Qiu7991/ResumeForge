// SPDX-License-Identifier: Apache-2.0
/**
 * 引擎连接卡：已连接 / 未安装 / 版本不匹配 三态 + 启停按钮。
 *
 * 三态判定（与后端 `build_ai_jobs_status` 口径一致）：
 * - 未安装：引擎路径没配或路径无效（`engine_configured=false`）；
 * - 版本不匹配：sidecar 可达但版本窗口外（`sidecar.version_ok=false`）；
 * - 已连接：可达且版本在窗口内。
 * 其余（路径无效但进程活着等）一律归入「未安装」分支并展示后端给出的可操作提示。
 */
import { Alert, App, Button, Card, Space, Tag, Typography } from "antd";
import { CheckCircleOutlined, PoweroffOutlined, ReloadOutlined, RobotOutlined } from "@ant-design/icons";
import { useState } from "react";
import { startEngine, stopEngine } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { AiJobsStatus } from "../../types/aiJobs";

type ConnectionTone = "success" | "warning" | "error";

export default function ConnectionCard({
  status,
  onReload,
}: {
  status: AiJobsStatus;
  onReload: () => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const { sidecar, owned_running: ownedRunning, port, engine_error: engineError } = status;

  const installed = status.engine_configured;
  const connected = sidecar.reachable && sidecar.version_ok;
  const mismatched = sidecar.reachable && !sidecar.version_ok;

  const [tone, label, description]: [ConnectionTone, string, string] = connected
    ? ["success", t("aiJobs.connection.connected"), ""]
    : mismatched
      ? ["error", t("aiJobs.connection.versionMismatch"), sidecar.reason]
      : installed
        ? ["warning", t("aiJobs.connection.notRunning"), sidecar.reason]
        : ["warning", t("aiJobs.connection.notInstalled"), engineError];

  const handleStart = async () => {
    setStarting(true);
    try {
      await startEngine();
      void message.success(t("aiJobs.connection.startSuccess"));
      onReload();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.connection.startFailed"));
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    setStopping(true);
    try {
      const result = await stopEngine();
      void message.success(
        result.stopped ? t("aiJobs.connection.stopSuccess") : t("aiJobs.connection.stopUnowned"),
      );
      onReload();
    } finally {
      setStopping(false);
    }
  };

  return (
    <Card
      title={
        <Space>
          <RobotOutlined />
          {t("aiJobs.connection.title")}
        </Space>
      }
      extra={
        <Button
          icon={<ReloadOutlined />}
          onClick={onReload}
          aria-label={t("aiJobs.connection.title")}
        />
      }
    >
      <Alert
        type={tone}
        showIcon
        icon={connected ? <CheckCircleOutlined /> : <RobotOutlined />}
        title={label}
        description={
          <>
            {description && <div>{description}</div>}
            <Space size="small" wrap>
              {connected && port > 0 && (
                <Tag>
                  {t("aiJobs.connection.port")} {port}
                </Tag>
              )}
              {sidecar.version && <Tag>{t("aiJobs.connection.version")} {sidecar.version}</Tag>}
              {ownedRunning && <Tag color="blue">{t("aiJobs.connection.connected")}</Tag>}
            </Space>
          </>
        }
      />
      <Space style={{ marginTop: 12 }}>
        <Button
          type="primary"
          icon={<PoweroffOutlined />}
          disabled={!installed || sidecar.reachable || undefined}
          loading={starting}
          onClick={() => void handleStart()}
        >
          {starting ? t("aiJobs.connection.starting") : t("aiJobs.connection.start")}
        </Button>
        <Button
          danger
          disabled={!ownedRunning || undefined}
          loading={stopping}
          onClick={() => void handleStop()}
        >
          {t("aiJobs.connection.stop")}
        </Button>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("aiJobs.page.description")}
        </Typography.Text>
      </Space>
    </Card>
  );
}
