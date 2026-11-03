// SPDX-License-Identifier: Apache-2.0
/** 投递队列的简历下拉：本岗位的简历排最前，收藏简历补在后面并去重。 */
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
});
