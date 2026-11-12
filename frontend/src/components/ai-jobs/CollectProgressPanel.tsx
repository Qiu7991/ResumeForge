// SPDX-License-Identifier: Apache-2.0
/**
 * 采集链路的阶段卡片流：采集 → 写入待导入 → 补抓 JD → AI 评分。
 *
 * 为什么不用 Steps 圆点（2026-11-12 用户反馈「进度显示还是不明显」）：
 *
 * 1. **Steps 只有"走到第几步"，没有"这一步走到哪儿"**。评分 12 条要两分钟，期间只
 *    看到一个圆点在转，不知道是 1/12 还是 11/12。
 * 2. **没有总量概念**。用户要判断"还要等多久"，得看到 `8/12` 这种比值。
 * 3. 四步里有两步（写入待导入、补抓 JD）原本连数字都没有。
 *
 * 卡片方案把每步摊成一张：大数字 + 一句状态 + 该步自己的进度条。一眼能看出
 * 「哪一步在跑、跑到几分之几、还剩几步」。
 *
 * 状态色只表达**这一步的处境**，不表达成功/失败的价值判断（用灰/蓝/绿/红四色）。
 */
import { Alert, Button, Progress, Space, Tag, Typography } from "antd";

import { t } from "../../i18n";
import { useLocale } from "../../i18n/i18nContext";
import type { CollectTaskSnapshot } from "../../types/jobHunt";
import type { CandidateScoreTask } from "../../api/candidateJob";

const { Text } = Typography;

/** 单张卡片的状态（协议值；文案在语言包里）。 */
type CardState = "idle" | "running" | "done" | "failed";

interface Props {
  /** 采集任务快照；还没开始采时为 null。 */
  task: CollectTaskSnapshot | null;
  /** 评分任务快照；没起评分时为 null。 */
  scoreTask: CandidateScoreTask | null;
  collecting: boolean;
  onStartBrowser: () => void;
  startingBrowser: boolean;
}

const STATE_COLOR: Record<CardState, string> = {
  idle: "#d9d9d9",
  running: "#1677ff",
  done: "#52c41a",
  failed: "#ff4d4f",
};

const STATE_BG: Record<CardState, string> = {
  idle: "rgba(0,0,0,0.02)",
  running: "rgba(22,119,255,0.06)",
  done: "rgba(82,196,26,0.06)",
  failed: "rgba(255,77,79,0.06)",
};

interface CardSpec {
  key: string;
  label: string;
  /** 主数字（null 表示这一步还没有数）。 */
  value: string | null;
  /** 主数字下面那句短说明。 */
  caption: string;
  state: CardState;
  /** 该步的内部进度（0-100）；null 表示没有可显示的细进度。 */
  percent: number | null;
}

