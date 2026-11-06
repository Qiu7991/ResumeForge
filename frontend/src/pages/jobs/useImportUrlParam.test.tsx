// SPDX-License-Identifier: Apache-2.0
/** 扩展收录弹窗：本地服务短暂不可达时自动重试一次（导入接口按 URL 幂等）。 */
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { useImportUrlParam } from "./useImportUrlParam";

const mocks = vi.hoisted(() => ({ importJobFromUrl: vi.fn() }));

vi.mock("../../api/jobs", () => ({ importJobFromUrl: mocks.importJobFromUrl }));

function Harness() {
  useImportUrlParam(vi.fn());
  return null;
}

const ENTRY =
  "/jobs?close_after=1&import_url=" + encodeURIComponent("https://example.com/job/1");

beforeEach(() => {
  mocks.importJobFromUrl.mockReset();
  window.close = vi.fn();
  Object.defineProperty(window, "opener", { value: null, configurable: true });
});

describe("useImportUrlParam", () => {
  it("弹窗加载后先发 started 回执，告诉扩展窗口已连上", async () => {
    mocks.importJobFromUrl.mockResolvedValue({ id: 1, title: "测试岗位" });
    const postMessage = vi.fn();
    Object.defineProperty(window, "opener", {
      value: { postMessage },
      configurable: true,
    });

    render(
      <MemoryRouter initialEntries={[ENTRY]}>
        <Harness />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        { type: "resumeforge-import-started" },
        "*",
      ),
    );
  });

  it("网络类失败后等 2 秒重试一次，成功后关闭弹窗", async () => {
    mocks.importJobFromUrl
      .mockRejectedValueOnce(new ApiError("网络失败", undefined, { code: "network" }))
      .mockResolvedValueOnce({ id: 1, title: "测试岗位" });

    render(
      <MemoryRouter initialEntries={[ENTRY]}>
        <Harness />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mocks.importJobFromUrl).toHaveBeenCalledTimes(2), {
      timeout: 5000,
    });
    await waitFor(() => expect(window.close).toHaveBeenCalled(), { timeout: 2000 });
  });

  it("非网络错误不重试（例如浏览器没启动的 409）", async () => {
    mocks.importJobFromUrl.mockRejectedValue(
      new ApiError("专用浏览器尚未启动", 409, { code: "http" }),
    );

    render(
      <MemoryRouter initialEntries={[ENTRY]}>
        <Harness />
      </MemoryRouter>,
    );

    await waitFor(() => expect(mocks.importJobFromUrl).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(mocks.importJobFromUrl).toHaveBeenCalledTimes(1);
  });
});
