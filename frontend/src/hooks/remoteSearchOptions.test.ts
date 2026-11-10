// SPDX-License-Identifier: Apache-2.0
/**
 * 投递队列的简历下拉：候选 = 本岗位的简历 + 收藏的简历，本岗位排最前、重复只留一次。
 *
 * 为什么单独钉这一条（2026-11-09）：用户实测 2.0 的下拉里只有「本岗位」那一份，
 * 而 1.x 会把收藏的简历都列出来——移植时只留了 `job_id` 那一路查询，收藏的一半丢了。
 * 这个用例守的就是"两路并集"，任何一路被删掉都会立刻红。
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { listResumes } from "../api/resumes";
import type { ResumeBrief } from "../types";
import { useResumeSearchSelectForJob } from "./remoteSearchOptions";

vi.mock("../api/resumes", () => ({
  listResumes: vi.fn(),
  getResume: vi.fn(),
}));

function brief(id: number, title: string, jobId: number | null, favorite: boolean): ResumeBrief {
  return {
    id,
    title,
    job_id: jobId,
    job_title: "",
    company: "",
    source: "ai",
    favorite,
    note: "",
    model: "",
    enhancement_enabled: false,
    enhancement_level: "standard",
    template: "",
    format_name: "",
    format_config: {},
    page_limit: 1,
    font_scale: 1,
    language: "zh-CN",
    created_at: "",
    updated_at: "",
  } as unknown as ResumeBrief;
}

describe("useResumeSearchSelectForJob", () => {
  it("候选 = 本岗位 + 收藏，本岗位排最前且重复项只留一次", async () => {
    const mocked = vi.mocked(listResumes);
    mocked.mockImplementation((params = {}) =>
      Promise.resolve({
        items: params.job_id
          ? [brief(1, "岗位版", 7, false)]
          : [brief(1, "岗位版", 7, true), brief(2, "通用收藏", null, true)],
        total: 2,
        page: 1,
        page_size: 50,
      }),
    );

    const { result } = renderHook(() => useResumeSearchSelectForJob(7));
    act(() => result.current.reload());

    await waitFor(() => expect(result.current.options).toHaveLength(2));
    expect(result.current.options.map((option) => option.value)).toEqual([1, 2]);
    // 两份都命中的（本岗位 + 收藏）只标「本岗位」：那是更强的语义。
    expect(result.current.options[0].label).toBe("岗位版（本岗位）");
    expect(result.current.options[1].label).toBe("通用收藏（收藏）");
    // 两路都带同一个关键词：收藏是在搜索结果里补位，不是固定首页。
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ job_id: 7, keyword: "", page_size: 50 }),
    );
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ favorite: true, keyword: "", page_size: 50 }),
    );
  });

  it("没有关联岗位时也要列出收藏（jobId 为 null）", async () => {
    const mocked = vi.mocked(listResumes);
    mocked.mockImplementation((params = {}) =>
      Promise.resolve({
        items: params.favorite ? [brief(3, "收藏母版", null, true)] : [],
        total: 1,
        page: 1,
        page_size: 50,
      }),
    );

    const { result } = renderHook(() => useResumeSearchSelectForJob(null));
    act(() => result.current.reload());

    await waitFor(() => expect(result.current.options).toHaveLength(1));
    expect(result.current.options[0]).toMatchObject({ value: 3, label: "收藏母版（收藏）" });
    // 没有岗位就不该发一次 job_id=undefined 的无效查询。
    expect(mocked).not.toHaveBeenCalledWith(expect.objectContaining({ job_id: undefined }));
  });
});
