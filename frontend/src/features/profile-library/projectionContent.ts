// SPDX-License-Identifier: Apache-2.0
/**
 * 服务端投影（`GET /api/profile/current/projection`）的 **v2 解析与合并**（纯函数，唯一实现）。
 *
 * ## 为什么需要它
 *
 * 投影的 `content` 自 v2 批次起是 **`ResumeDocument`**（sections/entries/items，item 自带
 * `source {section_key, field_id}`），候选直接带原生路径与条目。本文件负责：
 * - 候选 → v2 板块/条目（按 path 精确取，不按标题猜）；
 * - 合并进当前文档 = 只填空/补缺失（复用 `mergeProfileItems`），按 `source` 去重；
 *
 * 全部纯函数、不可变；「从资料填入」只有这一份解析/合并实现（ProfileFillMenu 与
 * profileFillOptions 的旧 v1 适配都从这里取）。
 */
import type {
  ResumeDocument,
  ResumeEntry,
  ResumeItem,
  ResumeSection,
} from "../../types/resumeDocument";
import { newId } from "../resume-document/normalize";
import { mergeProfileItems } from "../resume-document/convertFromProfile";
import type { PaperProjectionOut, ProjectionCandidateOut } from "./types";

/** 投影「消费分区键」（v1 资料层）→ v2 文档板块 key。 */
export const PROJECTION_SECTION_MAP: Record<string, string> = {
  education: "education",
  experience: "experience",
  campus_experience: "campus_experience",
  projects: "projects",
  skills: "skills",
  awards: "awards",
  publications: "publications",
  research_projects: "research_projects",
  patents: "patents",
  credentials: "credentials",
  languages: "languages",
};

/** 内容是不是 v2 文档（投影端点已切 v2；旧夹具/旧后端仍可能是 v1）。 */
export function isV2ProjectionContent(content: unknown): content is ResumeDocument {
  return (
    content !== null &&
    typeof content === "object" &&
    (content as { version?: unknown }).version === 2 &&
    Array.isArray((content as { sections?: unknown }).sections)
  );
}

/** 投影的 v2 文档；不是 v2（旧夹具/旧后端）返回 null。 */
export function projectionDocument(
  projection: PaperProjectionOut | null | undefined,
): ResumeDocument | null {
  const content = projection?.content;
  return isV2ProjectionContent(content) ? content : null;
}

/** 一个已解析的候选：v2 板块/条目 + 它对应的当前文档板块 key。 */
export interface ResolvedProjectionCandidate {
  candidate: ProjectionCandidateOut;
  /** v2 文档里的板块 key（系统板块 = education…；自建板块 = custom:<id>）。 */
  sectionKey: string;
  section: ResumeSection;
  entry: ResumeEntry;
  /** 该条目的 v2 items（原引用；合并时会按需克隆/改写）。 */
  items: ResumeItem[];
}

/** 拆 v2 路径：`{section}.{entryId}` / `{section}.{entryId}.{itemId}`。 */
function parseV2Path(
  path: string,
): { sectionKey: string; entryId: string; itemId: string | null } | null {
  const parts = path.split(".");
  if (parts.length < 2 || parts.length > 3) return null;
  if (parts.some((part) => part.length === 0)) return null;
  return { sectionKey: parts[0], entryId: parts[1], itemId: parts[2] ?? null };
}

/**
 * 候选 → v2 板块/条目。
 *
 * 解析顺序（backend-api v2 契约，2026-10-30）：
 * 1. **`candidate.document_entry`**：后端把该条目在 `projection.content` 里的**原样 v2 JSON**
 *    直接下发，拿它即可（不再解析路径；这是新代码的唯一推荐路径）；
 * 2. `candidate.document_path`（v2 路径 `{section}.{v2_entry_id}`）→ 在 content 里定位；
 *
 * 解析不到（空 section / 越界 / 自建板块被删）返回 null；菜单只列能真正填入的候选，
 * 不做点击无反应的死项。
 */
