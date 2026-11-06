// SPDX-License-Identifier: Apache-2.0
/**
 * 设置表单（P3-2）：引擎路径/端口、自动启动、AI 只读引用 + 同步按钮、简历上传按钮。
 * AI 配置唯一来源是简历通全局 LLM Profile——这里不出现第二个 Key 输入框。
 */
import { App, Button, Card, Checkbox, Form, Input, InputNumber, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { getAiJobsConfig, saveAiJobsConfig, syncLlmToEngine, syncResumeToEngine } from "../../api/aiJobs";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { AiJobsConfig } from "../../types/aiJobs";

export default function SettingsForm({ onSaved }: { onSaved: () => void }) {
  useLocale();
  const { message } = App.useApp();
  const [form] = Form.useForm<AiJobsConfig>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [llmSyncing, setLlmSyncing] = useState(false);
  const [resumeSyncing, setResumeSyncing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAiJobsConfig()
      .then((config) => {
        if (!cancelled) form.setFieldsValue(config);
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
  }, [form]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      await saveAiJobsConfig(values);
      void message.success(t("aiJobs.settings.saved"));
      onSaved();
    } catch (error) {
      if (error instanceof Error && error.message) {
        void message.error(error.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleLlmSync = async () => {
    setLlmSyncing(true);
    try {
      const result = await syncLlmToEngine();
      void message.success(t("aiJobs.settings.llmSynced", { model: result.model }));
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.settings.llmSynced", { model: "" }));
    } finally {
      setLlmSyncing(false);
    }
  };

  const handleResumeSync = async () => {
    setResumeSyncing(true);
    try {
      const result = await syncResumeToEngine();
      void message.success(result.uploaded ? t("aiJobs.resume.uploaded") : t("aiJobs.resume.skipped"));
    } catch (error) {
      void message.error(error instanceof Error ? error.message : t("aiJobs.resume.uploaded"));
    } finally {
      setResumeSyncing(false);
    }
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title={t("aiJobs.settings.engine")} loading={loading}>
        <Form<AiJobsConfig> form={form} layout="vertical">
          <Form.Item
            name="engine_repo"
            label={t("aiJobs.settings.engineRepo")}
            rules={[{ required: true, message: t("aiJobs.settings.engineRepoRequired") }]}
          >
            <Input placeholder={t("aiJobs.settings.engineRepoPlaceholder")} />
          </Form.Item>
          <Form.Item
            name="engine_python"
            label={t("aiJobs.settings.enginePython")}
            rules={[{ required: true, message: t("aiJobs.settings.enginePythonRequired") }]}
          >
            <Input placeholder={t("aiJobs.settings.enginePythonPlaceholder")} />
          </Form.Item>
          <Space size="middle" wrap>
            <Form.Item name="engine_port" label={t("aiJobs.settings.enginePort")} style={{ marginBottom: 0 }}>
              <InputNumber min={1} max={65535} />
            </Form.Item>
            <Form.Item name="proxy_port" label={t("aiJobs.settings.proxyPort")} style={{ marginBottom: 0 }}>
              <InputNumber min={1} max={65535} />
            </Form.Item>
            <Form.Item name="browser_port" label={t("aiJobs.settings.browserPort")} style={{ marginBottom: 0 }}>
              <InputNumber min={1} max={65535} />
            </Form.Item>
            <Form.Item name="auto_start" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Checkbox>{t("aiJobs.settings.autoStart")}</Checkbox>
            </Form.Item>
          </Space>
          <Button type="primary" loading={saving} onClick={() => void handleSave()} style={{ marginTop: 16 }}>
            {t("aiJobs.settings.save")}
          </Button>
        </Form>
      </Card>
      <Card title={t("aiJobs.settings.ai")}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          {t("aiJobs.settings.aiReadOnly")}
        </Typography.Paragraph>
        <Space wrap>
          <Button loading={llmSyncing} onClick={() => void handleLlmSync()}>
            {t("aiJobs.settings.llmSync")}
          </Button>
          <Button loading={resumeSyncing} onClick={() => void handleResumeSync()}>
            {t("aiJobs.resume.sync")}
          </Button>
        </Space>
      </Card>
    </Space>
  );
}
