// SPDX-License-Identifier: Apache-2.0
/**
 * 教练给的参考答案卡片。
 *
 * 为什么单独一块、不塞进对话流：对话流里只有两种话——候选人说的、面试官说的。
 * 教练的话混进去，复盘时分不清"这句是我答的吗"。
 *
 * 为什么显式标注 `grounded`：参考答案分两种——
 * - 完全来自他的资料（grounded=true）：可以照着说；
 * - 含可迁移表述（grounded=false）：只能借思路，**不能当真实经历讲**。
 *   真实面试第二轮追问就崩，比说"不知道"更伤。这条提示不能省。
 */
import { CloseOutlined, BulbOutlined, WarningOutlined } from "@ant-design/icons";
import { Button, Space, Tag, Typography } from "antd";
import type { InterviewCoachAnswer } from "../../types";
import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";

export function CoachAnswerCard({
  answer,
  onDismiss,
}: {
  answer: InterviewCoachAnswer;
  onDismiss: () => void;
}) {
  useLocale();
  return (
    <div className="interview-coach-card">
      <div className="interview-coach-card-head">
        <Space size={6}>
          <BulbOutlined />
          <Typography.Text strong>{t("interview.coach.title")}</Typography.Text>
          {answer.grounded ? (
            <Tag color="green">{t("interview.coach.groundedTag")}</Tag>
          ) : (
            <Tag color="orange" icon={<WarningOutlined />}>
              {t("interview.coach.partialTag")}
            </Tag>
          )}
        </Space>
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          aria-label={t("interview.coach.dismiss")}
          onClick={onDismiss}
        />
      </div>

      <Typography.Paragraph className="interview-coach-answer">{answer.answer}</Typography.Paragraph>

      {answer.outline.length > 0 ? (
        <div className="interview-coach-block">
          <Typography.Text type="secondary">{t("interview.coach.outlineLabel")}</Typography.Text>
          <ul className="interview-coach-outline">
            {answer.outline.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {answer.sources.length > 0 ? (
        <div className="interview-coach-block">
          <Typography.Text type="secondary">{t("interview.coach.sourcesLabel")}</Typography.Text>
          <Space size={4} wrap>
            {answer.sources.map((source) => (
              <Tag key={source}>{source}</Tag>
            ))}
          </Space>
        </div>
      ) : null}

      {answer.gaps.length > 0 ? (
        <div className="interview-coach-block">
          <Typography.Text type="warning">{t("interview.coach.gapsLabel")}</Typography.Text>
          <ul className="interview-coach-outline">
            {answer.gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 两条免责说明必须常驻：一条讲"不进评分"，一条讲"资料里没有的别硬讲"。 */}
      <Typography.Text type="secondary" className="interview-coach-note">
        {answer.grounded ? t("interview.coach.noteGrounded") : t("interview.coach.notePartial")}
      </Typography.Text>
      <Typography.Text type="secondary" className="interview-coach-note">
        {t("interview.coach.noteNotScored")}
      </Typography.Text>
    </div>
  );
}

export default CoachAnswerCard;
