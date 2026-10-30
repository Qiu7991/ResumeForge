import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AiTaskSnapshot } from "../types/aiTask";
import {
  getAiTasks,
  resetAiTasks,
  startAiTask,
  tickAiTasks,
} from "./aiTaskWatcher";

const api = vi.hoisted(() => ({
  createAiTask: vi.fn(),
  getAiTask: vi.fn(),
  listActiveAiTasks: vi.fn(),
  cancelAiTask: vi.fn(),
}));
const notify = vi.hoisted(() => ({ notifyTaskDone: vi.fn() }));

vi.mock("../api/aiTasks", () => api);
vi.mock("./taskNotify", () => notify);

function snapshot(overrides: Partial<AiTaskSnapshot> = {}): AiTaskSnapshot {
  return {
    id: 1,
    kind: "job_match",
    status: "running",
    progress: 30,
    label: "岗位匹配度分析",
    message: "正在分析",
    result_ref: null,
    error: "",
    created_at: "2026-10-31T10:00:00",
    started_at: "2026-10-31T10:00:00",
    finished_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  resetAiTasks();
  api.createAiTask.mockResolvedValue(snapshot());
  // 建任务时会立刻拉一次：默认返回"运行中"，避免未设桩的首轮更新落到下一条用例。
  api.getAiTask.mockResolvedValue(snapshot());
});

afterEach(() => {
  resetAiTasks();
});

describe("aiTaskWatcher", () => {
  it("登记任务 → 轮询到成功 → 通知并回调，列表清空", async () => {
    const onFinished = vi.fn();
    await startAiTask({
      kind: "job_match",
      payload: { job_id: 7 },
      label: "岗位匹配度分析",
      onFinished,
    });
    await Promise.resolve();
    expect(getAiTasks()).toHaveLength(1);

    api.getAiTask.mockResolvedValue(snapshot({ status: "succeeded", progress: 100 }));
    await tickAiTasks();

    expect(onFinished).toHaveBeenCalledWith(
      expect.objectContaining({ id: 1, status: "succeeded" }),
    );
    expect(notify.notifyTaskDone).toHaveBeenCalledWith(
      expect.objectContaining({ title: "岗位匹配度分析完成" }),
    );
    expect(getAiTasks()).toHaveLength(0);
  });

  it("失败时回调带错误原因，通知 kind=error", async () => {
    const onFinished = vi.fn();
    await startAiTask({ kind: "job_match", payload: {}, label: "匹配分析", onFinished });
    await Promise.resolve();

    api.getAiTask.mockResolvedValue(
      snapshot({ status: "failed", error: "岗位不存在或已被删除" }),
    );
    await tickAiTasks();

    expect(onFinished).toHaveBeenCalledWith(
      expect.objectContaining({ status: "failed", error: "岗位不存在或已被删除" }),
    );
    expect(notify.notifyTaskDone).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error", description: "岗位不存在或已被删除" }),
    );
  });

  it("404 时移除条目，不触发完成/失败通知", async () => {
    const { ApiError } = await import("../api/client");
    await startAiTask({ kind: "job_match", payload: {}, label: "匹配分析" });
    await Promise.resolve();

    api.getAiTask.mockRejectedValue(new ApiError("AI 任务不存在", 404, { code: "http" }));
    await tickAiTasks();

    expect(getAiTasks()).toHaveLength(0);
    expect(notify.notifyTaskDone).not.toHaveBeenCalled();
  });
});
