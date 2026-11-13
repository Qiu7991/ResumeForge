// SPDX-License-Identifier: Apache-2.0
/**
 * 一个存在 localStorage 里的对象/数组偏好（筛选项、关键词列表这类）。
 *
 * 与 `usePersistentNumber` 同源同理由：这些是**用户填过的条件**，不是页面临时状态。
 * 采集页每次打开都要重填关键词、经验、学历、薪资区间、城市、翻页数，等于把用户
 * 上一轮的判断全部作废——而采集本来就是个反复微调的过程（收紧一次、放宽一次）。
 *
 * 与数字版的差别只有两点：
 *   1. 存 JSON 而不是字符串（`String(value)` 对数组会得到 "a,b"）；
 *   2. 读取时要过 `hydrate`（调用方传的归一化函数），因为存进去的形状可能来自旧版本，
 *      或被人手改过。**不做归一化就等于把校验责任推给每个使用点**，而那些点写的是
 *      `filters.experience.map(...)`，脏值会直接白屏。
 *
 * 容错优先：读不到、解析失败、hydrate 抛错，一律静默回退默认值。
 */
import { useCallback, useEffect, useRef, useState } from "react";

export function usePersistentValue<T>(
  key: string,
  fallback: T,
  hydrate: (raw: unknown) => T,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null) return fallback;
      return hydrate(JSON.parse(raw));
    } catch {
      return fallback;
    }
  });

  // hydrate 通常是行内箭头函数，每次渲染都是新引用。放进 set 的依赖里会让
  // set 每渲染一次就换一个身份，而它会被传给 memo 过的子组件——用 ref 取最新那份。
  const hydrateRef = useRef(hydrate);
  hydrateRef.current = hydrate;

  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // 存不进去就算了：本次会话内仍然生效，只是下次打开回到旧值。
      }
    },
    [key],
  );

  // 跨标签页同步：同一个应用开两个窗口时，在一个窗口改条件，另一个窗口下次
  // 打开页面应当看到同一份（否则用户会以为「我明明改过」）。
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== key || event.newValue === null) return;
      try {
        setValue(hydrateRef.current(JSON.parse(event.newValue)));
      } catch {
        // 另一个窗口写进来的形状不认识：保留当前值，别把界面清空。
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key]);

  return [value, set];
}

export default usePersistentValue;
