import { describe, expect, it } from "vitest";
import { resolveMatchBatchGate } from "./matchBatchGate";

const base = { view: "setup" as const, selectionMode: true };

describe("resolveMatchBatchGate", () => {
  it("未进入选择模式：先带用户进入选择模式", () => {
    expect(
      resolveMatchBatchGate({ ...base, mode: "compare", selectionMode: false, selectedCount: 0 }),
    ).toEqual({ kind: "enter-selection" });
  });

  it("对比选岗要求 2–12 个岗位", () => {
    expect(resolveMatchBatchGate({ ...base, mode: "compare", selectedCount: 1 })).toMatchObject({
      kind: "warn",
    });
    expect(resolveMatchBatchGate({ ...base, mode: "compare", selectedCount: 13 })).toMatchObject({
      kind: "warn",
    });
    expect(resolveMatchBatchGate({ ...base, mode: "compare", selectedCount: 2 })).toEqual({
      kind: "open",
      view: "setup",
      mode: "compare",
    });
  });

  it("逐岗匹配仍支持最多 50 个岗位", () => {
    expect(resolveMatchBatchGate({ ...base, mode: "match", selectedCount: 51 })).toMatchObject({
      kind: "warn",
    });
    expect(resolveMatchBatchGate({ ...base, mode: "match", selectedCount: 50 })).toMatchObject({
      kind: "open",
    });
  });

  it("历史记录页不做岗位数量校验", () => {
    expect(
      resolveMatchBatchGate({ ...base, view: "history", mode: "compare", selectedCount: 0 }),
    ).toEqual({ kind: "open", view: "history", mode: "compare" });
  });
});
