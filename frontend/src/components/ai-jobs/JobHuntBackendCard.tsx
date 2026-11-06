// SPDX-License-Identifier: Apache-2.0
/**
 * 「自研求职后端」切换卡（J9）：job_hunt_backend = sidecar（默认）| native。
 *
 * 默认 sidecar——旧的 HTTP 代理路径是能跑的现状；native 只是把自研采集
 * （services/job_hunt）接上开关，工作台等未实现的能力继续走旧路径。
 */
import { App, Card, Radio, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { getJobHuntConfig, getJobHuntStatus, saveJobHuntConfig } from "../../api/jobHunt";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { JobHuntBackend } from "../../types/jobHunt";

export default function JobHuntBackendCard({ onSaved }: { onSaved: () => void }) {
  useLocale();
  const { message } = App.useApp();
  const [backend, setBackend] = useState<JobHuntBackend>("sidecar");
  const [platforms, setPlatforms] = useState<{ key: string; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getJobHuntConfig(), getJobHuntStatus()])
      .then(([config, status]) => {
        if (cancelled) return;
        setBackend(config.job_hunt_backend);
        setPlatforms(status.platforms);
      })
      .catch((error) => {
        if (!cancelled) void message.error(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      // eslint-disable-next-line react-hooks/exhaustive-deps
    };
  }, []);

  const handleChange = async (value: JobHuntBackend) => {
    const previous = backend;
    setBackend(value);
    setSaving(true);
    try {
      await saveJobHuntConfig({ job_hunt_backend: value });
      void message.success(t("aiJobs.backend.saved"));
      onSaved();
    } catch (error) {
      setBackend(previous); // 保存失败回滚显示，别让界面撒谎
      void message.error(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title={t("aiJobs.backend.title")} loading={loading}>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Radio.Group
          value={backend}
          disabled={saving}
          onChange={(event) => void handleChange(event.target.value)}
          options={[
            { value: "sidecar", label: t("aiJobs.backend.sidecar") },
            { value: "native", label: t("aiJobs.backend.native") },
          ]}
        />
        <Typography.Text type="secondary">{t("aiJobs.backend.desc")}</Typography.Text>
        <Space size={4} wrap>
          <Typography.Text type="secondary">{t("aiJobs.backend.platforms")}</Typography.Text>
          {platforms.map((platform) => (
            <Tag key={platform.key}>{platform.name}</Tag>
          ))}
        </Space>
      </Space>
    </Card>
  );
}
