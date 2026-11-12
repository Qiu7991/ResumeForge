// SPDX-License-Identifier: Apache-2.0
/**
 * 阶段卡片的状态判定。
 *
 * 用户实测反馈「我都看不懂，这到底是卡住了还是什么」——根因不是样式，是**状态算错**：
 * 一批全是重复（没有新候选、没有补 JD、没有评分）时，采集线程早就结束了，但卡片
 * 把 stage 停在 "staged" 判成"写入中"，于是永远转蓝圈、总进度卡在 25%。
 *
 * 所以这里守的是一条硬性质：**采集任务结束（finished）之后，前三个卡片不能还是"在跑"。**
 */
import { cleanup, render, screen } from "@testing-library/react";
import { App as AntdApp } from "antd";
import { afterEach, describe, expect, it } from "vitest";

import CollectProgressPanel from "./CollectProgressPanel";
import { t } from "../../i18n";
import type { CollectTaskSnapshot } from "../../types/jobHunt";

function task(overrides: Partial<CollectTaskSnapshot> = {}): CollectTaskSnapshot {
  return {
    task_id: "t1",
    site_key: "boss",
    keywords: "AI",
    city: "广州",
    max_pages: 2,
    status: "completed",
    current_page: 2,
    collected: 12,
    message: "",
    error: "",
    blocked: 0,
    stopped_reason: "",
    stub_count: 12,
    finished: true,
    stage: "staged",
    candidate_count: 0,
    duplicates: 12,
    jd_done: 0,
    jd_total: 0,
    jd_filled: 0,
    score_started: false,
    ...overrides,
  };
}

function renderPanel(props: Partial<React.ComponentProps<typeof CollectProgressPanel>> = {}) {
  return render(
    <AntdApp>
      <CollectProgressPanel
        task={null}
        scoreTask={null}
        collecting={false}
        onStartBrowser={() => undefined}
        startingBrowser={false}
        {...props}
      />
    </AntdApp>,
  );
}

afterEach(cleanup);

describe("CollectProgressPanel 状态判定", () => {
  it("一批全是重复时：显示「都已收过」，不是「进行中」", () => {
    // 这是用户实际遇到的那种：采 12 条全重复 → 没有新候选 → 没有补 JD/评分。
    // 采集线程结束了，界面就不能还转着蓝圈。
    renderPanel({ task: task() });

    // 结论句明确说明"都收过了"。
    expect(screen.getByText(t("aiJobs.stage.allDuplicate", { count: 12 }))).toBeInTheDocument();
    // 补 JD / 评分两卡说"无需"，而不是留一个空 — 。
    expect(screen.getByText(t("aiJobs.stage.fillJdNotNeeded"))).toBeInTheDocument();
    expect(screen.getByText(t("aiJobs.stage.scoreNotNeeded"))).toBeInTheDocument();
    // 状态标签是「已完成」（不是「采集中」）。
    expect(screen.getByText(t("aiJobs.progress.badge.done"))).toBeInTheDocument();
    expect(screen.queryByText(t("aiJobs.progress.badge.collecting"))).not.toBeInTheDocument();
  });

  it("全部完成时总进度必须是 100%，不能是 25%", () => {
    // 旧算法把没有子进度的阶段当 0% 摊平均，于是四步里只有采集 100 → 显示 25%
    // 却同时标「已完成」——自相矛盾，用户当然看不懂。
    const { container } = renderPanel({
      task: task({ candidate_count: 3, duplicates: 9, jd_done: 3, jd_total: 3, jd_filled: 3 }),
      scoreTask: { running: false, status: "completed", requested: 3, completed: 3, failed: 0 },
    });

    // antd 的 Progress 百分比是画出来的（aria-valuenow / 样式宽度），不是 DOM 文本。
    // 断言可访问属性才是稳的——按文本找 "100%" 会永远失败。
    const bars = container.querySelectorAll('[role="progressbar"]');
    expect(bars.length).toBeGreaterThan(0);
    const overall = bars[bars.length - 1] as HTMLElement;
    expect(overall.getAttribute("aria-valuenow")).toBe("100");
  });

  it("采集还在跑时：采集卡在跑，后面的卡是待运行", () => {
    renderPanel({
      task: task({
        status: "running",
        finished: false,
        stage: "",
        collected: 5,
        candidate_count: 0,
        duplicates: 0,
        current_page: 1,
      }),
      collecting: true,
    });

    expect(screen.getByText(t("aiJobs.progress.badge.collecting"))).toBeInTheDocument();
    // 还没轮到补 JD / 评分：不该显示「无需补抓」这种终点才有的文案。
    expect(screen.queryByText(t("aiJobs.stage.fillJdNotNeeded"))).not.toBeInTheDocument();
  });

  it("采集已结束但评分还在跑：不能显示「已完成」", () => {
    // 这是用户截图里那个：采集卡绿了、进度条 100%、标签「已完成」，
    // 但补 JD 显示 0/1、评分还没开始。矛盾的信息让人以为卡住了。
    //
    // 根因是后端在采集刚结束就设了 completed（补 JD/评分之前），而前端拿 finished
    // 当"全部完成"。现在两者分开：finished = 采集线程结束，评分看 scoreTask。
    renderPanel({
      task: task({ candidate_count: 1, duplicates: 17, jd_done: 1, jd_total: 1, jd_filled: 0 }),
      scoreTask: { running: true, status: "running", requested: 1, completed: 0, failed: 0 },
    });

    expect(screen.getByText(t("aiJobs.progress.badge.scoring"))).toBeInTheDocument();
    expect(screen.queryByText(t("aiJobs.progress.badge.done"))).not.toBeInTheDocument();
  });

  it("采集失败时状态标签是失败", () => {
    renderPanel({
      task: task({ status: "failed", finished: true, error: "browser_required: 请先启动浏览器" }),
    });

    expect(screen.getByText(t("aiJobs.progress.badge.failed"))).toBeInTheDocument();
    // 错误文案展示前剥掉协议值前缀。
    expect(screen.queryByText(/browser_required/)).not.toBeInTheDocument();
  });
});
