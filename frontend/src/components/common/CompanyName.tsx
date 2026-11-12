// SPDX-License-Identifier: Apache-2.0
/**
 * 公司名渲染：能查风鸟就渲染成链接，查不了就渲染成纯文本 + 说明。
 *
 * 抽成组件而不是在每个表格里各写一遍：四个地方都要「有全名给链接、截断名给提示」，
 * 各写一份必然分叉——而分叉的表现是「有的地方能点、有的地方不能点」，用户会当成 bug。
 *
 * 链接行为：`target="_blank" rel="noopener noreferrer"` → 系统默认浏览器新标签。
 * 用户明确选了系统默认浏览器（不是投递专用浏览器 Ego Lite），因为风鸟与 BOSS 登录态无关，
 * 混进投递专用浏览器反而会污染那边的 profile。
 */
import { Tooltip, Typography } from "antd";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import { companyLookupName, riskbirdUrl } from "../../utils/companyLookup";

interface Props {
  /** 公司名（可能是品牌短名或带 `...` 的截断串）。 */
  name: string | null | undefined;
  /** 为真时公司名不可点（如批量操作进行中）。 */
  disabled?: boolean;
}

export default function CompanyName({ name, disabled = false }: Props) {
  // 模块级 t()：必须订阅语言变化，否则切语言后提示语不重渲染。
  useLocale();

  const raw = (name ?? "").trim();
  if (!raw) return <Typography.Text type="secondary">-</Typography.Text>;

  const url = disabled ? null : riskbirdUrl(raw);
  if (url !== null) {
    return (
      <Tooltip title={t("company.lookupHint", { name: companyLookupName(raw) ?? raw })}>
        <Typography.Link href={url} target="_blank" rel="noopener noreferrer">
          {raw}
        </Typography.Link>
      </Tooltip>
    );
  }

  // 查不了：说明原因，别让用户以为是按钮坏了。
  // 两种情况分开说——截断名要提示「补抓详情」，短名要说「招聘网站只给了品牌名」。
  const isTruncated = /\.\.\.$|…$/.test(raw);
  const hint = isTruncated
    ? t("company.truncatedHint")
    : t("company.shortNameHint");
  return (
    <Tooltip title={hint}>
      <Typography.Text>{raw}</Typography.Text>
    </Tooltip>
  );
}
