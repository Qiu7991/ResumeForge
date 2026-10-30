import { afterEach, describe, expect, it, vi } from "vitest";
import { batchExportResumes } from "./resumeBatchExport";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("batchExportResumes", () => {
  it("POST resume_ids + format，并从响应头还原文件名/份数/跳过原因", async () => {
    const detail = "《草稿版》：导出被拦截：正文还有【待补】标记";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(["zip-bytes"]), {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition":
            "attachment; filename*=UTF-8''" + encodeURIComponent("简历批量导出-20261031.zip"),
          "X-Batch-Exported": "2",
          "X-Batch-Skipped": "1",
          "X-Batch-Skipped-Detail": encodeURIComponent(detail),
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await batchExportResumes([5, 3], "docx");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ resume_ids: [5, 3], format: "docx" }));
    expect(result.filename).toBe("简历批量导出-20261031.zip");
    expect(result.exported).toBe(2);
    expect(result.skipped).toBe(1);
    expect(result.skippedDetail).toBe(detail);
  });

  it("缺响应头时给可用的默认值，不把 NaN 传给界面", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(new Blob(["zip"]), { status: 200 })),
    );

    const result = await batchExportResumes([1]);

    expect(result.filename).toBe("简历批量导出.zip");
    expect(result.exported).toBe(0);
    expect(result.skipped).toBe(0);
    expect(result.skippedDetail).toBe("");
  });
});
