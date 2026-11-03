// SPDX-License-Identifier: Apache-2.0
/** 覆盖清单「从资料补上这段」：补进已有条目而不是造重复条目。 */
import { describe, expect, it } from "vitest";
import { fillCoverageNote } from "./projectionContent";
import type { PaperProjectionOut } from "./types";
import { defaultEntryLayout, defaultSectionLayout } from "../resume-document/defaults";
import type {
  FieldItem,
  ResumeDocument,
  ResumeEntry,
  ResumeItem,
  TextItem,
} from "../../types/resumeDocument";

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
      section("skills", "inline", [entry("ob_s1", [field("ob_sn1", "name", "TypeScript")])]),
      section("summary", "text", [entry("ob_sum1", [text("ob_sumt1", "旧总结")])]),
    ],
  };
}

function projection(): PaperProjectionOut {
  const projects = section("projects", "entries", [
    entry("ob_p1", [
      field("ob_pn1", "name", "AI 简历工作台"),
      text("ob_t1", "已有亮点"),
      text("ob_t2", "资料里的新亮点"),
      text("ob_t3", "资料里的第二条亮点"),
    ]),
    entry("ob_p2", [field("ob_pn2", "name", "PixelBeads 拼豆网站"), text("ob_t4", "拼豆项目亮点")]),
  ]);
  const skills = section("skills", "inline", [
    entry("ob_s1", [field("ob_sn1", "name", "TypeScript")]),
    entry("ob_s2", [field("ob_sn2", "name", "Rust")]),
  ]);
  const summary = section("summary", "text", [entry("ob_sum1", [text("ob_sumt1", "资料里的总结")])]);
  const content: ResumeDocument = {
    ...baseDocument(),
    sections: [projects, skills, summary],
  };
  return {
    content,
    candidates: [
      { section_key: "projects", title: "AI 简历工作台", document_entry: projects.entries[0] },
      { section_key: "projects", title: "PixelBeads 拼豆网站", document_entry: projects.entries[1] },
      { section_key: "skills", title: "Rust", document_entry: skills.entries[1] },
      { section_key: "summary", title: "个人总结/自我评价" },
    ],
  } as unknown as PaperProjectionOut;
}

const texts = (entryValue: ResumeEntry) =>
  entryValue.items.flatMap((item) => (item.kind === "text" ? [item.text] : []));
const names = (document: ResumeDocument, key: string) =>
  document.sections
    .find((section) => section.key === key)
    ?.entries.flatMap((entryValue) =>
      entryValue.items.flatMap((item) =>
        item.kind === "field" && item.key === "name" ? [item.value] : [],
      ),
    ) ?? [];

describe("fillCoverageNote", () => {
  it("项目亮点补进已有项目，不追加重复项目", () => {
    const result = fillCoverageNote(baseDocument(), projection(), {
      section: "projects",
      names: ["资料里的新亮点", "资料里的第二条亮点"],
    });

    const projects = result.document.sections.find((section) => section.key === "projects");
    expect(projects?.entries).toHaveLength(1);
    expect(texts(projects!.entries[0])).toEqual(["已有亮点", "资料里的新亮点", "资料里的第二条亮点"]);
    expect(result.filled).toBe(2);
  });

  it("整条项目没写才追加，重复执行不会追第二份", () => {
    const note = { section: "projects", names: ["PixelBeads 拼豆网站"] };
    const first = fillCoverageNote(baseDocument(), projection(), note);
    const second = fillCoverageNote(first.document, projection(), note);

    const projects = second.document.sections.find((section) => section.key === "projects");
    expect(projects?.entries).toHaveLength(2);
    expect(names(second.document, "projects")).toEqual(["AI 简历工作台", "PixelBeads 拼豆网站"]);
    expect(second.filled).toBe(0);
  });

  it("缺失技能作为新条目追加，且不重复", () => {
    const note = { section: "skills", names: ["Rust"] };
    const first = fillCoverageNote(baseDocument(), projection(), note);
    const second = fillCoverageNote(first.document, projection(), note);

    expect(names(first.document, "skills")).toEqual(["TypeScript", "Rust"]);
    expect(names(second.document, "skills")).toEqual(["TypeScript", "Rust"]);
  });

  it("个人总结按资料原文替换当前段落", () => {
    const result = fillCoverageNote(baseDocument(), projection(), {
      section: "summary",
      names: ["个人总结（与资料原文相似度 14%）"],
    });

    const summary = result.document.sections.find((section) => section.key === "summary");
    expect(texts(summary!.entries[0])).toEqual(["资料里的总结"]);
    expect(result.filled).toBe(1);
  });
});