export function resolveProjectionCandidate(
  projection: PaperProjectionOut | null | undefined,
  candidate: ProjectionCandidateOut,
): ResolvedProjectionCandidate | null {
  const document = projectionDocument(projection);
  if (!document) return null;
  const path = candidate.document_path || "";
  const v2 = path.includes(".") ? parseV2Path(path) : null;
  const documentEntry = candidate.document_entry;
  if (documentEntry) {
    // 新契约：entry JSON 原样下发。板块优先按 document_path 定位，缺失时退回 section_key 映射，
    // 再不行按 entry id 全文档找（防御旧后端/夹具）。
    const mappedKey = PROJECTION_SECTION_MAP[candidate.section_key] ?? "";
    const sectionKey = v2?.sectionKey || mappedKey;
    const section =
      document.sections.find((item) => item.key === sectionKey) ??
      document.sections.find((item) => item.entries.some((entry) => entry.id === documentEntry.id));
    if (!section) return null;
    const entry =
      section.entries.find((item) => item.id === documentEntry.id) ??
      (documentEntry as ResumeEntry);
    return { candidate, sectionKey: section.key, section, entry, items: entry.items };
  }
  if (!v2) return null;
  const sectionKey = v2.sectionKey;
  const section = document.sections.find((item) => item.key === v2.sectionKey);
  const entry = section?.entries.find((item) => item.id === v2.entryId);
  if (!section || !entry) return null;
  return { candidate, sectionKey, section, entry, items: entry.items };
}

/** 候选里能解析到 v2 条目的那些（菜单只列能真正填入的）。 */
export function resolvableProjectionCandidates(
  projection: PaperProjectionOut | null | undefined,
): ResolvedProjectionCandidate[] {
  const result: ResolvedProjectionCandidate[] = [];
  for (const candidate of projection?.candidates ?? []) {
    const resolved = resolveProjectionCandidate(projection, candidate);
    if (resolved) result.push(resolved);
  }
  return result;
}

/** item 的资料来源键（`section_key.field_id`）；text item 没有 source → null。 */
export function itemSourceKey(item: ResumeItem): string | null {
  // 只有 FieldItem 带 source（后端 schema：list / authors / text 没有来源字段）。
  if (item.kind !== "field") return null;
  const source = item.source;
  if (!source || !source.section_key || !source.field_id) return null;
  return `${source.section_key}.${source.field_id}`;
}

/** 深拷贝并换新 id（把投影条目搬进当前文档时避免 id 冲突）。 */
function cloneItemsWithNewIds(items: readonly ResumeItem[]): ResumeItem[] {
  return items.map((item) => JSON.parse(JSON.stringify({ ...item, id: newId() })) as ResumeItem);
}

function cloneEntryWithNewIds(entry: ResumeEntry): ResumeEntry {
  return {
    ...JSON.parse(JSON.stringify(entry)),
    id: newId(),
    items: cloneItemsWithNewIds(entry.items),
  } as ResumeEntry;
}

/** 按 key 找板块；找不到时用源板块的骨架补一个空板块（自建板块/可选板块首次填入）。 */
function ensureSection(
  document: ResumeDocument,
  source: ResumeSection,
  sectionOrder: readonly string[] = [],
): ResumeDocument {
  if (document.sections.some((section) => section.key === source.key)) return document;
  const newSection = {
    key: source.key,
    title: source.title,
    kind: source.kind,
    layout: JSON.parse(JSON.stringify(source.layout)),
    entries: [],
  } as ResumeSection;
  const order = new Map(sectionOrder.map((key, index) => [key, index]));
  const targetIndex = order.get(source.key);
  let insertAt = document.sections.length;
  if (targetIndex !== undefined) {
    const found = document.sections.findIndex((section) => {
      const index = order.get(section.key);
      return index !== undefined && index > targetIndex;
    });
    if (found >= 0) insertAt = found;
  }
  const sections = [...document.sections];
  sections.splice(insertAt, 0, newSection);
  return { ...document, sections };
}

export interface MergeProjectionCandidateResult {
  document: ResumeDocument;
  /** 实际补入/补空的 item 数量（0 = 没有可填的，宿主据此不写历史）。 */
  filled: number;
  /** 是否补入了「仅素材」字段（hidden + source），宿主据此提示"不上纸面"。 */
  materialOnly: boolean;
}

/**
 * 把一条已解析候选合并进当前文档（**只做加法**）：
 *
 * - 目标板块不存在 → 用源板块骨架补板块，并把整条来源条目作为新条目追加；
 * - 目标板块存在但该条没有条目 → 追加克隆条目；
 * - 否则填充**同一位置的条目**（源条目在来源板块里的下标；越界退回第一条）：
 *   - field/list/authors：同 key 且当前为空 → 用来源值补齐；缺失的 item 按 source 去重后追加；
 *   - text：目标条目还没有文本块时才追加（避免覆盖用户手写正文）；
 * - 全部 item 深拷贝并换新 id，不改来源投影、也不改入参文档。
 */
