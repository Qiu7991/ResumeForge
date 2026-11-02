// SPDX-License-Identifier: Apache-2.0
/** 批量工具条：删除不能只藏在下拉里，可见按钮要能触发并给出回收站说明。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GreetingBatchState } from "../../features/apply/greetingBatchRunner";
import type { BulkAiState } from "../../features/jobs/jobBulkAiRunner";
import { BatchToolbar } from "./BatchToolbar";

const IDLE_AI: BulkAiState = {
  running: false,
  kind: null,
  total: 0,
  done: 0,
  failed: 0,
  currentTitle: "",
  stopRequested: false,
};

const IDLE_GREETING: GreetingBatchState = {
  running: false,
  total: 0,
  done: 0,
  failed: 0,
  currentTitle: "",
  stopRequested: false,
};

function renderBar(onBulkAction = vi.fn()) {
  render(
    <AntdApp>
      <BatchToolbar
        selectionMode
        selectedJobIds={[1, 2]}
        setSelectedJobIds={vi.fn()}
        batchAction={null}
        batchStatus={undefined}
        setBatchStatus={vi.fn()}
        applyBatchStatus={vi.fn()}
        onBulkAction={onBulkAction}
        bulkAi={IDLE_AI}
        onStopBulkAi={vi.fn()}
        greetingBatch={IDLE_GREETING}
        onStopGreetings={vi.fn()}
        exitSelectionMode={vi.fn()}
      />
    </AntdApp>,
  );
  return onBulkAction;
}

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("BatchToolbar 批量删除", () => {
  it("有选中时显示可见的删除按钮，确认后交回 delete 动作", async () => {
    const onBulkAction = renderBar();

    const button = await screen.findByRole("button", { name: /批量删除/ });
    expect(button).toBeEnabled();

    fireEvent.click(button);
    const popconfirm = await waitFor(() => {
      const node = document.querySelector<HTMLElement>(".ant-popconfirm");
      expect(node).not.toBeNull();
      return node!;
    });
    expect(within(popconfirm).getAllByText(/回收站/).length).toBeGreaterThan(0);

    fireEvent.click(popconfirm.querySelector<HTMLButtonElement>(".ant-btn-primary")!);
    expect(onBulkAction).toHaveBeenCalledWith("delete");
  });
});
