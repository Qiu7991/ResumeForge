// SPDX-License-Identifier: Apache-2.0
/**
 * 预览弹窗里的「板块」快捷控制：显示/隐藏 + 上下移动顺序。
 *
 * v2 文档的板块顺序与 hidden 都在 document.sections 上，所以改动直接回写整份文档
 * （由宿主保存并重渲染），不走旧 v1 的 format_config.section_order。这样预览里
 * 调完的板块设置与制作台、导出看到的是同一份数据。
 */
import { ArrowDownOutlined, ArrowUpOutlined, EyeInvisibleOutlined, EyeOutlined } from "@ant-design/icons";
import { App, Button, Modal, Space, Typography } from "antd";
import { useState } from "react";
import { useLocale } from "../../i18n/i18nContext";
import { t } from "../../i18n";
import { RESUME_CATALOG_SECTION_LABEL_KEYS } from "../../i18n/enum/resumeCatalog";
import type { ResumeDocument } from "../../types/resumeDocument";
import { layer } from "../../theme/tokens";

interface Props {
  document: ResumeDocument;
  /** 「我的资料」的板块顺序（翻译成简历 key）；用于一键同步和补入时定位。 */
  sectionOrder?: readonly string[];
  disabled?: boolean;
  onApply: (next: ResumeDocument) => void | Promise<void>;
}

export default function PreviewSectionsControl({
  document,
  sectionOrder = [],
  disabled,
  onApply,
}: Props) {
  useLocale();
  const { message } = App.useApp();
  // 受控开关：改用 Modal 呈现（见下方 return 处的说明）。
  const [panelOpen, setPanelOpen] = useState(false);
  const sections = document.sections;

  const apply = (next: ResumeDocument) => {
    void onApply(next);
  };

  const toggle = (index: number) => {
    const target = sections[index];
    if (!target) return;
    if (!target.hidden && sections.filter((section) => !section.hidden).length <= 1) {
      message.warning(t("workbench.sectionsVisibility.keepOne"));
      return;
    }
    apply({
      ...document,
      sections: sections.map((section, current) =>
        current === index ? { ...section, hidden: !section.hidden } : section,
      ),
    });
  };

  const techStackItems = document.sections.flatMap((section) =>
    section.entries.flatMap((entry) =>
      entry.items.filter(
        (item) =>
          item.kind === "field" &&
          (item.key === "tech_stack" || item.source?.field_id?.endsWith(".tech_stack")),
      ),
    ),
  );
  const visibleTechStack = techStackItems.some((item) => item.kind === "field" && item.placement !== "hidden");
  const toggleTechStack = () => {
    apply({
      ...document,
      sections: document.sections.map((section) => ({
        ...section,
        entries: section.entries.map((entry) => ({
          ...entry,
          items: entry.items.map((item) =>
            item.kind === "field" &&
            (item.key === "tech_stack" || item.source?.field_id?.endsWith(".tech_stack"))
              ? { ...item, placement: visibleTechStack ? ("hidden" as const) : ("trail" as const) }
              : item,
          ),
        })),
      })),
    });
  };

  const syncOrder = () => {
    const order = new Map(sectionOrder.map((key, index) => [key, index]));
    const sections = [...document.sections].sort((a, b) => {
      const left = order.get(a.key);
      const right = order.get(b.key);
      if (left === undefined && right === undefined) return 0;
      if (left === undefined) return 1;
      if (right === undefined) return -1;
      return left - right;
    });
    apply({ ...document, sections });
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= sections.length) return;
    const next = [...sections];
    [next[index], next[target]] = [next[target], next[index]];
    apply({ ...document, sections: next });
  };

  return (
    <>
      {/*
       * 用**受控 Modal** 而不是 Popover：预览本身已经在一个 Modal 里，
       * Popover 的浮层定位（rc-tooltip）会以 Modal 的滚动容器为参照反复测量，
       * 实测在这台机器上算出的 y 落在视口外（-7204px），且开关状态来回翻转，
       * 表现为「点了没反应 / 抖一下就没」。Modal 有自己独立且稳定的层级与定位，
       * 不再依赖锚点测量。宽度 360 足够放下 280 的面板内容。
       */}
      <Button
        size="small"
        disabled={disabled}
        aria-label={t("workbench.sectionsVisibility.trigger")}
        aria-expanded={panelOpen}
        onClick={() => setPanelOpen((v) => !v)}
      >
        {t("workbench.sectionsVisibility.trigger")}
      </Button>
      <Modal
        open={panelOpen}
        onCancel={() => setPanelOpen(false)}
        footer={null}
        width={360}
        zIndex={layer.popupBase + 300}
        title={t("workbench.sectionsVisibility.title")}
        destroyOnHidden
      >
        <div style={{ width: "100%" }}>
          <Typography.Paragraph type="secondary" style={{ fontSize: 12, margin: "0 0 8px" }}>
            {t("workbench.sectionsVisibility.hint")}
          </Typography.Paragraph>
          {techStackItems.length > 0 ? (
            <Button
              size="small"
              style={{ marginBottom: 8, marginRight: 6 }}
              disabled={disabled}
              onClick={toggleTechStack}
            >
              {t(
                visibleTechStack
                  ? "workbench.sectionsVisibility.hideTechStack"
                  : "workbench.sectionsVisibility.showTechStack",
              )}
            </Button>
          ) : null}
          {sectionOrder.length > 0 ? (
            <Button size="small" style={{ marginBottom: 8 }} disabled={disabled} onClick={syncOrder}>
              {t("workbench.sectionsVisibility.syncProfile")}
            </Button>
          ) : null}
          <Space orientation="vertical" size={4} style={{ width: "100%" }}>
            {sections.map((section, index) => {
              const labelKey = RESUME_CATALOG_SECTION_LABEL_KEYS[section.key];
              const label = section.title || (labelKey ? t(labelKey) : section.key);
              const isHidden = Boolean(section.hidden);
              return (
                <Space key={section.key} size={4} style={{ width: "100%" }}>
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
                    onClick={() => toggle(index)}
                  />
                  <Typography.Text
                    delete={isHidden}
                    type={isHidden ? "secondary" : undefined}
                    style={{ flex: 1, minWidth: 90 }}
                  >
                    {label}
                  </Typography.Text>
                  <Button
                    size="small"
                    type="text"
                    disabled={disabled || index === 0}
                    aria-label={t("sections.templateControls.orderMoveUpAria", { label })}
                    icon={<ArrowUpOutlined />}
                    onClick={() => move(index, -1)}
                  />
                  <Button
                    size="small"
                    type="text"
                    disabled={disabled || index === sections.length - 1}
                    aria-label={t("sections.templateControls.orderMoveDownAria", { label })}
                    icon={<ArrowDownOutlined />}
                    onClick={() => move(index, 1)}
                  />
                </Space>
              );
            })}
          </Space>
        </div>
      </Modal>
    </>
  );
}