export function mergeProjectionCandidate(
  document: ResumeDocument,
  resolved: ResolvedProjectionCandidate,
  sectionOrder: readonly string[] = [],
): MergeProjectionCandidateResult {
  const withSection = ensureSection(document, resolved.section, sectionOrder);
  const targetSection = withSection.sections.find((section) => section.key === resolved.sectionKey);
  if (!targetSection) return { document, filled: 0, materialOnly: false };

  const incoming = cloneItemsWithNewIds(resolved.items);
  const nonText = incoming.filter((item) => item.kind !== "text");
  const texts = incoming.filter((item) => item.kind === "text");
  const sourceIndex = resolved.section.entries.findIndex((entry) => entry.id === resolved.entry.id);
  const targetEntry = targetSection.entries[Math.max(0, sourceIndex)] ?? targetSection.entries[0];

  if (!targetEntry) {
    const entry = cloneEntryWithNewIds(resolved.entry);
    const sections = withSection.sections.map((section) =>
      section.key === resolved.sectionKey
        ? { ...section, entries: [...section.entries, entry] }
        : section,
    );
    return {
      document: { ...withSection, sections },
      filled: entry.items.length,
      materialOnly: entry.items.some(
        (item) => item.kind === "field" && item.placement === "hidden" && item.source !== null,
      ),
    };
  }

  const existingSources = new Set(
    targetEntry.items.map(itemSourceKey).filter((key): key is string => key !== null),
  );
  const pending = nonText.filter((item) => {
    const key = itemSourceKey(item);
    return key === null || !existingSources.has(key);
  });
  const merged = mergeProfileItems(targetEntry.items, pending);
  const hasText = merged.items.some((item) => item.kind === "text");
  const items = hasText ? merged.items : [...merged.items, ...texts];
  const filled = merged.filled + (hasText ? 0 : texts.length);
  const sections = withSection.sections.map((section) =>
    section.key !== resolved.sectionKey
      ? section
      : {
          ...section,
          entries: section.entries.map((entry) =>
            entry.id === targetEntry.id ? { ...entry, items } : entry,
          ),
        },
  );
  const materialOnly = pending.some(
    (item) => item.kind === "field" && item.placement === "hidden" && item.source !== null,
  );
  return { document: { ...withSection, sections }, filled, materialOnly };
}

/**
 * 把候选**按身份**合进当前文档：同一条目就补缺，没写过才追加。
 *
 * 与 `mergeProjectionCandidate` 的差别：后者按"源条目下标"找目标条目（整条新增场景
 * 成立），但覆盖清单里的「项目 X 的项目亮点」是**条目已存在、只缺几个要点**——
 * 按下标合并会把内容塞进别的条目，按板块追加又会造出重复项目。这里先按身份字段
 * （项目名 / 公司 / 学校 / 技能名…）找同一条目：
 * - 找到 → 字段补空、列表取并集、缺失的正文补充，已有的一个字都不动；
 * - 找不到 → 才追加克隆条目。
 */
export function fillProjectionCandidate(
  document: ResumeDocument,
  resolved: ResolvedProjectionCandidate,
  sectionOrder: readonly string[] = [],
): MergeProjectionCandidateResult {
  const withSection = ensureSection(document, resolved.section, sectionOrder);
  const section = withSection.sections.find((item) => item.key === resolved.sectionKey);
  if (!section) return { document, filled: 0, materialOnly: false };

  // 个人总结这类「一段文本」板块：用资料原文替换当前段落，而不是再叠一段。
  if (section.kind === "text") {
    const source = resolved.items.find((item) => item.kind === "text");
    if (!source || source.kind !== "text" || !source.text.trim()) {
      return { document, filled: 0, materialOnly: false };
    }
    const entry = section.entries[0];
    if (!entry) {
      const nextEntry = cloneEntryWithNewIds({ ...resolved.entry, items: [source] });
      return {
        document: replaceSectionEntries(withSection, section.key, [nextEntry]),
        filled: 1,
        materialOnly: false,
      };
    }
    const textIndex = entry.items.findIndex((item) => item.kind === "text");
    if (textIndex < 0) {
      return {
        document: replaceSectionEntries(withSection, section.key, [
          { ...entry, items: [...entry.items, { ...source, id: newId() }] },
        ]),
        filled: 1,
        materialOnly: false,
      };
    }
    const current = entry.items[textIndex];
    if (current.kind === "text" && normalizeForCompare(current.text) === normalizeForCompare(source.text)) {
      return { document, filled: 0, materialOnly: false };
    }
    const items = entry.items.map((item, index) =>
      index === textIndex ? { ...source, id: item.id } : item,
    );
    return {
      document: replaceSectionEntries(
        withSection,
        section.key,
        section.entries.map((item) => (item.id === entry.id ? { ...item, items } : item)),
      ),
      filled: 1,
      materialOnly: false,
    };
  }

  const identity = entryIdentity(resolved.entry);
  const target = identity
    ? section.entries.find((entry) => entryIdentity(entry)?.value === identity.value)
    : undefined;
  if (!target) {
    const entry = cloneEntryWithNewIds(resolved.entry);
    return {
      document: replaceSectionEntries(withSection, section.key, [...section.entries, entry]),
      filled: entry.items.length,
      materialOnly: entry.items.some(
        (item) => item.kind === "field" && item.placement === "hidden" && item.source !== null,
      ),
    };
  }

  const merged = mergeMissingEntryItems(target.items, resolved.items);
  if (merged.filled === 0) return { document, filled: 0, materialOnly: false };
  return {
    document: replaceSectionEntries(
      withSection,
      section.key,
      section.entries.map((entry) =>
        entry.id === target.id ? { ...entry, items: merged.items } : entry,
      ),
    ),
    filled: merged.filled,
    materialOnly: false,
  };
}

