/** 「AI 对比选岗 / 匹配度分析」入口的前置校验：纯函数，方便单测与复用。
 *
 * 两个入口分析的都是勾选的岗位：没进选择模式先带用户进选择模式（而不是丢一句
 * 「请先选择岗位」的死路提示）；横向对比另有 2–12 个岗位的规模约束。
 */
export type MatchBatchView = "setup" | "history";
export type MatchBatchMode = "match" | "compare";

export type MatchBatchGate =
  | { kind: "enter-selection" }
  | { kind: "warn"; message: string }
  | { kind: "open"; view: MatchBatchView; mode: MatchBatchMode };

export function resolveMatchBatchGate({
  view,
  mode,
  selectionMode,
  selectedCount,
}: {
  view: MatchBatchView;
  mode: MatchBatchMode;
  selectionMode: boolean;
  selectedCount: number;
}): MatchBatchGate {
  if (view !== "setup") return { kind: "open", view, mode };
  if (!selectionMode) return { kind: "enter-selection" };
  if (selectedCount === 0) return { kind: "warn", message: "请先选择岗位" };
  if (mode === "compare" && selectedCount < 2) {
    return { kind: "warn", message: "AI 对比选岗至少需要勾选 2 个岗位" };
  }
  if (mode === "compare" && selectedCount > 12) {
    return { kind: "warn", message: "AI 对比选岗一次最多 12 个岗位" };
  }
  if (mode === "match" && selectedCount > 50) {
    return { kind: "warn", message: "一次最多分析 50 个岗位" };
  }
  return { kind: "open", view, mode };
}
