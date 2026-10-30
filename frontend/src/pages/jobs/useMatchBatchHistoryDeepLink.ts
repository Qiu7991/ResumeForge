/** 完成通知的「查看结果」深链：/jobs?match_batch=history 打开分析记录后清掉参数。
 *
 * 让刷新/返回不会再弹；`useJobsPageState` 管它自己的筛选参数，这里只动 match_batch。
 * URL → state 的镜像同步属"派生事件"，规则按书面理由豁免（与 useJobsPageState 同模式）。
 */
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

export function useMatchBatchHistoryDeepLink(
  setView: (view: "setup" | "history") => void,
  setOpen: (open: boolean) => void,
): void {
  const [searchParams, setSearchParams] = useSearchParams();

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (searchParams.get("match_batch") !== "history") return;
    setView("history");
    setOpen(true);
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("match_batch");
        return next;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams, setView, setOpen]);
  /* eslint-enable react-hooks/set-state-in-effect */
}
