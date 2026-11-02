// SPDX-License-Identifier: Apache-2.0
/** 批量生成招呼语：拿到默认招呼语时绝不能当成成功落库（否则又变成群发默认话术）。 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplyQueueItem } from "../../types";

const mocks = vi.hoisted(() => ({
  previewGreeting: vi.fn(),
  updateQueueItem: vi.fn(),
  notifyTaskDone: vi.fn(),
}));

vi.mock("../../api/apply", () => ({
  previewGreeting: mocks.previewGreeting,
  updateQueueItem: mocks.updateQueueItem,
}));
vi.mock("../../utils/taskNotify", () => ({ notifyTaskDone: mocks.notifyTaskDone }));

import { getGreetingBatchState, startGreetingBatch } from "./greetingBatchRunner";

const ITEM: ApplyQueueItem = {
  id: 7,
  job_id: 42,
  job_title: "大模型应用实习生",
  company: "A公司",
  resume_id: null,
  resume_title: "",
  greeting: "",
  sort_order: 0,
  status: "pending",
  admission: null,
  hard_gate: null,
  requires_confirm: false,
  created_at: "2026-11-02T08:00:00",
  updated_at: "2026-11-02T08:00:00",
};

async function waitIdle(): Promise<void> {
  for (let i = 0; i < 200 && getGreetingBatchState().running; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

beforeEach(() => {
  mocks.previewGreeting.mockReset();
  mocks.updateQueueItem.mockReset();
  mocks.notifyTaskDone.mockReset();
});

describe("greetingBatchRunner", () => {
  it("后端回退默认招呼语时记为失败，不落库", async () => {
    mocks.previewGreeting.mockResolvedValue({ greeting: "您好，我对该岗位很感兴趣", source: "default" });

    startGreetingBatch([ITEM]);
    await waitIdle();

    expect(mocks.updateQueueItem).not.toHaveBeenCalled();
    expect(getGreetingBatchState().failed).toBe(1);
    expect(mocks.notifyTaskDone).toHaveBeenCalled();
  });

  it("生成成功时以未确认状态落库", async () => {
    mocks.previewGreeting.mockResolvedValue({
      greeting: "计算机本科，做过 LLM 结构化抽取",
      source: "generated",
    });
    mocks.updateQueueItem.mockResolvedValue({ ...ITEM, greeting: "计算机本科，做过 LLM 结构化抽取" });

    startGreetingBatch([ITEM]);
    await waitIdle();

    expect(mocks.updateQueueItem).toHaveBeenCalledWith(ITEM.id, {
      greeting: "计算机本科，做过 LLM 结构化抽取",
      confirm_greeting: false,
    });
    expect(getGreetingBatchState().failed).toBe(0);
  });
});
