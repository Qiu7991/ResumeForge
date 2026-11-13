// SPDX-License-Identifier: Apache-2.0
/**
 * 备选岗位列表里的「匹配分」单元格：只渲染，**不发请求**。
 *
 * 为什么不做成会自己拉数据的组件：备选列表一屏 15-20 行，逐行请求分数会变成 N+1。
 * 分数是列表接口一起下发的概要字段（`score_total`/`score_error`），明细点开才要。
 *
 * 配色沿用岗位批量结果那一套（`JobMatchBatchResult.tsx`）：≥70 绿、40–69 蓝、
 * <40 琥珀。**纯展示口径**——颜色只帮视线定位高低，不构成第二套结论。
 */
import { Tag, Tooltip, Typography } from "antd";

import { t } from "../../../i18n";
import { useLocale } from "../../../i18n/i18nContext";

const { Text } = Typography;

interface Props {
  /** 语义评分总分；`null`/`undefined` = 还没评过（不是 0 分）。 */
  score: number | null | undefined;
  /** 评分失败原因；空串/未给 = 无错。 */
  error?: string;
}

function scoreColor(score: number): string {
  if (score >= 70) return "#3f9d63";
  if (score >= 40) return "#5b8ff9";
  return "#e6a23c";
}

export default function CandidateScoreCell({ score, error }: Props) {
  // 用模块级 t()：必须订阅语言变化，否则切换语言后这一格不重渲染。
  useLocale();

  if (error) {
    // 缺 JD 是最常见的一种，单独给文案：它不是失败，是"还没有可评的输入"。
    // 判据是后端给的**协议值前缀** `jd_missing`，不是中文串匹配——后端改一次
    // 错误文案，`includes("缺 JD")` 就会静默失效，而界面看上去只是少了提示。
    const isMissingJd = error.startsWith("jd_missing");
    return (
      <Tooltip title={error}>
        <Tag color={isMissingJd ? "default" : "error"} style={{ marginInlineEnd: 0 }}>
          {isMissingJd ? t("aiJobs.candidate.jdMissing") : t("aiJobs.candidate.scoreFailed")}
        </Tag>
      </Tooltip>
    );
  }

  if (score === null || score === undefined) {
    return <Text type="secondary">{t("aiJobs.candidate.notScored")}</Text>;
  }

  return (
    <Text strong style={{ color: scoreColor(score) }}>
      {score}
    </Text>
  );
}
