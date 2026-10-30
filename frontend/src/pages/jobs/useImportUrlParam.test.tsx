/** `?import_url=` 的两种落地：普通页面切到详情；一次性窗口里导入完回话并自关。 */

import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useImportUrlParam } from "./useImportUrlParam";

const apiMocks = vi.hoisted(() => ({ importJobFromUrl: vi.fn() }));
vi.mock("../../api/jobs", () => apiMocks);

function Harness({ onImported = vi.fn() }: { onImported?: (id: number) => void }) {
  useImportUrlParam(onImported);
  return null;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("useImportUrlParam", () => {
  it("一次性窗口里导入成功后回话给打开者并自关", async () => {
    apiMocks.importJobFromUrl.mockResolvedValue({ id: 7, title: "电力市场AI应用实习生" });
    const postMessage = vi.fn();
    Object.defineProperty(window, "opener", { value: { postMessage }, configurable: true });
    const close = vi.spyOn(window, "close").mockImplementation(() => {});

    render(
      <MemoryRouter
        initialEntries={[
          "/jobs?close_after=1&import_url=https%3A%2F%2Fwww.zhipin.com%2Fjob_detail%2Fabc.html",
        ]}
      >
        <Harness />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        { type: "resumeforge-import-result", ok: true, title: "电力市场AI应用实习生" },
        "*",
      ),
    );
    expect(close).toHaveBeenCalled();
  });

  it("普通页面导入成功后交给调用方（由它切到详情）", async () => {
    apiMocks.importJobFromUrl.mockResolvedValue({ id: 9, title: "海外 B2B" });
    const onImported = vi.fn();

    render(
      <MemoryRouter initialEntries={["/jobs?import_url=https%3A%2F%2Fx.test%2Fa"]}>
        <Harness onImported={onImported} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(onImported).toHaveBeenCalledWith(9));
  });

  it("关闭窗口模式下失败也要回话，不能让按钮一直转", async () => {
    apiMocks.importJobFromUrl.mockRejectedValue(new Error("页面里没读到岗位名称"));
    const postMessage = vi.fn();
    Object.defineProperty(window, "opener", { value: { postMessage }, configurable: true });
    vi.spyOn(window, "close").mockImplementation(() => {});

    render(
      <MemoryRouter initialEntries={["/jobs?close_after=1&import_url=https%3A%2F%2Fx.test%2Fa"]}>
        <Harness />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith(
        { type: "resumeforge-import-result", ok: false, error: "页面里没读到岗位名称" },
        "*",
      ),
    );
  });
});
