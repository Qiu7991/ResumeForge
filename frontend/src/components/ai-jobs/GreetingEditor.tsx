// SPDX-License-Identifier: Apache-2.0
/** 招呼语编辑器（P2-4）：读取/编辑（≤300 字）/确认原文；不覆盖引擎生成原文之外的语义。 */
import { App, Button, Input, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  confirmEngineGreeting,
  getEngineGreeting,
  saveEngineGreeting,
} from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

const GREETING_MAX = 300;

export default function GreetingEditor({
  engineJobId,
  onChanged,
}: {
  engineJobId: string;
  onChanged: () => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const [greeting, setGreeting] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setLoading(true);
    let cancelled = false;
    getEngineGreeting(engineJobId)
      .then((data) => {
        if (cancelled) return;
        setGreeting(data.greeting ?? "");
        setConfirmed(data.greeting_confirmed);
      })
      .catch(() => {
        if (!cancelled) setGreeting("");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [engineJobId]);

  const handleSave = async () => {
    if (greeting.length > GREETING_MAX) {
      void message.error(t("aiJobs.greeting.overLimit", { limit: GREETING_MAX }));
      return;
    }
    setSaving(true);
    try {
      const result = await saveEngineGreeting(engineJobId, greeting);
      setGreeting(result.greeting);
      setConfirmed(result.greeting_confirmed);
      setEditing(false);
      void message.success(t("aiJobs.greeting.saved"));
      onChanged();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.greeting.saved"));
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    setSaving(true);
    try {
      await confirmEngineGreeting(engineJobId);
      setConfirmed(true);
      void message.success(t("aiJobs.greeting.confirmedToast"));
      onChanged();
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.greeting.confirmedToast"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Space direction="vertical" size="small" style={{ width: "100%" }}>
      <Space size="small">
        <Typography.Text strong>{t("aiJobs.greeting.title")}</Typography.Text>
        <Tag color={confirmed ? "success" : "warning"}>
          {t(confirmed ? "aiJobs.greeting.confirmed" : "aiJobs.greeting.unconfirmed")}
        </Tag>
      </Space>
      {editing ? (
        <>
          <Input.TextArea
            value={greeting}
            onChange={(e) => setGreeting(e.target.value)}
            maxLength={GREETING_MAX}
            showCount
            rows={3}
            aria-label={t("aiJobs.greeting.edit")}
          />
          <Space>
            <Button type="primary" size="small" loading={saving} onClick={() => void handleSave()}>
              {t("aiJobs.greeting.save")}
            </Button>
            <Button size="small" onClick={() => setEditing(false)}>
              {t("aiJobs.confirm.cancel")}
            </Button>
          </Space>
        </>
      ) : (
        <>
          <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
            {greeting || (loading ? "…" : "-")}
          </Typography.Paragraph>
          <Space>
            <Button size="small" onClick={() => setEditing(true)}>
              {t("aiJobs.greeting.edit")}
            </Button>
            <Button size="small" type="primary" disabled={confirmed || undefined} loading={saving} onClick={() => void handleConfirm()}>
              {t("aiJobs.greeting.confirm")}
            </Button>
          </Space>
        </>
      )}
    </Space>
  );
}
