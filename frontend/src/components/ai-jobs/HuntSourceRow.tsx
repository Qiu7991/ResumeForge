// SPDX-License-Identifier: Apache-2.0
/**
 * 采集的「数据源与动作」分组：去哪搜（平台 / 城市 / 翻页数 / 分数线）+ 开始按钮。
 *
 * 为什么从 `NativeJobHuntView` 抽出来：
 * 1. 职责本来就不同——上半区决定**搜什么**（关键词与站点筛选，改得频繁），
 *    这一区决定**这次跑哪儿、跑多久**（平台/城市/页数，一年改几次）；
 * 2. 页面文件已经顶到 500 行预算，而这两区之间没有共享状态，拆开不需要
 *    往上层传一堆回调。
 *
 * 所有值都受控：默认值与持久化在页面里（`usePersistentValue`），这里只负责渲染，
 * 不做任何"自己记住"的动作——两处各记一份必然分叉。
 */
import { Button, Checkbox, Input, InputNumber, Select, Space, Tooltip, Typography } from "antd";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { JobHuntStatus } from "../../types/jobHunt";

const { Text } = Typography;

interface Props {
  status: JobHuntStatus;
  siteKey: string;
  onSiteKeyChange: (next: string) => void;
  city: string;
  onCityChange: (next: string) => void;
  maxPages: number;
  onMaxPagesChange: (next: number) => void;
  /** 分数线（分水岭）：不低于它的候选排上面。 */
  threshold: number;
  onThresholdChange: (next: number) => void;
  autoScore: boolean;
  onAutoScoreChange: (next: boolean) => void;
  keywords: number;
  collecting: boolean;
  starting: boolean;
  onCollect: () => void;
  /** 采集中可暂停/继续；`paused` 决定按钮文案。 */
  paused: boolean;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

export default function HuntSourceRow({
  status,
  siteKey,
  onSiteKeyChange,
  city,
  onCityChange,
  maxPages,
  onMaxPagesChange,
  threshold,
  onThresholdChange,
  autoScore,
  onAutoScoreChange,
  keywords,
  collecting,
  starting,
  onCollect,
  paused,
  onPause,
  onResume,
  onStop,
}: Props) {
  // 模块级 t() 不会自己重渲染：必须订阅语言变化，否则切语言后这一区不跟着变。
  useLocale();

  return (
    <div className="hunt-section">
      <div className="hunt-section-title">
        <Text strong>{t("aiJobs.hunt.sectionSource")}</Text>
      </div>
      <div className="hunt-source-row">
        <div className="hunt-field">
          <span className="hunt-field-label">{t("aiJobs.hunt.platform")}</span>
          <div className="hunt-field-control">
            <Select
              value={siteKey}
              onChange={onSiteKeyChange}
              style={{ width: "100%" }}
              options={status.platforms.map((platform) => ({
                value: platform.key,
                label: platform.name,
              }))}
              aria-label={t("aiJobs.hunt.platform")}
            />
          </div>
        </div>
        <div className="hunt-field">
          <span className="hunt-field-label">{t("aiJobs.native.city")}</span>
          <div className="hunt-field-control">
            <Input value={city} onChange={(e) => onCityChange(e.target.value)} aria-label={t("aiJobs.native.city")} />
          </div>
        </div>
        <div className="hunt-field">
          <span className="hunt-field-label">{t("aiJobs.hunt.pagesLabel")}</span>
          <div className="hunt-field-control">
            <Select
              value={maxPages}
              onChange={onMaxPagesChange}
              style={{ width: "100%" }}
              options={[1, 2, 3, 5].map((n) => ({
                value: n,
                label: t("aiJobs.native.pages", { n }),
              }))}
              aria-label={t("aiJobs.hunt.pagesLabel")}
            />
          </div>
        </div>
        <div className="hunt-field hunt-field--narrow">
          <Tooltip title={t("aiJobs.hunt.thresholdHint")}>
            <span className="hunt-field-label">{t("aiJobs.hunt.threshold")}</span>
          </Tooltip>
          <div className="hunt-field-control">
            <InputNumber
              value={threshold}
              onChange={(value) => onThresholdChange(typeof value === "number" ? value : 70)}
              min={0}
              max={100}
              step={5}
              style={{ width: "100%" }}
              aria-label={t("aiJobs.hunt.threshold")}
            />
          </div>
        </div>
      </div>

      <Space wrap size={12} style={{ marginTop: 12 }}>
        <Tooltip title={t("aiJobs.native.autoScoreHint")}>
          <Checkbox checked={autoScore} onChange={(e) => onAutoScoreChange(e.target.checked)}>
            {t("aiJobs.native.autoScore")}
          </Checkbox>
        </Tooltip>
        <Button type="primary" loading={starting || collecting} disabled={collecting} onClick={onCollect}>
          {t("aiJobs.native.collect")}
        </Button>
        {collecting && (
          <>
            {paused ? (
              <Button onClick={onResume}>{t("aiJobs.pipeline.resume")}</Button>
            ) : (
              <Button onClick={onPause}>{t("aiJobs.pipeline.pause")}</Button>
            )}
            <Button danger onClick={onStop}>
              {t("aiJobs.pipeline.stop")}
            </Button>
          </>
        )}
        {/* 组合数提示：4 词 × 3 页 = 12 次翻页，点之前先让人知道要跑多久。 */}
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t("aiJobs.hunt.comboHint", {
            keywords: keywords || 1,
            pages: maxPages,
            total: (keywords || 1) * maxPages,
          })}
        </Text>
      </Space>
    </div>
  );
}
