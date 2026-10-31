// SPDX-License-Identifier: Apache-2.0
/**
 * 简历模板工作台：内置样式画廊、自制样式模板（复制/导入/编辑/预览）与自制版式。
 *
 * 上游 2026-11 下线了自制样式模板的界面，本地二开**保留**并接回新版模板体系：
 * 组件本身仍在上游仓库（`StyleTemplateEditorModal` / `TemplateImportModal` /
 * `BuiltinStyleGallery`），这里只负责把它们重新组织成一个可用的管理页。
 */
import {
  CopyOutlined,
  ImportOutlined,
  PlusOutlined,
  RobotOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { App, Button, Card, Collapse, Dropdown, Empty, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchResumeTemplates } from "../../api/resumes";
import {
  deleteResumeTemplate,
  fetchBuiltinTemplateSource,
  listResumeTemplates,
} from "../../api/resumeTemplates";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { ResumeTemplateCatalog, ResumeTemplateDetail } from "../../types";
import FileDropZone from "../common/FileDropZone";
import BuiltinStyleGallery from "./BuiltinStyleGallery";
import FormatTemplateEditorModal from "./FormatTemplateEditorModal";
import StyleTemplateEditorModal from "./StyleTemplateEditorModal";
import TemplateCustomTable from "./TemplateCustomTable";
import TemplateImportModal from "./TemplateImportModal";
import TemplatePreviewModal from "./TemplatePreviewModal";

interface Props {
  /** 模板变化后通知外层刷新缓存。 */
  onChanged?: () => void;
}


export default function TemplateWorkbench({ onChanged }: Props) {
  useLocale();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<ResumeTemplateDetail[]>([]);
  const [catalog, setCatalog] = useState<ResumeTemplateCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [styleEditor, setStyleEditor] = useState<{
    open: boolean;
    id?: number | null;
    html: string;
    name: string;
    config: Record<string, unknown>;
  }>({ open: false, html: "", name: "", config: {} });
  const [formatEditor, setFormatEditor] = useState<{
    open: boolean;
    template: ResumeTemplateDetail | null;
  }>({ open: false, template: null });
  const [previewTemplate, setPreviewTemplate] = useState<ResumeTemplateDetail | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchTemplates = useCallback(async (): Promise<ResumeTemplateDetail[] | null> => {
    try {
      return await listResumeTemplates();
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t("templatesUi.workbench.error.loadTemplates"),
      );
      return null;
    }
  }, [message]);

  const fetchCatalog = useCallback(async (): Promise<ResumeTemplateCatalog | null> => {
    try {
      return await fetchResumeTemplates();
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t("templatesUi.workbench.error.loadCatalog"),
      );
      return null;
    }
  }, [message]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [nextTemplates, nextCatalog] = await Promise.all([fetchTemplates(), fetchCatalog()]);
      if (cancelled) return;
      if (nextTemplates !== null) setTemplates(nextTemplates);
      if (nextCatalog !== null) setCatalog(nextCatalog);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchTemplates, fetchCatalog]);

  const refreshAll = async () => {
    setLoading(true);
    const [nextTemplates, nextCatalog] = await Promise.all([fetchTemplates(), fetchCatalog()]);
    if (nextTemplates !== null) setTemplates(nextTemplates);
    if (nextCatalog !== null) setCatalog(nextCatalog);
    setLoading(false);
    onChanged?.();
  };

  const askAssistant = (prompt: string) => navigate(`/assistant?ask=${encodeURIComponent(prompt)}`);

  const remove = async (template: ResumeTemplateDetail) => {
    try {
      await deleteResumeTemplate(template.id);
      message.success(t("templatesUi.workbench.toast.deleted", { name: template.name }));
      void refreshAll();
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t("templatesUi.workbench.error.delete"),
      );
    }
  };

  const copyBuiltin = async (name: string) => {
    try {
      const source = await fetchBuiltinTemplateSource(name);
      setStyleEditor({
        open: true,
        html: source.html,
        name: t("templatesUi.workbench.copySuffix", { label: source.label }),
        config: source.config ?? {},
      });
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t("templatesUi.workbench.error.readBuiltin"),
      );
    }
  };

  const importFile = async (file: File) => {
    if (file.size > 400 * 1024) {
      message.warning(t("templatesUi.workbench.warning.tooLarge"));
      return;
    }
    setStyleEditor({
      open: true,
      html: await file.text(),
      name: file.name.replace(/\.(html?|j2)$/i, "").slice(0, 40),
      config: {},
    });
  };

  const styleTemplates = templates.filter((item) => item.kind === "style");
  const formatTemplates = templates.filter((item) => item.kind === "format");

  const editTemplate = (row: ResumeTemplateDetail) => {
    if (row.kind === "style") {
      setStyleEditor({ open: true, id: row.id, html: "", name: row.name, config: {} });
    } else {
      setFormatEditor({ open: true, template: row });
    }
  };

  const askTemplate = (row: ResumeTemplateDetail) =>
    askAssistant(`帮我调整格式模板「${row.name}」：`); // i18n-ok: 预填给求职助手的 prompt（模型输入）

  return (
    <div className="template-workbench">
      <Card
        size="small"
        className="settings-card"
        title={t("templatesUi.workbench.style.title")}
        extra={
          <Space wrap>
            <Dropdown
              menu={{
                items: (catalog?.templates ?? [])
                  .filter((item) => !item.custom)
                  .map((item) => ({
                    key: item.name,
                    label: `${item.label} · ${item.description}`,
                  })),
                onClick: ({ key }) => void copyBuiltin(key),
              }}
            >
              <Button icon={<CopyOutlined />}>
                {t("templatesUi.workbench.action.copyBuiltin")}
              </Button>
            </Dropdown>
            <FileDropZone
              accept=".html,.htm,.j2,.jinja,.txt"
              multiple={false}
              hint={t("templatesUi.workbench.uploadHint")}
              onFiles={(files) => void importFile(files[0])}
            >
              <label className="template-upload-button">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".html,.htm,.j2,.jinja,.txt"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void importFile(file);
                  }}
                />
                <Button
                  icon={<UploadOutlined />}
                  onClick={(event) => {
                    event.preventDefault();
                    fileInputRef.current?.click();
                  }}
                >
                  {t("templatesUi.workbench.action.importHtml")}
                </Button>
              </label>
            </FileDropZone>
            <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
              {t("templatesUi.workbench.action.importReference")}
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setStyleEditor({ open: true, html: "", name: "", config: {} })}
            >
              {t("templatesUi.workbench.action.createStyle")}
            </Button>
          </Space>
        }
        style={{ marginTop: 16 }}
      >
        <Collapse
          ghost
          defaultActiveKey={["builtin"]}
          items={[
            {
              key: "builtin",
              label: t("templatesUi.workbench.builtinStyles", {
                count: (catalog?.templates ?? []).filter((item) => !item.custom).length,
              }),
              children: (
                <BuiltinStyleGallery
                  items={(catalog?.templates ?? [])
                    .filter((item) => !item.custom)
                    .map((item) => ({
                      name: item.name,
                      label: item.label,
                      category: item.category,
                      description: item.description,
                    }))}
                />
              ),
            },
          ]}
        />
        {styleTemplates.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("templatesUi.workbench.empty.style")}
          />
        ) : (
          <TemplateCustomTable
            templates={styleTemplates}
            loading={loading}
            onPreview={setPreviewTemplate}
            onEdit={editTemplate}
            onAsk={askTemplate}
            onDelete={(row) => void remove(row)}
          />
        )}
      </Card>

      <Card
        size="small"
        className="settings-card"
        title={t("templatesUi.workbench.format.title")}
        style={{ marginTop: 16 }}
        extra={
          <Space wrap>
            <Button icon={<RobotOutlined />} onClick={() => askAssistant(t("templatesUi.workbench.prompt.newLayout"))}>
              {t("templatesUi.workbench.action.askAssistant")}
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setFormatEditor({ open: true, template: null })}
            >
              {t("templatesUi.workbench.action.create")}
            </Button>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          {t("templatesUi.workbench.builtinLabel")}
          {(catalog?.format_presets ?? [])
            .filter((item) => !item.custom)
            .map((item) => (
              <Tag key={item.name} className="template-chip">
                {item.label}
              </Tag>
            ))}
        </Typography.Paragraph>
        {formatTemplates.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("templatesUi.workbench.empty.format")}
          />
        ) : (
          <TemplateCustomTable
            templates={formatTemplates}
            loading={loading}
            onPreview={setPreviewTemplate}
            onEdit={editTemplate}
            onAsk={askTemplate}
            onDelete={(row) => void remove(row)}
          />
        )}
      </Card>

      <StyleTemplateEditorModal
        open={styleEditor.open}
        templateId={styleEditor.id ?? null}
        initialHtml={styleEditor.html}
        initialName={styleEditor.name}
        initialConfig={styleEditor.config}
        fields={catalog?.style_fields ?? []}
        onClose={() => setStyleEditor({ open: false, html: "", name: "", config: {} })}
        onSaved={() => void refreshAll()}
      />
      <FormatTemplateEditorModal
        open={formatEditor.open}
        fields={catalog?.format_fields ?? []}
        template={formatEditor.template}
        onClose={() => setFormatEditor({ open: false, template: null })}
        onSaved={() => void refreshAll()}
      />
      <TemplatePreviewModal
        template={previewTemplate}
        formatPresets={catalog?.format_presets ?? []}
        onClose={() => setPreviewTemplate(null)}
      />
      <TemplateImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        styleFields={catalog?.style_fields ?? []}
        onImported={() => void refreshAll()}
      />
    </div>
  );
}