function buildCards(
  task: CollectTaskSnapshot | null,
  scoreTask: CandidateScoreTask | null,
  collecting: boolean,
): CardSpec[] {
  const failed = task?.status === "failed" || Boolean(task?.error);
  const scoreRunning = Boolean(scoreTask?.running);
  const scoreFailed = scoreTask?.status === "failed";

  // 采集线程**已经跑完了**吗？这是判断前两步是否完成的总闸门。
  //
  // 之前是拿 stage 猜："stage === 'staged' 就是在写入中"——结果当一批全是重复
  // （candidate_ids 为空、没有补 JD 与评分）时，stage 永远停在 "staged"，
  // 卡片永远转蓝圈、总进度卡 25%。用户看到的就是「莫名其妙，到底卡住了没有」。
  //
  // 现在改成看 **task.finished**：采集线程结束了，前两步必然已经结束，
  // 唯一可能还在跑的是评分（另一个任务，看 scoreTask）。
  const collectFinished = Boolean(task?.finished) && !collecting;

  const staged = task?.candidate_count ?? 0;
  const duplicates = task?.duplicates ?? 0;
  const jdDone = task?.jd_done ?? 0;
  const jdTotal = task?.jd_total ?? 0;
  const scoreDone = scoreTask?.completed ?? 0;
  const scoreFailedCount = scoreTask?.failed ?? 0;
  const scoreTotal = scoreTask?.requested ?? 0;

  // ---- 1. 采集 ----
  const collectState: CardState = failed
    ? "failed"
    : collecting || (!collectFinished && (task?.stage === "collected" || !task?.stage))
      ? "running"
      : (task?.collected ?? 0) > 0
        ? "done"
        : "idle";
  const collectPercent =
    collecting && (task?.max_pages ?? 0) > 0
      ? Math.min(100, Math.round(((task?.current_page ?? 0) / (task?.max_pages ?? 1)) * 100))
      : null;

  // ---- 2. 写入待导入 ----
  // 采集线程结束 = 这一步结束。**即使一条都没新建**（全是重复）也是"完成"，
  // 不是"进行中"——这正是不该转蓝圈的那种情况。
  const stageState: CardState = failed
    ? "failed"
    : collectFinished
      ? "done"
      : task?.stage === "collected"
        ? "running"
        : "idle";

  // ---- 3. 补抓 JD ----
  // 采集线程结束后这一步必然是结束态：**有得补是"完成"，没得补也是"完成"**
  // （一分钱都不用花，不该让总进度挂着一个永远不会动的缺口）。
  const jdState: CardState = failed
    ? "failed"
    : collectFinished
      ? "done"
      : task?.stage === "filling_jd"
        ? "running"
        : "idle";
  const jdPercent = jdTotal > 0 ? Math.min(100, Math.round((jdDone / jdTotal) * 100)) : null;

  // ---- 4. AI 评分 ----
  // 同上：采集线程结束且没有可评的候选（全重复）= 这一步已经"走完"，
  // 不是"还没开始"。否则底部会一直显示"待运行"而用户明明什么都没在跑。
  const scoreState: CardState = scoreFailed
    ? "failed"
    : scoreRunning
      ? "running"
      : scoreTotal > 0 && scoreDone + scoreFailedCount >= scoreTotal
        ? "done"
        : collectFinished
          ? "done"
          : "idle";
  const scorePercent =
    scoreTotal > 0
      ? Math.min(100, Math.round(((scoreDone + scoreFailedCount) / scoreTotal) * 100))
      : null;

  return [
    {
      key: "collect",
      label: t("aiJobs.stage.collect"),
      value: task?.collected !== undefined && task.collected > 0 ? String(task.collected) : null,
      caption:
        collecting && task?.max_pages
          ? t("aiJobs.stage.collectPaging", {
              page: task.current_page ?? 0,
              pages: task.max_pages,
            })
          : t("aiJobs.stage.collectUnit"),
      state: collectState,
      percent: collectPercent,
    },
    {
      key: "stage",
      label: t("aiJobs.stage.stage"),
      value: staged > 0 ? String(staged) : null,
      // 全部重复时给一句明确的话：不是"在做"，是"这批都收过了"。
      caption:
        collectFinished && staged === 0 && duplicates > 0
          ? t("aiJobs.stage.allDuplicate", { count: duplicates })
          : duplicates > 0
            ? t("aiJobs.stage.duplicates", { count: duplicates })
            : t("aiJobs.stage.stageUnit"),
      state: stageState,
      percent: null,
    },
    {
      key: "fill_jd",
      label: t("aiJobs.stage.fillJd"),
      value: jdTotal > 0 ? `${jdDone}/${jdTotal}` : null,
      // 没有需要补的（全是重复，或都有正文）说「无需补抓」，而不是留一个空 "—"。
      caption:
        jdTotal > 0
          ? t("aiJobs.stage.fillJdFilled", { count: task?.jd_filled ?? 0 })
          : collectFinished
            ? t("aiJobs.stage.fillJdNotNeeded")
            : t("aiJobs.stage.fillJdUnit"),
      state: jdState,
      percent: jdPercent,
    },
    {
      key: "score",
      label: t("aiJobs.stage.score"),
      value: scoreTotal > 0 ? `${scoreDone + scoreFailedCount}/${scoreTotal}` : null,
      caption:
        scoreFailedCount > 0
          ? t("aiJobs.stage.scoreFailedCount", { count: scoreFailedCount })
          : scoreTotal > 0
            ? t("aiJobs.stage.scoreUnit")
            : collectFinished
              ? t("aiJobs.stage.scoreNotNeeded")
              : t("aiJobs.stage.scoreUnit"),
      state: scoreState,
      percent: scorePercent,
    },
  ];
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

  const failed = task?.status === "failed" || Boolean(task?.error);
  const cards = buildCards(task, scoreTask, collecting);

  // 采集失败且是"浏览器没启动"时直接给补救按钮——这是最常见的失败原因。
  // 判据是后端返回的**协议值前缀** `browser_required`，不是中文文案匹配：
  // 靠文案匹配时后端改一次措辞，这个按钮就静默消失，用户又回到"转一下没反应"。
  const needsBrowser = failed && (task?.error ?? "").startsWith("browser_required");
  // 后端错误可能带协议值前缀（`browser_required: `），展示前剥掉。
  const errorText = (task?.error ?? "").replace(/^[a-z_]+:\s*/, "");

  /**
   * 总进度：四步的平均完成度。
   *
   * 三步口径（之前只按 100/0 摊，会出现"总进度 25% 却标已完成"）：
   * - 已完成 → 100
   * - 未开始（idle）→ **不计入分母**：还没轮到它，把 0 算进去会让进度凭空变慢，
   *   看着像卡住
   * - 在跑 → 用它自己的子进度（没有子进度时按 50 记，表示"正在这一步中间"）
   */
  const overallPercent = (() => {
    const counted = cards.filter((card) => card.state !== "idle");
    if (counted.length === 0) return 0;
    const sum = counted.reduce((total, card) => {
      if (card.state === "done") return total + 100;
      return total + (card.percent ?? 50);
    }, 0);
    return Math.round(sum / counted.length);
  })();

  // 全部完成 = 每张卡都 done。用它决定底部的状态标签，**不用百分比**：
  // 百分比可能因为四舍五入显示 100 而其实还差一步。
  const allDone = cards.every((card) => card.state === "done" || card.state === "failed");

  return (
    <div style={{ marginTop: 12 }}>
      {/* 四张阶段卡片：等宽、横向排开，窄屏自动换行。 */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: 8,
        }}
      >
        {cards.map((card) => (
          <div
            key={card.key}
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              background: STATE_BG[card.state],
              border: `1px solid ${card.state === "idle" ? "rgba(0,0,0,0.06)" : STATE_COLOR[card.state]}`,
              display: "flex",
              flexDirection: "column",
              gap: 4,
            }}
          >
            <Space size={6}>
              {/* 状态点：不转圈、不用动画——颜色+形状单一信号，扫一眼就知道这步什么处境。 */}
              <span
                aria-hidden
                style={{
                  display: "inline-block",
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: STATE_COLOR[card.state],
                }}
              />
              <Text type={card.state === "idle" ? "secondary" : undefined} strong>
                {card.label}
              </Text>
            </Space>

            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span
                style={{
                  fontSize: 24,
                  lineHeight: 1.1,
                  fontWeight: 600,
                  color: card.state === "idle" ? "#bfbfbf" : STATE_COLOR[card.state],
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {card.value ?? "—"}
              </span>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {card.caption}
              </Text>
            </div>

            {card.percent !== null && card.state !== "done" ? (
              <Progress
                percent={card.percent}
                size="small"
                showInfo={false}
                strokeColor={STATE_COLOR[card.state]}
                style={{ margin: 0 }}
              />
            ) : null}
          </div>
        ))}
      </div>

      {/* 总进度：四步的平均完成度。回答"还要等多久"。 */}
      <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}>
        <Text type="secondary" style={{ whiteSpace: "nowrap", fontSize: 12 }}>
          {t("aiJobs.stage.overall")}
        </Text>
        <Progress
          percent={overallPercent}
          size="small"
          status={failed ? "exception" : overallPercent === 100 ? "success" : "active"}
          style={{ margin: 0, flex: 1 }}
        />
      </div>

      <Space wrap style={{ marginTop: 10 }} size={8}>
        <Tag
          color={
            failed
              ? "error"
              : collecting || scoreTask?.running
                ? "processing"
                : allDone
                  ? "success"
                  : "default"
          }
        >
          {failed
            ? t("aiJobs.progress.badge.failed")
            : collecting
              ? t("aiJobs.progress.badge.collecting")
              : scoreTask?.running
                ? t("aiJobs.progress.badge.scoring")
                : allDone
                  ? t("aiJobs.progress.badge.done")
                  : t("aiJobs.progress.badge.idle")}
        </Tag>
        <Text type="secondary">{scoreTask?.running ? scoreTask?.message : task?.message}</Text>
        {task?.blocked ? (
          <Text type="secondary">{t("aiJobs.native.blockedCount", { count: task.blocked })}</Text>
        ) : null}
      </Space>

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
