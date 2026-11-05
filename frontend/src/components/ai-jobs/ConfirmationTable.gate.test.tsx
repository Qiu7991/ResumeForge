// SPDX-License-Identifier: Apache-2.0
/**
 * B6 发送闸门的前端体现：后端环境闸 AI_JOBS_ALLOW_SEND 关闭（探测 403）时，
 * 「确认投递」入口按钮必须不可点；探测失败按 fail-closed 处理并给出重新检查。
 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConfirmationTable from "./ConfirmationTable";
import type { EngineJobSummary, SendQuota } from "../../types/aiJobs";

const apiMocks = vi.hoisted(() => ({
  deliverAiJobs: vi.fn(),
  rejectAiJobs: vi.fn(),
  probeSendGate: vi.fn(),
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
];

function renderTable() {
  render(
    <AntdApp>
      <ConfirmationTable jobs={jobs} quota={quota} onChanged={vi.fn()} />
    </AntdApp>,
  );
}

function sendEntryButton() {
  // 「确认投递」是打开确认弹窗的入口按钮（弹窗内的主按钮文案是「确认发送」）。
  return screen.getByRole("button", { name: /确认投递/ });
}

async function selectFirstRow() {
  fireEvent.click(screen.getAllByRole("checkbox")[1]);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ConfirmationTable 发送闸门（B6）", () => {
  it("闸门关闭（探测 403）时：入口按钮禁用，即使已勾选岗位也无法打开确认弹窗", async () => {
    apiMocks.probeSendGate.mockResolvedValue("closed");
    renderTable();
    // 等探测落地（按钮从「检查中」进入「已关闭」态）
    await waitFor(() => expect(screen.getByText(/AI_JOBS_ALLOW_SEND=0/)).toBeTruthy());
    await selectFirstRow();
    expect(sendEntryButton().hasAttribute("disabled")).toBe(true);
    // 明确提示
    expect(screen.getByText(/投递通道不可用/)).toBeTruthy();
    // 兜底证明：直接点击也不会打开弹窗（禁用按钮点击无效）
    fireEvent.click(sendEntryButton());
    expect(screen.queryByText(/我已核对所选岗位/)).toBeNull();
    expect(apiMocks.deliverAiJobs).not.toHaveBeenCalled();
  });

  it("闸门打开（探测 400）时：勾选后入口按钮可用，正常进入二次确认", async () => {
    apiMocks.probeSendGate.mockResolvedValue("open");
    renderTable();
    // 无勾选时仍禁用（原有约束保持）
    await waitFor(() => expect(sendEntryButton()).toBeTruthy());
    expect(sendEntryButton().hasAttribute("disabled")).toBe(true);
    await selectFirstRow();
    // 探测落地（open）后仅受「是否勾选」约束 → 可用
    await waitFor(() => {
      expect(sendEntryButton().hasAttribute("disabled")).toBe(false);
    });
    fireEvent.click(sendEntryButton());
    expect(screen.getByText(/我已核对所选岗位/)).toBeTruthy();
  });

  it("探测失败按 fail-closed：按钮禁用 + 提示停用 + 可重新检查恢复", async () => {
    apiMocks.probeSendGate.mockRejectedValue(new Error("网络抖动"));
    renderTable();
    await waitFor(() => expect(screen.getByText(/发送已停用/)).toBeTruthy());
    await selectFirstRow();
    expect(sendEntryButton().hasAttribute("disabled")).toBe(true);
    // 重新检查转「开」后恢复可用（勾选保留）
    apiMocks.probeSendGate.mockResolvedValue("open");
    fireEvent.click(screen.getByRole("button", { name: /重新检查/ }));
    await waitFor(() => {
      expect(sendEntryButton().hasAttribute("disabled")).toBe(false);
    });
    expect(screen.queryByText(/发送已停用/)).toBeNull();
  });
});
