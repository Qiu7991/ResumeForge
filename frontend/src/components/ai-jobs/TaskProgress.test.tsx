// SPDX-License-Identifier: Apache-2.0
/** TaskProgress：状态标签、终态禁停止、日志展开、停止交互。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TaskProgress from "./TaskProgress";
import type { AiWorkbenchTask } from "../../types/aiJobs";

const apiMocks = vi.hoisted(() => ({ stopAiTask: vi.fn() }));
vi.mock("../../api/aiJobs", () => apiMocks);

function taskFixture(overrides: Partial<AiWorkbenchTask> = {}): AiWorkbenchTask {
  return {
    id: "task-1",
    mode: "full",
    label: "全流程",
    status: "running",
    logs: ["fake: step 1", "fake: step 2"],
    error: null,
    created_at: "2026-11-03T01:00:00",
    updated_at: "2026-11-03T01:00:00",
    deadline_at: null,
    stop_reason: null,
    metrics: {},
    progress: {},
    ...overrides,
  };
}

function renderTask(task: AiWorkbenchTask) {
  render(
    <AntdApp>
      <TaskProgress task={task} onStopped={vi.fn()} />
    </AntdApp>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TaskProgress", () => {
  it("shows status tag and mode label", () => {
    renderTask(taskFixture());
    expect(screen.getByText("运行中")).toBeTruthy();
    expect(screen.getByText("全流程")).toBeTruthy();
  });

  it("disables stop for terminal tasks", () => {
    renderTask(taskFixture({ status: "completed" }));
    expect(screen.getByRole("button", { name: /停止任务/ }).hasAttribute("disabled")).toBe(true);
  });

  it("expands logs and shows error", () => {
    renderTask(taskFixture({ error: "BOSS 登录已失效" }));
    fireEvent.click(screen.getByText("运行日志"));
    expect(screen.getByText("fake: step 2")).toBeTruthy();
    expect(screen.getByText("BOSS 登录已失效")).toBeTruthy();
  });

  it("stops the task and reports success", async () => {
    apiMocks.stopAiTask.mockResolvedValue({ ok: true });
    const onStopped = vi.fn();
    render(
      <AntdApp>
        <TaskProgress task={taskFixture()} onStopped={onStopped} />
      </AntdApp>,
    );
    fireEvent.click(screen.getByRole("button", { name: /停止任务/ }));
    await waitFor(() => expect(apiMocks.stopAiTask).toHaveBeenCalledWith("task-1"));
    await waitFor(() => expect(onStopped).toHaveBeenCalledOnce());
  });
});
