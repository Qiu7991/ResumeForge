// SPDX-License-Identifier: Apache-2.0
/**
 * 公司名 → 风鸟（riskbird.com）查询链接。
 *
 * ## URL 格式是实测确认的，不需要 entid
 *
 * ```
 * https://www.riskbird.com/ent/{工商全名}.html
 * ```
 *
 * 实测：访问 `https://www.riskbird.com/ent/广州示例传媒科技有限公司.html` 会 302 到
 * `/auth/login?redirect=/ent/广州示例传媒科技有限公司.html`——**登录后会跳回目标公司页**。
 * 所以第一次点会要求微信扫码登录一次，之后 cookie 在浏览器里就不再问了。
 *
 * ## 为什么必须用**工商全名**
 *
 * BOSS 列表页给的是品牌短名（`示例传媒`）或自己截断的串（`广州市示例国际贸...`）。
 * 风鸟按工商全名索引：`示例传媒` 查不到，`广州示例传媒科技有限公司` 才行。
 * 全名要靠补抓详情页的「工商信息」——见后端 `services/job_hunt/company_name.py`。
 *
 * ## 截断名不给链接
 *
 * `广州市示例国际贸...` 去掉三点是 `广州市示例国际贸`，风鸟照样查不到。
 * 给一个必然失败的链接比不给更差——用户会以为「这个功能坏了」。所以返回 null，
 * 界面上把公司名渲染成纯文本并提示「公司名被招聘网站截断，补抓详情后可得全名」。
 */

/** 风鸟公司详情页的路径前缀。 */
const RISKBIRD_ENT_BASE = "https://www.riskbird.com/ent/";

/**
 * 详情页里被误当成公司名的界面文本。
 *
 * **这些中文是协议值**，必须与后端 `services/job_hunt/company_name.py` 的 `_UI_NOISE`
 * 逐字一致——两边不一致时，后端认为是噪声的名字前端却当成公司名，会给一个必然查不到的链接。
 */
// i18n-ok: 与后端 _UI_NOISE 逐字对应的协议值
const UI_NOISE = new Set(["公司", "企业", "查看", "更多", "详情", "首页", "招聘", "工商信息"]);

/**
 * 这个名字能否用来查风鸟。返回清理后的名字，不适合则 null。
 *
 * 判定与后端 `looks_like_company_name` 保持同向：非空、不是界面噪声、不是截断名。
 */
export function companyLookupName(raw: string | null | undefined): string | null {
  const name = (raw ?? "").trim();
  if (!name) return null;
  if (UI_NOISE.has(name)) return null;
  // 截断名（尾随 ASCII 三点或省略号）：去掉标记也只是残名，查不到。
  if (/\.\.\.$|…$/.test(name)) return null;
  // 太短的是品牌碎片或解析错误（风鸟按全名索引，2 个字基本查不到）。
  if (name.length < 4) return null;
  return name;
}

/**
 * 生成风鸟公司详情页链接；名字不适合查询时返回 `null`。
 *
 * 用 `encodeURIComponent` 而不是直接拼接：公司名里常有括号（`（广州）`）、
 * 顿号、空格，裸拼会让 URL 断在第一个特殊字符上。
 */
export function riskbirdUrl(raw: string | null | undefined): string | null {
  const name = companyLookupName(raw);
  if (name === null) return null;
  return `${RISKBIRD_ENT_BASE}${encodeURIComponent(name)}.html`;
}
