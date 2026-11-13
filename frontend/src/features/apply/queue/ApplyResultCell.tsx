// SPDX-License-Identifier: Apache-2.0
/**
 * 队列里的「投递结果」单元格：**投了没有、成没成、什么时候投的**。
 *
 * 为什么单独一列（2026-11-12 用户反馈「这个是什么意思？最好做个什么时候投递，
 * 然后是否投递成功的状态指示」）：
 *
 * 队列的 `status` 只有 pending/skipped/done/failed 四态，它回答的是"**要不要投**"。
 * 真正的执行结果在投递记录（`apply_task_item`）里，有独立的状态、时间与失败分类。
 * 以前界面只显示前者，于是用户看到一排「已投递」却不知道是什么时候投的、到底成没成。
 *
 * 显示规则：
 * - 没投过 → 灰字「未投递」
 * - success → 绿 Tag「已投递」+ 时间
 * - failed → 红 Tag「投递失败」+ 时间 + 失败分类
 * - skipped → 灰 Tag「已跳过」+ 时间
 * - running / pending → 蓝 Tag「投递中」
 */
import { Space, Tag, Tooltip, Typography } from "antd";

import { t, type MessageKey } from "../../../i18n";
import { useLocale } from "../../../i18n/i18nContext";
import { formatDateTime } from "../../../utils/format";
import type { ApplyQueueItem } from "../../../types";

const { Text } = Typography;

/** 投递记录状态 → 标签色。 */
const STATUS_COLOR = {
  success: "success",
  failed: "error",
  skipped: "default",
  running: "processing",
  pending: "processing",
} as const;

/** 投递记录状态 → 文案 key。 */
const STATUS_LABEL_KEYS: Record<string, MessageKey> = {
  success: "applyQueue.applyResult.success",
  failed: "applyQueue.applyResult.failed",
  skipped: "applyQueue.applyResult.skipped",
  running: "applyQueue.applyResult.running",
  pending: "applyQueue.applyResult.running",
};

/** 失败分类（稳定码）→ 文案 key。认不出的码原样显示，不吞掉信息。 */
const FAILURE_LABEL_KEYS: Record<string, MessageKey> = {
  captcha_required: "applyQueue.applyResult.failure.captcha",
  selector_invalid: "applyQueue.applyResult.failure.selector",
  login_required: "applyQueue.applyResult.failure.login",
  network_error: "applyQueue.applyResult.failure.network",
  rate_limited: "applyQueue.applyResult.failure.rateLimited",
  job_closed: "applyQueue.applyResult.failure.jobClosed",
  unknown: "applyQueue.applyResult.failure.unknown",
};

interface Props {
  item: ApplyQueueItem;
}

export default function ApplyResultCell({ item }: Props) {
  // 模块级 t()：必须订阅语言变化，否则切语言后这一格不重渲染。
  useLocale();

  const status = item.last_apply_status;

  // 从没投过：明确说「未投递」，而不是留空——空白让人分不清"没投"和"界面没做"。
  if (!status) {
    return <Text type="secondary">{t("applyQueue.applyResult.never")}</Text>;
  }

  const color = STATUS_COLOR[status] ?? "default";
  const labelKey = STATUS_LABEL_KEYS[status];
  const failureKey = item.last_failure_category
    ? FAILURE_LABEL_KEYS[item.last_failure_category]
    : undefined;

  return (
    <Space orientation="vertical" size={0}>
      <Space size={4} wrap>
        <Tag color={color} style={{ marginInlineEnd: 0 }}>
          {labelKey ? t(labelKey) : status}
        </Tag>
        {item.last_apply_at ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatDateTime(item.last_apply_at)}
          </Text>
        ) : null}
      </Space>
      {item.last_failure_category ? (
        <Tooltip title={item.last_failure_category}>
          {/* 失败分类只给一句话结论，完整诊断在「投递记录」里看。 */}
          <Text type="danger" style={{ fontSize: 12 }}>
            {failureKey ? t(failureKey) : item.last_failure_category}
          </Text>
        </Tooltip>
      ) : null}
    </Space>
  );
}
