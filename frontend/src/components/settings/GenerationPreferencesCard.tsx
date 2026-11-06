// SPDX-License-Identifier: Apache-2.0
/**
 * 生成偏好卡（设置页 · 应用）：简历里是否单独显示项目技术栈。
 *
 * 默认关。关闭的含义是"不上纸面"，不是删除：技术栈数据仍在简历文档里，
 * 编辑器里可以拖回来。旧简历不受影响——偏好只在生成/保存那一刻读取。
 */
import { App, Card, Space, Switch, Typography } from "antd";
import LoadingBlock from "../common/LoadingBlock";
import { useShowTechStack } from "../../features/settings/useShowTechStack";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

export default function GenerationPreferencesCard() {
  useLocale();
  const { message } = App.useApp();
  const { enabled, loading, saving, toggle } = useShowTechStack();

  const onChange = async (checked: boolean) => {
    const saved = await toggle(checked);
    if (saved === checked) {
      message.success(
        checked
          ? t("settingsUi.generationPrefs.enableToast")
          : t("settingsUi.generationPrefs.disableToast"),
      );
    } else {
      message.error(t("settingsUi.generationPrefs.saveFailed"));
    }
  };

  return (
    <Card title={t("settingsUi.generationPrefs.title")} className="settings-card">
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {t("settingsUi.generationPrefs.intro")}
      </Typography.Paragraph>
      <LoadingBlock spinning={loading}>
        <Space orientation="vertical" size={4}>
          <Switch
            checked={enabled}
            loading={saving}
            checkedChildren={t("settingsUi.switch.on")}
            unCheckedChildren={t("settingsUi.switch.off")}
            aria-label={t("settingsUi.generationPrefs.toggleAria")}
            onChange={(checked) => void onChange(checked)}
          />
          <Typography.Text type="secondary">
            {t("settingsUi.generationPrefs.hint")}
          </Typography.Text>
        </Space>
      </LoadingBlock>
    </Card>
  );
}
