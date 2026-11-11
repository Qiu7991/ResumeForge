// SPDX-License-Identifier: Apache-2.0
/**
 * 采集链路的阶段进度面板：采集 → 落库 → 补 JD → 评分，四步各是什么状态一眼可见。
 *
 * 为什么需要独立一块（2026-11-11 用户反馈「点了之后就转了一下，状态指示不明显」）：
 *
 * 1. 原来只有一枚 `Tag` 显示 running/completed，中间那两步（落库、补 JD）**完全不可见**；
 * 2. 后端其实一直在推进（`task.stage` 会走 collected → staged → filling_jd → scoring），
 *    但界面没消费这个字段；
 * 3. 采集任务先结束（`finished: true`）、评分任务还在跑——只看采集任务的状态会以为
 *    「已经完成了」，实际分数还没出。
 *
 * 所以这里把**两个任务**（采集 + 评分）合成一条进度链来显示，并给出每一步的计数。
 */
import { Alert, Button, Progress, Space, Steps, Tag, Typography } from "antd";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { CollectTaskSnapshot } from "../../types/jobHunt";
import type { CandidateScoreTask } from "../../api/candidateJob";

const { Text } = Typography;

export type StageKey = "collect" | "stage" | "fill_jd" | "score";

interface Props {
  /** 采集任务快照；还没开始采时为 null。 */
  task: CollectTaskSnapshot | null;
  /** 评分任务快照；没起评分时为 null。 */
  scoreTask: CandidateScoreTask | null;
  collecting: boolean;
  onStartBrowser: () => void;
  startingBrowser: boolean;
}

/**
 * 后端 ``task.stage`` → 进度链走到第几步。
 *
 * 后端只在采集线程里推进这个字段；评分是另一个任务，所以"评分走到哪"要看
 * ``scoreTask`` 而不是 ``task.stage``。
 */
function collectStep(task: CollectTaskSnapshot | null): number {
  if (!task) return 0;
  switch (task.stage) {
    case "collected":
      return 1;
    case "staged":
      return 2;
    case "filling_jd":
      return 3;
    case "scoring":
      return 4;
    default:
      return 0;
  }
}

export default function CollectProgressPanel({
  task,
  scoreTask,
  collecting,
  onStartBrowser,
  startingBrowser,
}: Props) {
  // 模块级 t() 必须订阅语言变化，否则切语言后这一块不重渲染。
  useLocale();

  const scoreRunning = Boolean(scoreTask?.running);
  const failed = task?.status === "failed" || Boolean(task?.error);
  // 采集失败且是"浏览器没启动"时直接给补救按钮——这是最常见的失败原因。
  // 判据是后端返回的**协议值前缀** ``browser_required``，不是中文文案匹配：
  // 靠文案匹配时后端改一次措辞，这个按钮就静默消失，用户又回到"转一下没反应"。
  const needsBrowser = failed && (task?.error ?? "").startsWith("browser_required");

  const step = collectStep(task);
  // 采集任务自己结束后评分还在跑：进度链要停在「评分」这一步的进行中。
  const current = scoreRunning ? 3 : Math.max(0, step - 1);

  const items = [
    {
      title: t("aiJobs.progress.step.collect"),
      description: collecting ? t("aiJobs.progress.collecting") : undefined,
    },
    {
      title: t("aiJobs.progress.step.stage"),
      description: task?.candidate_count ? `${task.candidate_count}` : undefined,
    },
    {
      title: t("aiJobs.progress.step.fillJd"),
      description: task?.jd_filled ? `${task.jd_filled}` : undefined,
    },
    {
      title: t("aiJobs.progress.step.score"),
      description: scoreTask?.requested
        ? `${scoreTask.completed ?? 0}/${scoreTask.requested}`
        : undefined,
    },
  ];

  // 后端错误可能带协议值前缀（`browser_required: `），展示前剥掉——
  // 前缀是给代码判断用的，不该出现在用户看到的那句话里。
  const errorText = (task?.error ?? "").replace(/^[a-z_]+:\s*/, "");

  return (
    <div
      style={{
        marginTop: 12,
        padding: "12px 16px",
        borderRadius: 8,
        background: "rgba(0,0,0,0.02)",
        border: "1px solid rgba(0,0,0,0.06)",
      }}
    >
      <Steps
        size="small"
        current={current}
        status={failed ? "error" : scoreRunning || collecting ? "process" : "finish"}
        items={items}
      />

      <Space wrap style={{ marginTop: 12 }}>
        <Tag
          color={
            failed ? "error" : task?.status === "paused" ? "warning" : scoreRunning || collecting ? "processing" : "success"
          }
        >
          {scoreRunning
            ? t("aiJobs.progress.badge.scoring")
            : failed
              ? t("aiJobs.progress.badge.failed")
              : collecting
                ? t("aiJobs.progress.badge.collecting")
                : t("aiJobs.progress.badge.done")}
        </Tag>
        <Text type="secondary">{scoreRunning ? scoreTask?.message : task?.message}</Text>
        {task?.duplicates ? (
          <Text type="secondary">{t("aiJobs.progress.duplicates", { count: task.duplicates })}</Text>
        ) : null}
        {task?.blocked ? (
          <Text type="secondary">{t("aiJobs.native.blockedCount", { count: task.blocked })}</Text>
        ) : null}
      </Space>

      {scoreRunning && scoreTask?.requested ? (
        <Progress
          size="small"
          style={{ marginTop: 8, maxWidth: 360 }}
          percent={Math.round(
            (((scoreTask.completed ?? 0) + (scoreTask.failed ?? 0)) / scoreTask.requested) * 100,
          )}
          status="active"
        />
      ) : null}

      {failed ? (
        <Alert
          style={{ marginTop: 8 }}
          type="error"
          showIcon
          message={t("aiJobs.progress.failedTitle")}
          description={errorText || undefined}
          action={
            needsBrowser ? (
              <Button size="small" onClick={onStartBrowser} loading={startingBrowser}>
                {t("aiJobs.native.startBrowser")}
              </Button>
            ) : undefined
          }
        />
      ) : null}

      {scoreTask?.errors?.length ? (
        <Alert
          style={{ marginTop: 8 }}
          type="warning"
          showIcon
          message={t("aiJobs.progress.scoreErrors", { count: scoreTask.errors.length })}
          description={scoreTask.errors.slice(0, 5).join(t("aiJobs.native.errorSeparator"))}
        />
      ) : null}
    </div>
  );
}
