// SPDX-License-Identifier: Apache-2.0
/**
 * AI 求职采集条件的持久化（localStorage）。
 *
 * ## 为什么要把归一化和存储单独放一层
 *
 * 存进 localStorage 的东西会被三种东西改坏：旧版本的形状、用户手改、另一个标签页
 * 写进来的半截数据。而渲染处写的是 `filters.experience.map(...)`、`keywords.slice(0, 3)`
 * ——脏值直接白屏。所以**读取路径必须过一遍归一化**，而且这个责任不能摊到每个
 * 使用点：摊开之后必然有一处忘记校验，而那一处就是崩的那个。
 *
 * ## 为什么要校验协议值而不是照单全收
 *
 * `experience` 这些是**协议值**（后端折成站点编码，见 `HuntFilterForm.FILTER_OPTIONS`）。
 * 存进去的旧值可能已经不在当前选项里（比如我们以后收窄了经验档），原样回填会让
 * Select 显示一个选不中任何选项的空标签，用户既看不懂也删不掉。所以回填时只保留
 * 仍然合法的项；全都不合法就回退到出厂默认。
 */
import { DEFAULT_FILTERS, DEFAULT_KEYWORDS, FILTER_OPTIONS } from "../../components/ai-jobs/HuntFilterForm";

/** 存储键前缀。按字段分开存，改一个字段不需要读整包（也便于手工排查）。 */
const PREFIX = "rf.aiJobs.hunt";

export const HUNT_STORAGE_KEYS = {
  keywords: `${PREFIX}.keywords`,
  filters: `${PREFIX}.filters`,
  newestFirst: `${PREFIX}.newestFirst`,
  salary: `${PREFIX}.salary`,
  city: `${PREFIX}.city`,
  maxPages: `${PREFIX}.maxPages`,
  siteKey: `${PREFIX}.siteKey`,
  autoScore: `${PREFIX}.autoScore`,
};

/** 翻页数上限：与表单里的「最多 N 页」选项保持一致（1/2/3/4）。 */
export const MAX_PAGES_LIMT = 4;

/** 关键词：去空、去重、保序；全空则回退出厂默认（别让用户面对一个空搜索框）。 */
export function normalizeKeywords(raw: unknown): string[] {
  if (!Array.isArray(raw)) return DEFAULT_KEYWORDS;
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const item of raw) {
    const word = typeof item === "string" ? item.trim() : "";
    if (!word || seen.has(word)) continue;
    seen.add(word);
    cleaned.push(word);
  }
  return cleaned.length ? cleaned : DEFAULT_KEYWORDS;
}

/**
 * 站点筛选项：只保留当前选项里仍然存在的协议值。
 *
 * 某一组全部失效时**不保留空数组**而是整组删掉——空数组在请求里等于「显式不限」，
 * 与"没设过"在语义上不同（后端 `resolve_search_filters` 会按组处理）。
 */
export function normalizeFilters(raw: unknown): Record<string, string[]> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return DEFAULT_FILTERS;
  const cleaned: Record<string, string[]> = {};
  for (const [group, allowed] of Object.entries(FILTER_OPTIONS)) {
    const value = (raw as Record<string, unknown>)[group];
    if (!Array.isArray(value)) continue;
    const picked: string[] = [];
    for (const item of value) {
      const code = typeof item === "string" ? item.trim() : "";
      if (code && allowed.includes(code) && !picked.includes(code)) picked.push(code);
    }
    if (picked.length) cleaned[group] = picked;
  }
  // 全都失效（比如选项表彻底改过）= 回到出厂条件，而不是"什么都不筛"。
  return Object.keys(cleaned).length ? cleaned : DEFAULT_FILTERS;
}

/** 薪资区间：两个非负整数，保证 min ≤ max（都为 0 表示不限）。 */
export function normalizeSalary(raw: unknown): { min: number; max: number } {
  const payload = (raw ?? {}) as { min?: unknown; max?: unknown };
  const toK = (value: unknown): number => {
    const parsed = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return 0;
    return Math.min(200, Math.round(parsed));
  };
  let min = toK(payload.min);
  let max = toK(payload.max);
  // 反了就交换，而不是丢掉——用户手改存成 20/8 时，意图明显是 8-20。
  if (min && max && min > max) [min, max] = [max, min];
  return { min, max };
}

/** 城市：非空字符串，否则回退出厂默认（默认值本身来自 i18n，由调用方传进来）。 */
export function normalizeCity(raw: unknown, fallback: string): string {
  if (typeof raw !== "string") return fallback;
  const city = raw.trim();
  return city || fallback;
}

/** 翻页数：1..MAX_PAGES_LIMT 的整数。 */
export function normalizeMaxPages(raw: unknown): number {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return 1;
  return Math.min(MAX_PAGES_LIMT, Math.max(1, Math.round(parsed)));
}

/** 布尔开关（最新优先 / 采集后自动评分）。只认真正的布尔，其余回退默认。 */
export function normalizeBoolean(raw: unknown, fallback: boolean): boolean {
  return typeof raw === "boolean" ? raw : fallback;
}

/** 平台：非空字符串，否则交给调用方给默认（默认值来自后端返回的平台清单）。 */
export function normalizeSiteKey(raw: unknown, fallback: string): string {
  if (typeof raw !== "string") return fallback;
  const key = raw.trim();
  return key || fallback;
}
