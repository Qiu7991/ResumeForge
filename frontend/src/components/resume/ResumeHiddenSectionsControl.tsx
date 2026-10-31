// SPDX-License-Identifier: Apache-2.0
/** 隐藏板块：被隐藏的板块不进入预览 / PDF / Word / 文本导出（四个渲染器同源）。 */
import { EyeInvisibleOutlined, EyeOutlined } from "@ant-design/icons";
import { App, Button, Space, Tag, Typography } from "antd";
import { useMemo } from "react";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { ResumeFormatConfig } from "../../types/resumeFormat";
import type { ResumeLayout } from "../../types";

interface SectionOption {
  key: string;
  label: string;
}

function normalizedHidden(value: unknown, known: Set<string>): string[] {
  if (!Array.isArray(value)) return [];
  const hidden: string[] = [];
  for (const item of value) {
    const key = typeof item === "string" ? item.trim() : "";
    if (key && known.has(key) && !hidden.includes(key)) hidden.push(key);
  }
  return hidden;
}

export default function ResumeHiddenSectionsControl({
  layout,
  options,
  disabled = false,
  onChange,
}: {
  layout: ResumeLayout;
  options: SectionOption[];
  disabled?: boolean;
  onChange: (layout: ResumeLayout) => void;
}) {
  useLocale();
  const { message } = App.useApp();
  const known = useMemo(() => new Set(options.map((item) => item.key)), [options]);
  const hidden = useMemo(
    () => normalizedHidden(layout.format_config?.hidden_sections, known),
    [layout.format_config?.hidden_sections, known],
  );

  const toggle = (key: string) => {
    const isHidden = hidden.includes(key);
    if (!isHidden && options.length - hidden.length <= 1) {
      message.warning(t("sections.hidden.keepOne"));
      return;
    }
    const next = isHidden ? hidden.filter((item) => item !== key) : [...hidden, key];
    const formatConfig = { ...(layout.format_config ?? {}) } as ResumeFormatConfig;
    if (next.length > 0) formatConfig.hidden_sections = next;
    else delete formatConfig.hidden_sections;
    onChange({ ...layout, format_config: formatConfig });
  };

  if (options.length === 0) return null;
  return (
    <div className="resume-hidden-sections">
      <Space size={6} wrap>
        <Typography.Text strong>{t("sections.hidden.title")}</Typography.Text>
        <Tag>
          {t("sections.hidden.count", { hidden: hidden.length, total: options.length })}
        </Tag>
      </Space>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: "4px 0 8px" }}>
        {t("sections.hidden.hint")}
      </Typography.Paragraph>
      <Space orientation="vertical" size={4} style={{ width: "100%" }}>
        {options.map((item) => {
          const isHidden = hidden.includes(item.key);
          return (
            <Space key={item.key} size={6} style={{ width: "100%" }}>
              <Button
                size="small"
                type={isHidden ? "primary" : "default"}
                disabled={disabled}
                icon={isHidden ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                aria-label={t(isHidden ? "sections.hidden.show" : "sections.hidden.hide", {
                  label: item.label,
                })}
                onClick={() => toggle(item.key)}
              />
              <Typography.Text delete={isHidden} type={isHidden ? "secondary" : undefined}>
                {item.label}
              </Typography.Text>
            </Space>
          );
        })}
      </Space>
    </div>
  );
}
