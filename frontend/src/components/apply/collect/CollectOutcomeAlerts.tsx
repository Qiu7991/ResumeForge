// SPDX-License-Identifier: Apache-2.0
/**
 * 采集批次的两张账目 Alert：「未生效条件」/「站点侧筛选」，
 * 以及可选的「翻页提前停止」与「感兴趣失效岗位」说明。
 *
 * 纯展示组件——账目由 collectTaskSummary.ts 从 task.config 解析后经 props 传入。
 */
import { Alert, Typography } from "antd";
import { t } from "../../../i18n";
import { useLocale } from "../../../i18n/i18nContext";
import type { SiteFilterSummary } from "./collectTaskSummary";

interface Props {
  unmapped: string[];
  siteFiltered: SiteFilterSummary | null;
  /** 翻页提前停止的页码（0/缺省 = 没有触发）。 */
  paginationStoppedAt?: number;
  /** 「感兴趣」来源里失效岗位的条数（0/缺省 = 没有失效卡）。 */
  interestInvalid?: number;
  /** 「感兴趣」来源里**库里已经有的**、因此跳过的条数（0/缺省 = 没跳过）。 */
  interestAlreadyKnown?: number;
  /** 「感兴趣」来源本轮实际查看了多少个收藏位置（0/缺省 = 没记录）。 */
  interestScanned?: number;
}

export default function CollectOutcomeAlerts({
  unmapped,
  siteFiltered,
  paginationStoppedAt = 0,
  interestInvalid = 0,
  interestAlreadyKnown = 0,
  interestScanned = 0,
}: Props) {
  // 本组件用模块级 t()：必须订阅语言变化，否则切语言后账目停在旧文案。
  useLocale();
  const separator = t("applyCollect.outcome.listSeparator");
  return (
    <div className="apply-collect-outcomes">
      {interestInvalid > 0 && (
        <Alert
          className="apply-collect-interest-invalid"
          type="info"
          showIcon
          title={t("applyCollect.outcome.interest.invalid", { count: interestInvalid })}
        />
      )}
      {(interestScanned > 0 || interestAlreadyKnown > 0) && (
        <Alert
          className="apply-collect-interest-scan"
          type="info"
          showIcon
          title={t("applyCollect.outcome.interest.scan", {
            scanned: interestScanned,
            known: interestAlreadyKnown,
          })}
          description={t("applyCollect.outcome.interest.scanHint")}
        />
      )}
      {paginationStoppedAt > 0 && (
        <Alert
          className="apply-collect-pagination"
          type="info"
          showIcon
          title={t("applyCollect.outcome.pagination.title", { page: paginationStoppedAt })}
          description={t("applyCollect.outcome.pagination.description")}
        />
      )}
      {unmapped.length > 0 && (
        <Alert
          className="apply-collect-unmapped"
          type="warning"
          showIcon
          title={t("applyCollect.outcome.unmapped.title")}
          description={
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              {t("applyCollect.outcome.unmapped.description", {
                conditions: unmapped.join(separator),
              })}
            </Typography.Paragraph>
          }
        />
      )}

      {/* 站点侧筛选的账目：**哪几条真的生效了**，以及**哪几条没能生效**。后端早就把这两笔账
          写进了批次配置，一直没在界面上露面——那等于记了账不给看。 */}
      {siteFiltered && (
        <Alert
          className="apply-collect-site-filtered"
          type={siteFiltered.unapplied.length > 0 ? "warning" : "success"}
          showIcon
          title={
            siteFiltered.applied.length > 0
              ? t("applyCollect.outcome.siteFiltered.appliedTitle", {
                  conditions: siteFiltered.applied.join(separator),
                })
              : t("applyCollect.outcome.siteFiltered.unappliedTitle")
          }
          description={
            siteFiltered.unapplied.length > 0 ? (
              <Typography.Text type="danger">
                {t("applyCollect.outcome.siteFiltered.unappliedDescription", {
                  conditions: siteFiltered.unapplied.join(separator),
                })}
              </Typography.Text>
            ) : (
              <Typography.Text type="secondary">
                {t("applyCollect.outcome.siteFiltered.appliedDescription")}
              </Typography.Text>
            )
          }
        />
      )}
    </div>
  );
}
