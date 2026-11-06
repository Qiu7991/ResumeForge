// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职工作台轮询：single-flight + 1.5/3/6s 失败退避（与 useTaskPolling 同一套节奏）。
 *
 * 为什么不是复用 useTaskPolling：它类型绑定了 `ApplyTaskDetail`（数字 taskId、
 * 404 语义），而 AI 侧轮的是无 id 的工作台聚合状态、终态判据也不同。逻辑同构
 * 但契约不同，按交接文档 §7.4 单独实现，不共用类型。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { isCancellation } from "../api/client";
import { isDocumentHidden, onVisibilityChange } from "../utils/visibility";

const POLL_INTERVAL_MS = 1500;
const BACKOFF_MS = [1500, 3000, 6000] as const;

interface PollingState<T> {
  data: T | null;
  error: string;
  /** 手动拉取一次；返回是否成功（轮询循环据此退避）。 */
  refresh: () => Promise<boolean>;
}

/**
 * @param fetcher 拉取工作台状态；对调用方保持稳定语义（内部 ref 取最新）。
 * @param enabled false 时停止轮询（保留当前数据，供手动 refresh）。
 */
export function useAiJobsPolling<T>(
  fetcher: (signal?: AbortSignal) => Promise<T>,
  enabled: boolean,
): PollingState<T> {
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const version = useRef(0);
  const inFlight = useRef<number | null>(null);
  const failures = useRef(0);

  const refresh = useCallback(async (): Promise<boolean> => {
    const current = ++version.current;
    inFlight.current = current;
    try {
      const result = await fetcherRef.current();
      if (current === version.current) {
        setData(result);
        setError("");
      }
      return true;
    } catch (err) {
      if (current === version.current && !isCancellation(err)) {
        setError(err instanceof Error ? err.message : String(err));
      }
      return false;
    } finally {
      if (inFlight.current === current) inFlight.current = null;
    }
  }, []);

  useEffect(() => {
    version.current += 1;
    failures.current = 0;
    if (enabled) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let timer: number | undefined;

    const schedule = (delay: number) => {
      if (!disposed) timer = window.setTimeout(() => void tick(), delay);
    };

    const tick = async () => {
      if (disposed) return;
      // 后台跳过本轮；single-flight：上一轮没回来不叠加。
      if (isDocumentHidden() || inFlight.current !== null) {
        schedule(POLL_INTERVAL_MS);
        return;
      }
      const ok = await refresh();
      if (disposed) return;
      if (ok) {
        failures.current = 0;
        schedule(POLL_INTERVAL_MS);
      } else {
        failures.current += 1;
        schedule(BACKOFF_MS[Math.min(failures.current, BACKOFF_MS.length) - 1]);
      }
    };

    const unsubscribeVisibility = onVisibilityChange(() => {
      if (disposed || isDocumentHidden() || inFlight.current !== null) return;
      if (timer !== undefined) window.clearTimeout(timer);
      void tick();
    });

    schedule(POLL_INTERVAL_MS);

    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      unsubscribeVisibility();
    };
  }, [enabled, refresh]);

  return { data, error, refresh };
}
