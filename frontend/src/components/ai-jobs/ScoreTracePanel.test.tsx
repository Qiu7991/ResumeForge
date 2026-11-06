// SPDX-License-Identifier: Apache-2.0
/** ScoreTracePanel：五维渲染、封顶/硬缺口、legacy 缺失状态。 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import ScoreTracePanel from "./ScoreTracePanel";
import type { ScoreTrace } from "../../types/aiJobs";

afterEach(() => cleanup());

const full: ScoreTrace = {
  engine_job_id: "job-1",
  score: 82,
  dimensions: {
    core_duties: { evidence: "三年 Python 后端经验", score: 18 },
    hard_requirements: { evidence: "本科及以上满足", score: 15 },
  },
  caps: ["薪资低于期望"],
  hard_gaps: ["缺少域驱动设计经验"],
  reason: "整体匹配，薪资偏弱",
};

describe("ScoreTracePanel", () => {
  it("renders dimensions with evidence and score", () => {
    render(<ScoreTracePanel trace={full} />);
    expect(screen.getByText("核心职责")).toBeTruthy();
    expect(screen.getByText("三年 Python 后端经验")).toBeTruthy();
    expect(screen.getByText("整体匹配，薪资偏弱")).toBeTruthy();
  });

  it("renders caps and hard gaps as tags", () => {
    render(<ScoreTracePanel trace={full} />);
    expect(screen.getByText("薪资低于期望")).toBeTruthy();
    expect(screen.getByText("缺少域驱动设计经验")).toBeTruthy();
  });

  it("shows missing state for legacy jobs without trace", () => {
    render(<ScoreTracePanel trace={null} />);
    expect(screen.getByText("该岗位没有评分详情")).toBeTruthy();
    render(<ScoreTracePanel trace={{ score: 70 }} />);
    expect(screen.getAllByText("该岗位没有评分详情").length).toBeGreaterThan(0);
  });
});
