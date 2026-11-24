// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listResumes } from "../../../api/resumes";
import { fetchResumeTitles, RESUME_TITLE_PAGE_SIZE } from "./resumeTitles";

vi.mock("../../../api/resumes", () => ({
  listResumes: vi.fn(),
}));

describe("fetchResumeTitles", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("stays within backend GET /api/resumes page_size <= 100 limit", async () => {
    expect(RESUME_TITLE_PAGE_SIZE).toBeLessThanOrEqual(100);
    vi.mocked(listResumes).mockResolvedValueOnce({
      items: [{ id: 12, title: "AI Engineer" }],
      total: 1,
      page: 1,
      page_size: RESUME_TITLE_PAGE_SIZE,
    } as unknown as Awaited<ReturnType<typeof listResumes>>);

    const map = await fetchResumeTitles();

    expect(listResumes).toHaveBeenCalledWith({ page_size: RESUME_TITLE_PAGE_SIZE });
    expect(map).toEqual({ 12: "AI Engineer" });
  });
});
