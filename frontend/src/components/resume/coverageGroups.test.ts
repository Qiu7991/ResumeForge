// SPDX-License-Identifier: Apache-2.0
/**
 * 未收录清单的**纯数据整理**：5-A 的新分组键、原因推导优先级、3-A 的三分支判定。
 *
 * 这些规则以前散在组件里（甚至不存在），组件测试只能间接碰到；单独成文件后每条口径
 * 都能逐条钉住：
 * - 分组键是 `(section, section_label)`，`项目「X」的亮点` 不再并进 `项目经历`；
 * - 归一别名只用于查语言包（`section`），发给后端仍用原样键（`rawSection`）；
 * - 显式 `reasons` 优先，缺失时按 `capacity > filtered > model` 推导，三轴都不命中
 *   就是 `null`（界面显示「未说明」，不硬猜）；
 * - 「补进简历 / AI 补上这段 / 去制作台添加」的分支只由 `resolveCoverageAction` 决定。
 *
 * 本文件不含 CJK 字面量（i18n 棘轮只统计 `ByText` 里的中文，这里一条都没有）。
 */
import { describe, expect, it } from "vitest";
import type { ResumeCoverageNote } from "../../types";
import {
  coverageReasonLabelKey,
  coverageSummaryCount,
  DEFAULT_VISIBLE_ITEMS,
  groupCoverageNotes,
  isCustomSection,
  LONG_ITEM_CHARS,
  reasonOf,
  resolveCoverageAction,
} from "./coverageGroups";

function note(overrides: Partial<ResumeCoverageNote> = {}): ResumeCoverageNote {
  return {
    section: "projects",
    section_label: "PROJECTS",
    names: [],
    filtered: [],
    model_omitted: [],
    total: 0,
    ...overrides,
  };
}

describe("groupCoverageNotes grouping key (5-A)", () => {
  it("keeps notes of one section but different section_label in separate groups", () => {
    const groups = groupCoverageNotes([
      note({ names: ["Alpha"], total: 1 }),
      note({ names: ["Alpha"], section_label: "PROJECT-ALPHA-HIGHLIGHTS", total: 6 }),
    ]);

    // The bug: only `section` was used, so 1 project name and 6 highlight lines merged
    // into one "projects (7)" row and the user could not tell them apart.
    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.sectionLabel)).toEqual([
      "PROJECTS",
      "PROJECT-ALPHA-HIGHLIGHTS",
    ]);
    expect(groups.map((group) => group.total)).toEqual([1, 6]);
  });

  it("merges notes with the same (section, section_label) and sums total", () => {
    const groups = groupCoverageNotes([
      note({ names: ["Alpha"], total: 1 }),
      note({ names: ["Beta"], total: 2 }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].names).toEqual(["Alpha", "Beta"]);
    expect(groups[0].total).toBe(3);
  });

  it("dedupes names inside a group while keeping first-seen order", () => {
    const groups = groupCoverageNotes([
      note({ names: ["A", "B"], total: 2 }),
      note({ names: ["B", "C"], total: 3 }),
    ]);

    expect(groups[0].items.map((item) => item.name)).toEqual(["A", "B", "C"]);
  });

  it("normalises profile-side plural keys for label lookup but keeps the raw key", () => {
    const groups = groupCoverageNotes([
      note({ section: "experiences", section_label: "EXP", names: ["Alpha"], total: 1 }),
      note({ section: "experience", section_label: "EXP", names: ["Beta"], total: 1 }),
    ]);

    // One group: the two keys are the same section once normalised (label lookup needs it).
    expect(groups).toHaveLength(1);
    expect(groups[0].section).toBe("experience");
    // The raw key survives: it is what `append-profile-entries` must receive.
    expect(groups[0].rawSection).toBe("experiences");
  });

  it("keeps group order at the first appearance in the backend array", () => {
    const groups = groupCoverageNotes([
      note({ section: "skills", section_label: "SKILLS", names: ["Excel"], total: 1 }),
      note({ names: ["Alpha"], total: 1 }),
      note({ section: "skills", section_label: "SKILLS", names: ["SQL"], total: 1 }),
    ]);

    expect(groups.map((group) => group.section)).toEqual(["skills", "projects"]);
    expect(groups[0].total).toBe(2);
  });
});

