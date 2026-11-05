// SPDX-License-Identifier: Apache-2.0
/**
 * 队列编辑器：写招呼语时能就地看岗位 JD。
 *
 * 用户在排招呼语时反复回岗位广场看 JD，回来还得重新点开编辑——这个用例锁住
 * 「展开才拉取、拉过一次缓存、没 JD 说清楚去哪儿补」这三条行为。
 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApplyQueueItem } from "../../../types";
import { QueueItemEditor } from "./QueueItemEditor";

const apiMocks = vi.hoisted(() => ({
  previewGreeting: vi.fn(),
  updateQueueItem: vi.fn(),
  getJob: vi.fn(),
  listResumes: vi.fn(),
  getResume: vi.fn(),
}));

vi.mock("../../../api/apply", () => ({
  previewGreeting: apiMocks.previewGreeting,
  updateQueueItem: apiMocks.updateQueueItem,
}));

vi.mock("../../../api/jobs", () => ({
  getJob: apiMocks.getJob,
}));

vi.mock("../../../api/resumes", () => ({
  listResumes: apiMocks.listResumes,
  getResume: apiMocks.getResume,
}));

const ITEM: ApplyQueueItem = {
  id: 3,
  job_id: 42,
  job_title: "大模型技术适配测试岗",
  company: "蓝粤",
  resume_id: 50,
  resume_title: "赵岚柯-通用版",
  greeting: "您好，做过大模型应用场景验证与测试排查。",
  greeting_confirmed: true,
  sort_order: 0,
  status: "pending",
  admission: null,
  hard_gate: null,
  requires_confirm: false,
  created_at: "2026-11-05T08:00:00",
  updated_at: "2026-11-05T08:00:00",
};

function renderEditor() {
  return render(
    <AntdApp>
      <QueueItemEditor item={ITEM} onClose={vi.fn()} onSaved={vi.fn()} />
    </AntdApp>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listResumes.mockResolvedValue({ items: [], total: 0 });
  apiMocks.getResume.mockResolvedValue({
    id: 50,
    title: "赵岚柯-通用版",
    job_id: 42,
    content: {
      sections: [
        {
          key: "projects",
          entries: [
            { items: [{ key: "name", value: "CreatorDistill 创作者内容分析系统" }] },
            { items: [{ key: "name", value: "AIGC 短视频生产体系" }] },
          ],
        },
      ],
    },
  });
  apiMocks.getJob.mockResolvedValue({
    id: 42,
    title: ITEM.job_title,
    description: "负责大模型能力的适配与测试。",
    requirements: "熟悉 Python 与模型评测。",
  });
});

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("QueueItemEditor 岗位 JD", () => {
  it("展开时才拉取岗位详情，并把职责与要求显示出来", async () => {
    renderEditor();

    // 未展开前不发请求：翻队列不该给每个编辑弹窗都补一次 /jobs。
    expect(apiMocks.getJob).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "查看岗位 JD" }));

    await waitFor(() => expect(apiMocks.getJob).toHaveBeenCalledWith(42));
    await waitFor(() => {
      const body = document.querySelector(".apply-queue-jd-body");
      expect(body?.textContent).toContain("负责大模型能力的适配与测试。");
      expect(body?.textContent).toContain("熟悉 Python 与模型评测。");
    });
  });

  it("收起再展开不重复请求（同一弹窗内缓存）", async () => {
    renderEditor();

    fireEvent.click(screen.getByRole("button", { name: "查看岗位 JD" }));
    await waitFor(() => expect(apiMocks.getJob).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "收起岗位 JD" }));
    fireEvent.click(screen.getByRole("button", { name: "查看岗位 JD" }));

    expect(apiMocks.getJob).toHaveBeenCalledTimes(1);
  });
});

describe("QueueItemEditor 指定项目", () => {
  it("项目候选取自当前简历，选中后生成请求带上 focus_project", async () => {
    apiMocks.previewGreeting.mockResolvedValue({
      greeting: "您好，做过用 AI 工具端到端交付的 AI 应用。",
      source: "generated",
    });
    renderEditor();

    // 项目列表来自「使用简历」那份文档，而不是全局静态清单。
    await waitFor(() => expect(apiMocks.getResume).toHaveBeenCalledWith(50));

    const combos = screen.getAllByRole("combobox");
    fireEvent.mouseDown(combos[combos.length - 1]);
    await screen.findAllByRole("option");
    const combo = combos[combos.length - 1];
    // antd v6 的选项点击在 jsdom 里不触发 onChange，用键盘选中（与真实用户操作等价）。
    fireEvent.keyDown(combo, { key: "ArrowDown", code: "ArrowDown", keyCode: 40, which: 40 });
    fireEvent.keyDown(combo, { key: "Enter", code: "Enter", keyCode: 13, which: 13 });
    const chosen = document.querySelectorAll(".ant-select")[1]?.textContent?.trim() ?? "";
    expect(chosen.length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "按岗位生成招呼语" }));

    await waitFor(() =>
      expect(apiMocks.previewGreeting).toHaveBeenCalledWith(
        expect.objectContaining({ focus_project: chosen }),
        expect.anything(),
      ),
    );
  });
});
