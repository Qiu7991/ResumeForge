// SPDX-License-Identifier: Apache-2.0
/** 二开回归（Phase 5 / B3）：只测纯函数层，不起 React 渲染。
 *
 * 钉住两条二开不变量：
 * 1. 覆盖补全（F09）：按身份合并、重复补全幂等——重复点「补上这段」不追加第二份；
 * 2. 生成版式（F04/F08）：buildSectionOrderConfig 不把 v1 旧键 hidden_sections 带进
 *    生成请求（Phase 3.2），section_order 与默认相同就不落键。
 *
 * fixture 形状与 fillCoverageNote.test.ts 保持同一套（PaperProjectionOut 的 candidates
 * 必须带 document_entry，fillCoverageNote 按条目身份合并）。
 */

import { describe, expect, it } from "vitest";

import { fillCoverageNote } from "./projectionContent";
import type { PaperProjectionOut } from "./types";
import { defaultEntryLayout, defaultSectionLayout } from "../resume-document/defaults";
import type { FieldItem, ResumeDocument, ResumeEntry, ResumeItem, TextItem } from "../../types/resumeDocument";
import {
  buildSectionOrderConfig,
  DEFAULT_RESUME_SECTION_ORDER,
} from "../../utils/resumeSectionOrder";

function field(id: string, key: string, value: string): FieldItem {
  return {
    kind: "field",
    id,
    key,
    label: "",
    value,
    placement: "title",
    format: "text",
    wrap: "none",
    show_label: false,
    solo: false,
    source: null,
    body_style: "bullet",
  };
}

function text(id: string, value: string): TextItem {
  return { kind: "text", id, style: "paragraph", text: value, hidden: false };
}

function entry(id: string, items: ResumeItem[]): ResumeEntry {
  return {
    id,
    hidden: false,
    lock_content: false,
    lock_layout: false,
    layout: defaultEntryLayout(),
    items,
  };
}

function section(key: string, kind: "entries" | "inline" | "text", entries: ResumeEntry[]) {
  return { key, title: "", kind, layout: defaultSectionLayout(), entries };
}

function baseDocument(): ResumeDocument {
  return {
    version: 2,
    language: "zh-CN",
    header: { items: [], contact_breaks: [] },
    sections: [
      section("projects", "entries", [
        entry("ob_p1", [field("ob_pn1", "name", "AI 简历工作台"), text("ob_t1", "已有亮点")]),
      ]),
    ],
  };
}

function projection(): PaperProjectionOut {
  const projects = section("projects", "entries", [
    entry("ob_p1", [field("ob_pn1", "name", "AI 简历工作台"), text("ob_t2", "资料里的新亮点")]),
    entry("ob_p2", [field("ob_pn2", "name", "PixelBeads 拼豆网站"), text("ob_t3", "独立上线的小程序")]),
  ]);
  const content: ResumeDocument = { ...baseDocument(), sections: [projects] };
  return {
    content,
    candidates: [
      { section_key: "projects", title: "AI 简历工作台", document_entry: projects.entries[0] },
      { section_key: "projects", title: "PixelBeads 拼豆网站", document_entry: projects.entries[1] },
    ],
  } as unknown as PaperProjectionOut;
}

function entryNames(document: ResumeDocument): string[] {
  const projects = document.sections.find((s) => s.key === "projects");
  return (projects?.entries ?? []).map((e) => {
    const name = (e.items ?? []).find((i) => i.kind === "field" && i.key === "name");
    return name && name.kind === "field" ? name.value : "";
  });
}

describe("fork 回归：覆盖补全（F09）", () => {
  it("按身份追加缺失条目，重复补全幂等（不追加第二份）", () => {
    const note = { section: "projects", names: ["PixelBeads 拼豆网站"] };
    const first = fillCoverageNote(baseDocument(), projection(), note);
    expect(first.filled).toBeGreaterThan(0);

    const second = fillCoverageNote(first.document, projection(), note);
    expect(second.filled).toBe(0);
    expect(entryNames(second.document)).toEqual(["AI 简历工作台", "PixelBeads 拼豆网站"]);
  });

  it("已有条目只并要点，不产生重名条目", () => {
    const result = fillCoverageNote(baseDocument(), projection(), {
      section: "projects",
      names: ["AI 简历工作台"],
    });
    expect(entryNames(result.document).filter((name) => name === "AI 简历工作台")).toHaveLength(1);
  });
});

describe("fork 回归：生成版式不带旧键（F04/F08）", () => {
  it("base 里的 hidden_sections 不进生成请求", () => {
    const next = buildSectionOrderConfig(DEFAULT_RESUME_SECTION_ORDER, DEFAULT_RESUME_SECTION_ORDER, {
      hidden_sections: ["awards"],
    });
    expect("hidden_sections" in next).toBe(false);
    expect("section_order" in next).toBe(false);
  });

  it("用户调过顺序才写 section_order；与默认相同就不写", () => {
    const reordered = [...DEFAULT_RESUME_SECTION_ORDER].reverse();
    const changed = buildSectionOrderConfig(reordered, DEFAULT_RESUME_SECTION_ORDER, {});
    expect(changed.section_order).toEqual(reordered);

    const unchanged = buildSectionOrderConfig(
      DEFAULT_RESUME_SECTION_ORDER,
      DEFAULT_RESUME_SECTION_ORDER,
      {},
    );
    expect("section_order" in unchanged).toBe(false);
  });
});
