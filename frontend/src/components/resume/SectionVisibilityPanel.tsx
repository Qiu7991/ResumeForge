// SPDX-License-Identifier: Apache-2.0
/**
 * v2 文档的「显示板块」：隐藏 = section.hidden=true，数据保留、不上纸面。
 *
 * 与分页面板的「已设置断页」区分：这里控制"这块内容出不出来"，断页只控制从哪里开始。
 */
import { EyeInvisibleOutlined, EyeOutlined } from "@ant-design/icons";
import { App, Button, Space, Tag, Typography } from "antd";
import { t } from "../../i18n";
import { RESUME_CATALOG_SECTION_LABEL_KEYS } from "../../i18n/enum/resumeCatalog";
import { useLocale } from "../../i18n/i18nContext";
import type { ResumeDocument } from "../../types/resumeDocument";

interface Props {
  document: ResumeDocument;
  onChange: (next: ResumeDocument) => void;
  disabled?: boolean;
}

export default function SectionVisibilityPanel({ document, onChange, disabled }: Props) {
  useLocale();
  const { message } = App.useApp();
  // inline（技能）同样是可隐藏板块，不能因为不是条目型就漏掉。
  const sections = document.sections;
  const hiddenCount = sections.filter((section) => section.hidden).length;

  const toggle = (key: string) => {
    const target = sections.find((section) => section.key === key);
    if (!target) return;
    if (!target.hidden && sections.length - hiddenCount <= 1) {
      message.warning(t("workbench.sectionsVisibility.keepOne"));
      return;
    }
    onChange({
      ...document,
      sections: document.sections.map((section) =>
        section.key === key ? { ...section, hidden: !section.hidden } : section,
      ),
    });
  };

  if (sections.length === 0) return null;
  return (
    <div className="resume-section-visibility">
      <Space size={6} wrap>
        <Typography.Text strong>{t("workbench.sectionsVisibility.title")}</Typography.Text>
        <Tag>
          {t("workbench.sectionsVisibility.count", {
            hidden: hiddenCount,
            total: sections.length,
          })}
        </Tag>
      </Space>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: "4px 0 8px" }}>
        {t("workbench.sectionsVisibility.hint")}
      </Typography.Paragraph>
      <Space orientation="vertical" size={4} style={{ width: "100%" }}>
        {sections.map((section) => {
          const isHidden = Boolean(section.hidden);
          const labelKey = RESUME_CATALOG_SECTION_LABEL_KEYS[section.key];
          const label = section.title || (labelKey ? t(labelKey) : section.key);
          return (
            <Space key={section.key} size={6} style={{ width: "100%" }}>
              <Button
                size="small"
                type={isHidden ? "primary" : "default"}
                disabled={disabled}
                icon={isHidden ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                aria-label={t(
                  isHidden
                    ? "workbench.sectionsVisibility.show"
                    : "workbench.sectionsVisibility.hide",
                  { label },
                )}
                onClick={() => toggle(section.key)}
              />
              <Typography.Text delete={isHidden} type={isHidden ? "secondary" : undefined}>
                {label}
              </Typography.Text>
            </Space>
          );
        })}
      </Space>
    </div>
  );
}
