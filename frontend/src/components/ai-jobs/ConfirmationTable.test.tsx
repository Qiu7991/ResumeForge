// SPDX-License-Identifier: Apache-2.0
/** ConfirmationTable：选择、白名单外提示由后端给；这里钉住确认弹窗三要素与拒绝。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConfirmationTable from "./ConfirmationTable";
import type { EngineJobSummary, SendQuota } from "../../types/aiJobs";

const apiMocks = vi.hoisted(() => ({
  deliverAiJobs: vi.fn(),
  rejectAiJobs: vi.fn(),
}));
vi.mock("../../api/aiJobs", () => apiMocks);

const quota: SendQuota = { daily_limit: 30, sent: 2, remaining: 28, exhausted: false };

const jobs: EngineJobSummary[] = [
  {
    id: "job-1",
    title: "AI 应用工程师",
    company: "示例公司",
    status: "ready",
    score: 82,
    greeting: "您好，看到贵司在招 AI 应用工程师",
    source_platform: "boss",
    platform_label: "BOSS直聘",
  },
  {
    id: "job-2",
    title: "算法实习生",
    company: "另一家",
    status: "ready",
    score: 75,
    greeting: null,
    source_platform: "zhilian",
    platform_label: "智联招聘",
    platform_read_only: true,
  },
];

function renderTable() {
  render(
    <AntdApp>
      <ConfirmationTable jobs={jobs} quota={quota} onChanged={vi.fn()} />
    </AntdApp>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ConfirmationTable", () => {
  it("renders jobs with platform and greeting state", () => {
    renderTable();
    expect(screen.getByText("示例公司")).toBeTruthy();
    expect(screen.getByText("BOSS直聘")).toBeTruthy();
    expect(screen.getByText("智联招聘")).toBeTruthy();
    expect(screen.getAllByText("招呼语未确认").length).toBeGreaterThan(0);
  });

  it("confirm modal requires checkbox and shows quota + warning", async () => {
    renderTable();
    // 勾选第一行（索引 0 是表头全选框）
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByRole("button", { name: /确认投递/ }));
    expect(screen.getByText("已选 1 个岗位")).toBeTruthy();
    expect(screen.getByText(/今日已发 2\/30/)).toBeTruthy();
    expect(screen.getByText(/不可撤回/)).toBeTruthy();
    // 未勾选承诺前不可发送
    const confirmButton = screen.getByRole("button", { name: /确认发送/ });
    expect(confirmButton.hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByText("我已核对所选岗位的招呼语与目标公司"));
    expect(screen.getByRole("button", { name: /确认发送/ }).hasAttribute("disabled")).toBe(false);
  });

  it("delivers selected jobs and calls onChanged", async () => {
    apiMocks.deliverAiJobs.mockResolvedValue({ result: {}, tracker_synced: 0 });
    const onChanged = vi.fn();
    render(
      <AntdApp>
        <ConfirmationTable jobs={jobs} quota={quota} onChanged={onChanged} />
      </AntdApp>,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByRole("button", { name: /确认投递/ }));
    fireEvent.click(screen.getByText("我已核对所选岗位的招呼语与目标公司"));
    fireEvent.click(screen.getByRole("button", { name: /确认发送/ }));
    await waitFor(() => expect(apiMocks.deliverAiJobs).toHaveBeenCalledWith(["job-1"]));
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });

  it("rejects selected jobs", async () => {
    apiMocks.rejectAiJobs.mockResolvedValue({ result: {} });
    renderTable();
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByRole("button", { name: /拒绝所选/ }));
    await waitFor(() => expect(apiMocks.rejectAiJobs).toHaveBeenCalledWith(["job-1"]));
  });
});