describe("reason derivation (5-A)", () => {
  it("prefers the explicit reasons map over the three arrays", () => {
    const value = note({
      names: ["Excel"],
      filtered: ["Excel"],
      model_omitted: ["Excel"],
      reasons: { Excel: "model" },
    });

    expect(reasonOf(value, "Excel")).toBe("model");
  });

  it("falls back to capacity > filtered > model for legacy records", () => {
    const value = note({
      names: ["A", "B", "C", "D"],
      capacity_omitted: ["A"],
      filtered: ["A", "B"],
      model_omitted: ["A", "B", "C"],
    });

    // A is in all three buckets -> capacity wins (it is the hardest constraint).
    expect(reasonOf(value, "A")).toBe("capacity");
    expect(reasonOf(value, "B")).toBe("filtered");
    expect(reasonOf(value, "C")).toBe("model");
    // D is in no bucket at all: the UI must say "not stated" instead of guessing.
    expect(reasonOf(value, "D")).toBeNull();
  });

  it("ignores an unknown reason value and keeps deriving from the arrays", () => {
    const value = note({
      names: ["Excel"],
      filtered: ["Excel"],
      // A future backend may add a reason axis; the read side must not crash or guess.
      reasons: { Excel: "brand_new_axis" },
    });

    expect(reasonOf(value, "Excel")).toBe("filtered");
  });

  it("counts every item exactly once in the group header buckets", () => {
    const [group] = groupCoverageNotes([
      note({
        section: "skills",
        section_label: "SKILLS",
        names: ["A", "B", "C", "D"],
        capacity_omitted: ["A", "B"],
        filtered: [],
        model_omitted: ["C"],
        total: 4,
      }),
    ]);

    const counted =
      group.reasonCounts.capacity + group.reasonCounts.filtered + group.reasonCounts.model;
    // "The numbers in the header badge add up to the number of items" (5-A acceptance).
    expect(counted + group.unknownCount).toBe(group.items.length);
    expect(group.reasonCounts).toEqual({ capacity: 2, filtered: 0, model: 1 });
    expect(group.unknownCount).toBe(1);
  });

  it("flags a group as mixed only when it carries more than one reason", () => {
    const [pure] = groupCoverageNotes([
      note({ names: ["A", "B"], filtered: ["A", "B"], total: 2 }),
    ]);
    const [mixed] = groupCoverageNotes([
      note({ names: ["A", "B"], filtered: ["A"], model_omitted: ["B"], total: 2 }),
    ]);

    expect(pure.mixedReason).toBe(false);
    expect(mixed.mixedReason).toBe(true);
  });

  it("treats 'not stated' as a distinct reason when mixing", () => {
    const [group] = groupCoverageNotes([note({ names: ["A", "B"], filtered: ["A"], total: 2 })]);

    // B has no explanation: half-explained groups still need per-row badges.
    expect(group.mixedReason).toBe(true);
  });

  it("maps every reason (including null) to a message key", () => {
    expect(coverageReasonLabelKey("filtered")).toBe("resume.coverage.reason.filtered");
    expect(coverageReasonLabelKey("capacity")).toBe("resume.coverage.reason.capacity");
    expect(coverageReasonLabelKey("model")).toBe("resume.coverage.reason.model");
    expect(coverageReasonLabelKey(null)).toBe("resume.coverage.reason.unknown");
  });
});

describe("coverageSummaryCount", () => {
  it("sums group totals (not names length) plus legacy warnings", () => {
    const count = coverageSummaryCount(
      [
        note({ names: ["Alpha"], total: 6 }),
        note({ section: "skills", section_label: "SKILLS", names: ["Excel"], total: 2 }),
      ],
      ["legacy warning"],
    );

    // Unchanged by 5-A: splitting one section into several groups must not change the total.
    expect(count).toBe(9);
  });

  it("is zero when both inputs are empty", () => {
    expect(coverageSummaryCount([], [])).toBe(0);
  });
});

describe("entry_ids union (3-A)", () => {
  it("collects the ids of every note in the group without duplicates", () => {
    const [group] = groupCoverageNotes([
      note({ section: "custom:abc", section_label: "Mine", entry_ids: ["e1", "e2"], total: 2 }),
      note({ section: "custom:abc", section_label: "Mine", entry_ids: ["e2", "e3"], total: 1 }),
    ]);

    expect(group.entryIds).toEqual(["e1", "e2", "e3"]);
  });

  it("leaves entryIds empty for legacy records that never had the field", () => {
    const [group] = groupCoverageNotes([note({ section: "custom:abc", total: 1 })]);

    expect(group.entryIds).toEqual([]);
  });
});

