// SPDX-License-Identifier: Apache-2.0
/**
 * 一个存在 localStorage 里的数值偏好（分数线这类）。
 *
 * 为什么不用 useState：分数线是**筛选偏好**——用户调到 85 分，下次打开还是 85 分。
 * 用 useState 的话每次刷新都回到默认值，看起来像"设置没生效"。
 *
 * 容错优先：读取时任何异常（隐私模式禁用 storage、存进去的是脏值、超出范围）都
 * 静默回到默认值。一个偏好读不到不该把整页搞白。
 */
import { useCallback, useState } from "react";

export function usePersistentNumber(
  key: string,
  fallback: number,
  { min = 0, max = 100 }: { min?: number; max?: number } = {},
): [number, (next: number) => void] {
  const clamp = useCallback(
    (value: number) => Math.min(max, Math.max(min, Math.round(value))),
    [max, min],
  );

  const [value, setValue] = useState<number>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null) return fallback;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) return fallback;
      return Math.min(max, Math.max(min, Math.round(parsed)));
    } catch {
      return fallback;
    }
  });

  const set = useCallback(
    (next: number) => {
      const clamped = clamp(next);
      setValue(clamped);
      try {
        window.localStorage.setItem(key, String(clamped));
      } catch {
        // 存不进去就算了：本次会话内仍然生效，只是下次打开回到旧值。
      }
    },
    [clamp, key],
  );

  return [value, set];
}

export default usePersistentNumber;
