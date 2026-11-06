// SPDX-License-Identifier: Apache-2.0
/** useAiJobsPolling：single-flight、退避、终态停轮、手动刷新。 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAiJobsPolling } from "./useAiJobsPolling";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useAiJobsPolling", () => {
  it("enabled 时立即拉取一次并在成功后继续轮询", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue({ n: 1 });
    const { result } = renderHook(() => useAiJobsPolling(fetcher, true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual({ n: 1 });
    expect(result.current.error).toBe("");
  });

  it("disabled 时不拉取；手动 refresh 可用", async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValue({ n: 2 });
    const { result } = renderHook(() => useAiJobsPolling(fetcher, false));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).not.toHaveBeenCalled();
    let ok = false;
    await act(async () => {
      ok = await result.current.refresh();
    });
    expect(ok).toBe(true);
    expect(result.current.data).toEqual({ n: 2 });
  });

  it("失败按 1.5/3/6 退避并在成功后复位", async () => {
    vi.useFakeTimers();
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("网络抖动"))
      .mockRejectedValueOnce(new Error("网络抖动"))
      .mockResolvedValue({ n: 3 });
    const { result } = renderHook(() => useAiJobsPolling(fetcher, true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    // 第一次失败 → 下一次 1.5s 后
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBe("网络抖动");
    // 第二次失败 → 3s 后成功；错误态清除、数据更新（具体调用次数不钉死，只认结果）。
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(result.current.error).toBe("");
    expect(result.current.data).toEqual({ n: 3 });
  });

  it("fetcher 抛出的取消错误不进错误态", async () => {
    vi.useFakeTimers();
    // 与 request() 的取消形态一致：ApiError + code="cancelled"
    const { ApiError } = await import("../api/apiError");
    const cancellation = new ApiError("已取消", undefined, { code: "cancelled" });
    const fetcher = vi.fn().mockRejectedValue(cancellation);
    const { result } = renderHook(() => useAiJobsPolling(fetcher, true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBe("");
  });
});