describe("resolveCoverageAction decision table (3-A)", () => {
  const appendable = {
    section: "custom:abc",
    rawSection: "custom:abc",
    entryIds: ["e1"],
  };

  it("uses append for a custom section whose entries can be located", () => {
    expect(resolveCoverageAction(appendable)).toBe("append");
  });

  it("falls back to the workbench for a legacy custom section without entry_ids", () => {
    // No entry_ids: we cannot locate the entry deterministically, so we must not promise
    // an insert that would probably guess the wrong record.
    expect(resolveCoverageAction({ ...appendable, entryIds: [] })).toBe("workbench");
  });

  /*
   * 2026-11-08 口径变更（**产品能力变了，不是放松断言**）：
   *
   * 技能从「只能整组 AI 改写」变成「可以逐条确定性补入」。用户原话：「我的目的是
   * 能够有按键，我选择性的要补上哪些，而不是全让 ai 做决策」。后端 `skills` 现在是
   * 可补入板块（`resume_profile_append_builtin.BUILTIN_SECTIONS` 增加了 skills，
   * 资料侧每条技能 = 一条条目，简历侧每条也是独立 entry），所以有 entry_ids 就给
   * 「从资料补上这段」，而不是整组交给模型。
   *
   * `languages` / `summary` 没有条目概念（是整段文本），仍然只能靠修订。
   * 技能定位不到条目时（旧记录、资料改过名）仍会回落到 revise —— 见下面那条。
   */
  it("keeps the AI revise button for sections that are one whole text block", () => {
    for (const section of ["languages", "summary"]) {
      expect(resolveCoverageAction({ section, rawSection: section, entryIds: ["e1"] })).toBe(
        "revise",
      );
    }
  });

  it("offers per-entry append for skills once they can be located", () => {
    expect(
      resolveCoverageAction({ section: "skills", rawSection: "skills", entryIds: ["e1"] }),
    ).toBe("append");
  });

  it("still falls back to AI revise for skills whose entries cannot be located", () => {
    // 旧记录 / 生成后资料改过名：没有 entry_ids ⇒ 不能承诺"补哪一条"，但也不该送进
    // 制作台那条死路（技能本来就靠在正文里改写就能补）。
    expect(
      resolveCoverageAction({ section: "skills", rawSection: "skills", entryIds: [] }),
    ).toBe("revise");
  });

  /*
   * 2026-11-08 口径变更（**产品能力变了，不是放松断言**）：
   *
   * 旧断言是「所有条目级板块一律去制作台」。实际用户路径是死路——后端
   * `builtin_entry_ids` 明明定位到了资料条目的 id，清单上写着「项目经历 · 8 条」，
   * 点「去制作台添加」后制作台里并没有「补这段」入口。
   *
   * 现在后端真的支持内置板块补入了（`resume_profile_append_builtin` 复用生成链
   * 转换器把资料条目转成 v2 entry），所以有 entry_ids 就应当出「补进简历」。
   * 新的不变量：**有 entry_ids + 板块在可补入名单里 → append**。
   */
  it("offers append for entry-level sections once the backend can insert them", () => {
    for (const section of [
      "projects",
      "experience",
      "education",
      "awards",
      "campus_experience",
      "publications",
      "research_projects",
      "patents",
      "credentials",
    ]) {
      expect(resolveCoverageAction({ section, rawSection: section, entryIds: ["e1"] })).toBe(
        "append",
      );
    }
  });

  it("still sends entry-level sections to the workbench when nothing can be located", () => {
    // 没有 entry_ids = 定位不到资料条目（旧入口/旧记录）：不能承诺一次补入，
    // 那可能替用户插错记录。这条是 append 的前置条件，不是历史遗留。
    for (const section of ["projects", "experience", "education"]) {
      expect(resolveCoverageAction({ section, rawSection: section, entryIds: [] })).toBe(
        "workbench",
      );
    }
  });

  it("downgrades append to the workbench when the host cannot save", () => {
    expect(resolveCoverageAction(appendable, false)).toBe("workbench");
  });

  // 2026-11-08：字段级缺口（条目在、缺几句亮点/技术栈）。
  // 后端 `find_unwritten_field_details` 会显式标 `granularity: "field"`。
  // 这类缺口 append 做不到（`resume_profile_append` 只补整条），AI 修订却能改写
  // 已有项目的 highlights/tech_stack——所以必须给 revise，不能推去制作台。
  it("routes field-level gaps to AI revise even for entry-level sections", () => {
    for (const section of ["projects", "research_projects"]) {
      expect(
        resolveCoverageAction({
          section,
          rawSection: section,
          // entry_ids 可能为空（字段级没有单一条目身份），也可能带着——
          // 两种情况都必须走 revise，粒度标记说了算。
          entryIds: [],
          granularity: "field",
        }),
      ).toBe("revise");
      expect(
        resolveCoverageAction({
          section,
          rawSection: section,
          entryIds: ["e1"],
          granularity: "field",
        }),
      ).toBe("revise");
    }
  });

  it("keeps append and revise strictly separated by granularity", () => {
    // 整条没写（granularity 缺省 = entry）→ append。
    expect(
      resolveCoverageAction({ section: "projects", rawSection: "projects", entryIds: ["e1"] }),
    ).toBe("append");
    // 条目在、只缺几句（granularity = field）→ revise。
    // 这两种必须在同一条测试里对拍：字段级若漏到 append，会把整条资料再插一遍，
    // 正文出现两份同名项目——比漏几句严重得多。
    expect(
      resolveCoverageAction({
        section: "projects",
        rawSection: "projects",
        entryIds: [],
        granularity: "field",
      }),
    ).toBe("revise");
  });

  it("recognises the custom section prefix only", () => {
    expect(isCustomSection("custom:abc")).toBe(true);
    expect(isCustomSection("projects")).toBe(false);
  });
});

describe("display thresholds", () => {
  it("keeps 5 rows visible by default and ellipsises above 48 characters", () => {
    // Both numbers are product decisions from 5-A; pin them so a refactor cannot drift.
    expect(DEFAULT_VISIBLE_ITEMS).toBe(5);
    expect(LONG_ITEM_CHARS).toBe(48);
  });
});
