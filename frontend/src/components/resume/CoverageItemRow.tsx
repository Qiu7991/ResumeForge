// SPDX-License-Identifier: Apache-2.0
/**
 * 未收录清单的**一项**：平铺展示内容 + 该项自己的操作按钮。
 *
 * ## 为什么改成"平铺 + 逐条按钮"（2026-11-08）
 *
 * 原实现是「一列名字（长条目省略号 + Tooltip）+ 组底部一个『补进简历』」。
 * 用户反馈：「到底怎么用才能选择补写……我想要能选择性的补哪几条，
 * 而不是全让 AI 做决策」；1.x 的样子正是**每条内容整段可见、各自带按钮**。
 *
 * 改完之后：
 * - 内容**完整展示**（不再省略号），用户读到具体内容再决定要不要；
 * - 每条**各自补入**（后端 `append-profile-entries` 本来就收 entry_ids 数组，
 *   只是前端一直整组传）；
 * - 补完之后这条就地变成「AI 润色这段」——补的是原文事实，润色是可选的独立动作，
 *   不合并成一步（合并会让"这段到底是谁写的"说不清）。
 */
import { Button, Space, Tooltip } from "antd";
import { useI18n, useLocale } from "../../i18n/i18nContext";
import { coverageReasonLabelKey, type CoverageItemReason } from "./coverageGroups";

interface Props {
  /** 资料条目的身份名 / 整段正文（后端下发的原文，不裁剪、不改写）。 */
  name: string;
  /** 这条为什么没写进简历；`null` = 未说明。 */
  reason: CoverageItemReason;
  /** 仅混合原因的组传 true：纯因一组时不逐条贴标签。 */
  showReason?: boolean;
  /** 确定性补入这一条（只有该条能定位到资料条目时才给）。 */
  onAppend?: () => void;
  /** 这条正在补入。 */
  appending?: boolean;
  /** 已经补进正文：按钮换成「AI 润色这段」。 */
  appended?: boolean;
  /** 润色刚补的这条（补完才可用）。 */
  onPolish?: () => void;
  /** 润色请求在飞。 */
  polishing?: boolean;
}

export default function CoverageItemRow({
  name,
  reason,
  showReason = false,
  onAppend,
  appending = false,
  appended = false,
  onPolish,
  polishing = false,
}: Props) {
  // 用了 `t()` 就必须订阅语言变化，否则切语言后这一行不重渲染。
  useLocale();
  const { t } = useI18n();
  // 引号口径与旧版提示块一致（`resume.coverage.item`）。
  const label = t("resume.coverage.item", { name });
  const reasonText = showReason ? t(coverageReasonLabelKey(reason)) : "";

  return (
    <li className="resume-coverage-item-row">
      <div className="resume-coverage-item-body">
        <span className="resume-coverage-item">{label}</span>
        {reasonText ? (
          <Tooltip title={t("resume.coverage.reasonHint")}>
            <span className="resume-coverage-item-reason">{reasonText}</span>
          </Tooltip>
        ) : null}
      </div>
      {appended ? (
        <Space size={6} className="resume-coverage-item-actions">
          {onPolish ? (
            <Button size="small" loading={polishing} onClick={onPolish}>
              {t("resume.coverage.polishThis")}
            </Button>
          ) : null}
          <span className="resume-coverage-item-done">{t("resume.coverage.appendedTag")}</span>
        </Space>
      ) : onAppend ? (
        <Space size={6} className="resume-coverage-item-actions">
          <Button size="small" loading={appending} onClick={onAppend}>
            {t("resume.coverage.appendThis")}
          </Button>
        </Space>
      ) : null}
    </li>
  );
}