const ENTRY_IDENTITY_KEYS = ["name", "company", "school", "organization", "title"] as const;

function normalizeForCompare(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, "").toLowerCase();
}

/** 条目的身份（项目名 / 公司 / 学校 / 技能名…）：用于判断"是不是同一条"。 */
function entryIdentity(entry: ResumeEntry): { key: string; value: string } | null {
  for (const key of ENTRY_IDENTITY_KEYS) {
    const item = entry.items.find((candidate) => candidate.kind === "field" && candidate.key === key);
    if (item?.kind !== "field") continue;
    const value = normalizeForCompare(item.value);
    if (value) return { key, value };
  }
  return null;
}

function cloneItemWithNewId(item: ResumeItem): ResumeItem {
  return { ...JSON.parse(JSON.stringify(item)), id: newId() } as ResumeItem;
}

function replaceSectionEntries(
  document: ResumeDocument,
  sectionKey: string,
  entries: ResumeEntry[],
): ResumeDocument {
  return {
    ...document,
    sections: document.sections.map((section) =>
      section.key === sectionKey ? { ...section, entries } : section,
    ),
  };
}

/** 只补充目标条目**还没有**的 item：字段补空、列表并集、正文按文本去重追加。 */
function mergeMissingEntryItems(
  current: readonly ResumeItem[],
  incoming: readonly ResumeItem[],
): { items: ResumeItem[]; filled: number } {
  const items = current.map((item) => ({ ...item }) as ResumeItem);
  let filled = 0;

  for (const item of incoming) {
    if (item.kind === "text") continue;
    const index = items.findIndex(
      (existing) => existing.kind === item.kind && existing.key === item.key,
    );
    if (index < 0) {
      items.push(cloneItemWithNewId(item));
      filled += 1;
      continue;
    }
    const existing = items[index];
    if (item.kind === "list" && existing.kind === "list") {
      const values = [...(existing.values ?? [])];
      const seen = new Set(values.map(normalizeForCompare));
      let added = 0;
      for (const value of item.values ?? []) {
        const key = normalizeForCompare(value);
        if (!key || seen.has(key)) continue;
        values.push(value);
        seen.add(key);
        added += 1;
      }
      if (added > 0) {
        items[index] = { ...existing, values };
        filled += added;
      }
    } else if (item.kind === "field" && existing.kind === "field") {
      if (String(existing.value ?? "").trim()) continue;
      items[index] = cloneItemWithNewId(item);
      filled += 1;
    }
  }

  const seenTexts = new Set(
    items.flatMap((item) => (item.kind === "text" ? [normalizeForCompare(item.text)] : [])),
  );
  for (const item of incoming) {
    if (item.kind !== "text") continue;
    const key = normalizeForCompare(item.text);
    if (!key || seenTexts.has(key)) continue;
    items.push(cloneItemWithNewId(item));
    seenTexts.add(key);
    filled += 1;
  }
  return { items, filled };
}

/**
 * 「这些资料没写进简历」→ 确定性补齐（覆盖清单的「从资料补上这段」唯一实现）。
 *
 * 名字可能是：整条身份名（项目/公司/学校/技能）、条目里的某段正文（项目亮点）、
 * 或"个人总结"这种描述。分别按身份、正文包含、板块类型匹配候选；同一候选被多个
 * 名字命中也只合并一次（重复调用是幂等的）。
 */
