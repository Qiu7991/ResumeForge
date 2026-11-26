// SPDX-License-Identifier: Apache-2.0
/**
 * 「已导入」暂存记录：孤立标记与批量清理。
 *
 * 守住三条：切到已导入视图时按 `status: "imported"` 拉取、孤立/在库两种状态各自标对、
 * 清理按钮只把孤立或勾选的候选 id 交给批量软删接口（不碰正式岗位）。
 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CandidateJob } from "../../types";
import { t } from "../../i18n";
import CollectResultPanel from "./CollectResultPanel";

const apiMocks = vi.hoisted(() => ({
  listCandidateJobs: vi.fn(),
  importCandidateJobs: vi.fn(),
  bulkDeleteCandidateJobs: vi.fn(),
}));

vi.mock("../../api/candidateJob", () => ({
  listCandidateJobs: apiMocks.listCandidateJobs,
  importCandidateJobs: apiMocks.importCandidateJobs,
  bulkDeleteCandidateJobs: apiMocks.bulkDeleteCandidateJobs,
}));

const ORPHAN_TITLE = "孤立岗位";
const LIVE_TITLE = "在库岗位";
const SELECTED_TITLE = "选中岗位";

function candidate(overrides: Partial<CandidateJob> = {}): CandidateJob {
  return {
    id: 1,
    title: ORPHAN_TITLE,
    company: "示例公司",
    location: "天津",
    salary: "20-30K",
    raw_text: "",
    images: [],
    note: "",
    source: "示例站点",
    source_url: "https://example.com/job/1",
    collect_task_id: 7,
    status: "imported",
    imported_job_id: 11,
    imported_job_missing: false,
    created_at: "2026-09-18T10:00:00",
    updated_at: "2026-09-18T10:00:00",
    ...overrides,
  };
}

/** 待导入视图返回空、已导入视图返回给定记录（两个视图共用同一个列表接口）。 */
function mockLists(imported: CandidateJob[]) {
  apiMocks.listCandidateJobs.mockImplementation((params: { status?: string } = {}) =>
    Promise.resolve(params.status === "imported" ? imported : []),
  );
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <AntdApp>
        <CollectResultPanel taskId={7} />
      </AntdApp>
    </MemoryRouter>,
  );
}

async function openImportedView() {
  await screen.findByRole("radio", { name: t("collectResult.view.pending") });
  fireEvent.click(screen.getByRole("radio", { name: t("collectResult.view.imported") }));
}

beforeEach(() => {
  apiMocks.listCandidateJobs.mockReset();
  apiMocks.importCandidateJobs.mockReset();
  apiMocks.bulkDeleteCandidateJobs.mockReset();
});

afterEach(cleanup);

describe("CollectImportedPanel", () => {
  it("切到已导入视图后按 imported 拉取，并标出两种岗位状态", async () => {
    mockLists([
      candidate({ id: 1, title: ORPHAN_TITLE, imported_job_missing: true }),
      candidate({
        id: 2,
        title: LIVE_TITLE,
        imported_job_missing: false,
        source_url: "https://example.com/job/2",
      }),
    ]);
    renderPanel();
    await openImportedView();

    expect(await screen.findByText(ORPHAN_TITLE)).toBeInTheDocument();
    expect(screen.getByText(LIVE_TITLE)).toBeInTheDocument();
    expect(screen.getByText(t("collectResult.imported.status.orphaned"))).toBeInTheDocument();
    expect(screen.getByText(t("collectResult.imported.status.live"))).toBeInTheDocument();
    expect(apiMocks.listCandidateJobs).toHaveBeenCalledWith({
      status: "imported",
      sort: "created_desc",
    });
  });

  it("清理孤立记录时只批量软删孤立 id 并刷新列表", async () => {
    mockLists([candidate({ id: 7, imported_job_missing: true })]);
    apiMocks.bulkDeleteCandidateJobs.mockResolvedValue({ deleted: 1, missing: 0 });
    renderPanel();
    await openImportedView();

    fireEvent.click(
      await screen.findByRole("button", {
        name: t("collectResult.imported.cleanOrphaned", { count: 1 }),
      }),
    );

    await waitFor(() => expect(apiMocks.bulkDeleteCandidateJobs).toHaveBeenCalledWith([7]));
    // 软删成功后必须重新拉取，否则那条孤立的记录还留在表里。
    // 1 = 挂载时的待导入列表，2 = 切到已导入视图，3 = 清理后的刷新。
    await waitFor(() => expect(apiMocks.listCandidateJobs).toHaveBeenCalledTimes(3));
  });

  it("勾选记录后按选中 id 移出暂存区", async () => {
    mockLists([
      candidate({ id: 7, title: SELECTED_TITLE }),
      candidate({ id: 8, title: LIVE_TITLE, source_url: "https://example.com/job/8" }),
    ]);
    apiMocks.bulkDeleteCandidateJobs.mockResolvedValue({ deleted: 1, missing: 0 });
    renderPanel();
    await openImportedView();
    await screen.findByText(SELECTED_TITLE);

    // 第 0 个是表头的全选框，第一行的勾选框从下标 1 开始。
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(
      screen.getByRole("button", {
        name: t("collectResult.imported.deleteSelectedWithCount", { count: 1 }),
      }),
    );

    await waitFor(() => expect(apiMocks.bulkDeleteCandidateJobs).toHaveBeenCalledWith([7]));
  });
});
