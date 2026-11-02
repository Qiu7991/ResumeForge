// SPDX-License-Identifier: Apache-2.0
/** 我的资料 → 生成偏好：当前只有「简历显示项目技术栈」，改动即保存。 */
import { App, Switch, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  getGenerationPreferences,
  saveGenerationPreferences,
} from "../../api/profile";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

export default function ProfileGenerationPreferences() {
  useLocale();
  const { message } = App.useApp();
  const [includeTechStack, setIncludeTechStack] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    void getGenerationPreferences()
      .then((value) => {
        if (alive) setIncludeTechStack(value.include_tech_stack);
      })
      .catch(() => {
        if (alive) setIncludeTechStack(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  const change = async (checked: boolean) => {
    const previous = includeTechStack;
    setIncludeTechStack(checked);
    setSaving(true);
    try {
      const saved = await saveGenerationPreferences({ include_tech_stack: checked });
      setIncludeTechStack(saved.include_tech_stack);
    } catch (err) {
      setIncludeTechStack(previous ?? false);
      message.error(
        err instanceof Error ? err.message : t("profileLibrary.generationPrefs.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        border: "1px solid var(--rf-border-color, #f0f0f0)",
        borderRadius: 10,
        padding: "12px 16px",
        marginBottom: 16,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 16,
        flexWrap: "wrap",
      }}
    >
      <div style={{ maxWidth: 720 }}>
        <Typography.Text strong>{t("profileLibrary.generationPrefs.title")}</Typography.Text>
        <div style={{ marginTop: 2 }}>
          <Typography.Text>{t("profileLibrary.generationPrefs.techStack")}</Typography.Text>
        </div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("profileLibrary.generationPrefs.techStackHint")}
        </Typography.Text>
      </div>
      <Switch
        checked={includeTechStack ?? false}
        loading={saving}
        disabled={includeTechStack === null}
        onChange={(checked) => void change(checked)}
        aria-label={t("profileLibrary.generationPrefs.techStack")}
      />
    </div>
  );
}
