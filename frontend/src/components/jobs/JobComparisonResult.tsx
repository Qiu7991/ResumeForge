/**
 * 横向对比结果：名次 + 每个岗位"为什么排在这里"。
 *
 * 与逐岗卡片的分工：这里是**相对判断**（谁更适合、差在哪），下方卡片仍是每个岗位的
 * 五类结论与参考分。两者不重复，也不互相推导——排序不出现百分比，参考分不参与排序。
 */
import { Card, Space, Tag, Typography } from "antd";
import type { JobComparisonResult, JobComparisonVerdict, JobMatchBatchItem } from "../../types";

const VERDICT_META: Record<JobComparisonVerdict, { color: string; label: string }> = {
  best: { color: "green", label: "最合适" },
  good: { color: "blue", label: "较合适" },
  fair: { color: "gold", label: "一般" },
  weak: { color: "default", label: "偏弱" },
};

export default function JobComparisonResult({
  comparison,
  items,
}: {
  comparison: JobComparisonResult;
  items: JobMatchBatchItem[];
}) {
  const jobById = new Map(items.map((item) => [item.job_id, item]));
  const ranked = [...comparison.items].sort((left, right) => left.rank - right.rank);
  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      {comparison.error ? (
        <Typography.Text type="warning">{comparison.error}</Typography.Text>
      ) : (
        <Card size="small">
          <Typography.Paragraph strong style={{ marginBottom: 0 }}>
            {comparison.summary}
          </Typography.Paragraph>
        </Card>
      )}
      {ranked.map((entry) => {
        const job = jobById.get(entry.job_id);
        const verdict = VERDICT_META[entry.verdict] ?? VERDICT_META.fair;
        return (
          <Card
            key={entry.job_id}
            size="small"
            title={
              <Space size={6} wrap>
                <Tag color={entry.rank === 1 ? "gold" : "default"}>第 {entry.rank} 名</Tag>
                <span>{job?.job_title ?? entry.headline}</span>
                {job?.company ? (
                  <Typography.Text type="secondary">· {job.company}</Typography.Text>
                ) : null}
              </Space>
            }
            extra={<Tag color={verdict.color}>{verdict.label}</Tag>}
          >
            {entry.headline ? <Typography.Paragraph>{entry.headline}</Typography.Paragraph> : null}
            <ul style={{ margin: "0 0 8px", paddingLeft: 20 }}>
              {entry.reasons.map((reason, index) => (
                <li key={`${entry.job_id}-reason-${index}`}>{reason}</li>
              ))}
            </ul>
            {entry.concerns.length > 0 ? (
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                需要留意：{entry.concerns.join("；")}
              </Typography.Paragraph>
            ) : null}
          </Card>
        );
      })}
      <Typography.Text type="secondary">
        排序是相对判断，不出现百分比评分；参考分仅作展示，不参与排序与准入。
      </Typography.Text>
      {comparison.notes.map((note, index) => (
        <Typography.Text key={`comparison-note-${index}`} type="secondary">
          {note}
        </Typography.Text>
      ))}
    </Space>
  );
}
