// SPDX-License-Identifier: Apache-2.0
/**
 * 公司名 → 风鸟（riskbird.com）查询链接。
 *
 * ## 两条官方 URL（均由风鸟前端路由实测确认）
 *
 * 1. **工商全名**（以有限公司 / 股份有限公司 / 合伙企业 / 事务所 / 研究院等法定后缀结尾）：
 *    ```
 *    https://www.riskbird.com/ent/{工商全名}.html
 *    ```
 *    直达公司工商注册详情页（无需 entid；首次会经登录回调跳回目标页）。
 *
 * 2. **品牌短名**（如 `示例品牌`、`示例科技`、`示例`）：
 *    ```
 *    https://www.riskbird.com/search/company?keyword={品牌短名}
 *    ```
 *    `/ent/` 只按精准工商全名索引，传短名会落到空白页；走官方「查公司」搜索路由
 *    （来自风鸟前端 `searchHooks`: `/search/company?keyword=...`）可直接列出候选企业。
 *
 * ## 截断名不给链接
 *
 * `广州市示例国际贸...` 去掉三点仍是残串，先提示用户补抓详情后再查。
 */

/** 风鸟公司精准详情页路径前缀（仅工商全名使用）。 */
const RISKBIRD_ENT_BASE = "https://www.riskbird.com/ent/";
/** 风鸟「查公司」搜索页路径前缀（品牌短名兜底使用）。 */
const RISKBIRD_SEARCH_BASE = "https://www.riskbird.com/search/company?keyword=";

/**
 * 中国工商/组织注册全名的常见法定后缀（允许尾部带地区/类型括号，如 `（有限合伙）`）。
 * 品牌短名如 `示例品牌`、`示例公司`、`广州示例科技` 不命中此正则，改走搜索页。
 */
// i18n-ok: 中国工商注册主体名称法定后缀正则，属领域协议匹配非界面文案
const LEGAL_ENTITY_SUFFIX_RE =
  /(?:有限公司|有限责任公司|股份有限公司|集团有限公司|分公司|总公司|集团公司|合伙企业|有限合伙|事务所|研究院|研究所|设计院|医院|银行|信用社|合作社|营业部|办事处)(?:[（(][^）)]{1,16}[）)])?$/;

/**
 * 详情页里被误当成公司名的界面文本。
 *
 * **这些中文是协议值**，必须与后端 `services/job_hunt/company_name.py` 的 `_UI_NOISE`
 * 逐字一致——两边不一致时，后端认为是噪声的名字前端却当成公司名，会给一个必然查不到的链接。
 */
// i18n-ok: 与后端 _UI_NOISE 逐字对应的协议值
const UI_NOISE = new Set(["公司", "企业", "查看", "更多", "详情", "首页", "招聘", "工商信息"]);

/** 判断名字是否像完整的工商注册全名（决定走直达 `/ent/` 还是搜索 `/search/company`）。 */
export function isFullCompanyName(raw: string | null | undefined): boolean {
  const name = (raw ?? "").trim();
  if (name.length < 5) return false;
  if (/\.\.\.$|…$/.test(name)) return false;
  return LEGAL_ENTITY_SUFFIX_RE.test(name);
}

/**
 * 这个名字能否用来查风鸟。返回清理后的名字，不适合则 null。
 *
 * 判定与后端 `looks_like_company_name` 保持同向：非空、不是界面噪声、不是截断名、至少 2 字。
 */
export function companyLookupName(raw: string | null | undefined): string | null {
  const name = (raw ?? "").trim();
  if (!name) return null;
  if (UI_NOISE.has(name)) return null;
  // 截断名（尾随 ASCII 三点或省略号）：去掉标记也只是残名，查不到。
  if (/\.\.\.$|…$/.test(name)) return null;
  // 单字多为解析碎片；2 字及以上品牌名（如「示例」）可走搜索页。
  if (name.length < 2) return null;
  return name;
}

/**
 * 生成风鸟查询链接；名字不适合查询时返回 `null`。
 *
 * - 工商全名 → `/ent/{encodeURIComponent(name)}.html`（直达企业详情）
 * - 品牌短名 → `/search/company?keyword={encodeURIComponent(name)}`（避免 `/ent/` 落空白页）
 */
export function riskbirdUrl(raw: string | null | undefined): string | null {
  const name = companyLookupName(raw);
  if (name === null) return null;
  if (isFullCompanyName(name)) {
    return `${RISKBIRD_ENT_BASE}${encodeURIComponent(name)}.html`;
  }
  return `${RISKBIRD_SEARCH_BASE}${encodeURIComponent(name)}`;
}