export function fillCoverageNote(
  document: ResumeDocument,
  projection: PaperProjectionOut | null | undefined,
  note: { section: string; names: string[] },
  sectionOrder: readonly string[] = [],
): MergeProjectionCandidateResult {
  const candidates = resolvableProjectionCandidates(projection);
  let next = document;
  let filled = 0;
  for (const name of note.names) {
    const key = normalizeForCompare(name);
    if (!key) continue;
    // 不做全文子串过滤：像「C++」这种短技能可能恰好出现在别的正文里，跳过会把真正
    // 缺失的条目漏掉。合并本身按身份/文本去重，重复调用是幂等的。
    // 个人总结在投影里没有 v2 条目路径（后端候选不带 document_entry），直接从投影
    // 的 summary 板块取原文替换当前段落——否则这个名字永远匹配不到候选。
    if (note.section === "summary") {
      const sourceSection = projectionDocument(projection)?.sections.find(
        (section) => section.key === "summary",
      );
      const source = sourceSection?.entries
        .flatMap((entry) => entry.items)
        .find((item) => item.kind === "text" && item.text.trim());
      if (source?.kind !== "text") continue;
      const currentSection = next.sections.find((section) => section.key === "summary");
      if (!currentSection) continue;
      const entry = currentSection.entries[0];
      if (!entry) continue;
      const index = entry.items.findIndex((item) => item.kind === "text");
      if (index < 0) continue;
      const current = entry.items[index];
      if (current.kind === "text" && normalizeForCompare(current.text) === normalizeForCompare(source.text)) {
        continue;
      }
      const items = entry.items.map((item, itemIndex) =>
        itemIndex === index ? { ...source, id: item.id } : item,
      );
      next = replaceSectionEntries(
        next,
        "summary",
        currentSection.entries.map((item) => (item.id === entry.id ? { ...item, items } : item)),
      );
      filled += 1;
      continue;
    }
    const resolved = candidates.find((item) => candidateMatchesName(item, key));
    if (!resolved) continue;
    const result = fillProjectionCandidate(next, resolved, sectionOrder);
    if (result.filled > 0) {
      next = result.document;
      filled += result.filled;
    }
  }
  return { document: next, filled, materialOnly: false };
}

function candidateMatchesName(resolved: ResolvedProjectionCandidate, key: string): boolean {
  const identity = entryIdentity(resolved.entry);
  if (identity && identity.value === key) return true;
  if (normalizeForCompare(resolved.candidate.title) === key) return true;
  return resolved.entry.items.some((item) => {
    if (item.kind === "text") return normalizeForCompare(item.text) === key;
    if (item.kind === "field") return normalizeForCompare(item.value) === key;
    if (item.kind === "list") return item.values.some((value) => normalizeForCompare(value) === key);
    return false;
  });
}

/**
 * 把候选作为**新条目**追加到对应板块（不合并到现有第一条）。
 *
 * 覆盖清单里的项目/实习是"整条没写进简历"，用 mergeProjectionCandidate 会错误地把
 * 内容填进现有第一条；这里克隆来源条目、换新 id 后追加，板块不存在时先补骨架。
 */
export function appendProjectionEntry(
  document: ResumeDocument,
  resolved: ResolvedProjectionCandidate,
  sectionOrder: readonly string[] = [],
): MergeProjectionCandidateResult {
  const withSection = ensureSection(document, resolved.section, sectionOrder);
  const entry = cloneEntryWithNewIds(resolved.entry);
  const sections = withSection.sections.map((section) =>
    section.key === resolved.sectionKey
      ? { ...section, entries: [...section.entries, entry] }
      : section,
  );
  return {
    document: { ...withSection, sections },
    filled: entry.items.length,
    materialOnly: entry.items.some(
      (item) => item.kind === "field" && item.placement === "hidden" && item.source !== null,
    ),
  };
}

/** 一步到位：解析 + 合并；候选解析不到返回 null。 */
export function applyProjectionCandidate(
  document: ResumeDocument,
  projection: PaperProjectionOut | null | undefined,
  candidate: ProjectionCandidateOut,
): MergeProjectionCandidateResult | null {
  const resolved = resolveProjectionCandidate(projection, candidate);
  if (!resolved) return null;
  return mergeProjectionCandidate(document, resolved);
}
