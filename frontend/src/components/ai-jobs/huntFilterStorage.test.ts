// SPDX-License-Identifier: Apache-2.0
/**
 * 采集条件持久化：归一化必须挡住一切脏输入。
 *
 * 这些函数是 localStorage 的**唯一防线**。存进去的东西可能来自旧版本形状、用户手改、
 * 或另一个标签页写的一半数据；而使用处写的是 `filters.experience.map(...)`、
 * `keywords.slice(...)`——校验漏一处就白屏。所以每条规则都单独钉一遍。
 */
import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, DEFAULT_KEYWORDS, FILTER_OPTIONS } from "./HuntFilterForm";
import {
  MAX_PAGES_LIMT,
  normalizeBoolean,
  normalizeCity,
  normalizeFilters,
  normalizeKeywords,
  normalizeMaxPages,
  normalizeSalary,
  normalizeSiteKey,
} from "./huntFilterStorage";

describe("normalizeKeywords", () => {
  it("去空、去重、保序", () => {
    expect(normalizeKeywords(["  AI ", "AI", "", "大模型", null, 42])).toEqual(["AI", "大模型"]);
  });

  it("全空时回退出厂默认，而不是给一个空搜索框", () => {
    expect(normalizeKeywords([])).toEqual(DEFAULT_KEYWORDS);
    expect(normalizeKeywords(["", "  "])).toEqual(DEFAULT_KEYWORDS);
  });

  it("不是数组（旧版字符串形状）也回退默认", () => {
    expect(normalizeKeywords("AI")).toEqual(DEFAULT_KEYWORDS);
    expect(normalizeKeywords(null)).toEqual(DEFAULT_KEYWORDS);
  });
});

describe("normalizeFilters", () => {
  it("只保留当前选项里仍然合法的协议值", () => {
    const result = normalizeFilters({
      experience: ["应届生", "已下线的档位"],
      degree: ["本科"],
    });
    expect(result.experience).toEqual(["应届生"]);
    expect(result.degree).toEqual(["本科"]);
  });

  it("整组失效时删掉该组，而不是保留空数组（空数组语义是「显式不限」）", () => {
    const result = normalizeFilters({ experience: ["不存在的档位"], degree: ["本科"] });
    expect("experience" in result).toBe(false);
    expect(result.degree).toEqual(["本科"]);
  });

  it("全部失效或输入不是对象时回退出厂条件", () => {
    expect(normalizeFilters({ experience: ["x"] })).toEqual(DEFAULT_FILTERS);
    expect(normalizeFilters(null)).toEqual(DEFAULT_FILTERS);
    expect(normalizeFilters(["应届生"])).toEqual(DEFAULT_FILTERS);
  });

  it("不认识的分组键被丢掉（旧版本的组名不该混进请求）", () => {
    const result = normalizeFilters({ 已废弃的组: ["值"], degree: ["本科"] });
    expect(Object.keys(result)).toEqual(["degree"]);
  });

  it("厂默认里的每个值都在当前选项表里（否则默认值自己就是脏值）", () => {
    for (const [group, values] of Object.entries(DEFAULT_FILTERS)) {
      for (const value of values) {
        expect(FILTER_OPTIONS[group]).toContain(value);
      }
    }
  });
});

describe("normalizeSalary", () => {
  it("正常区间原样保留", () => {
    expect(normalizeSalary({ min: 8, max: 12 })).toEqual({ min: 8, max: 12 });
  });

  it("反了就交换，而不是丢掉——用户手改的意图明确", () => {
    expect(normalizeSalary({ min: 20, max: 8 })).toEqual({ min: 8, max: 20 });
  });

  it("缺一边时另一边保留（单边区间是合法的）", () => {
    expect(normalizeSalary({ min: 8 })).toEqual({ min: 8, max: 0 });
  });

  it("非数字与负数归零，超大值夹到 200", () => {
    expect(normalizeSalary({ min: "abc", max: -5 })).toEqual({ min: 0, max: 0 });
    expect(normalizeSalary({ min: 9999 })).toEqual({ min: 200, max: 0 });
  });

  it("null / 非对象回退不限", () => {
    expect(normalizeSalary(null)).toEqual({ min: 0, max: 0 });
  });
});

describe("normalizeCity", () => {
  it("非空字符串去掉首尾空格", () => {
    expect(normalizeCity("  深圳 ", "广州")).toBe("深圳");
  });

  it("空串与非字符串回退默认", () => {
    expect(normalizeCity("   ", "广州")).toBe("广州");
    expect(normalizeCity(123, "广州")).toBe("广州");
  });
});

describe("normalizeMaxPages", () => {
  it("夹到 1..上限之间", () => {
    expect(normalizeMaxPages(3)).toBe(3);
    expect(normalizeMaxPages(0)).toBe(1);
    expect(normalizeMaxPages(999)).toBe(MAX_PAGES_LIMT);
  });

  it("非数字回退 1", () => {
    expect(normalizeMaxPages("abc")).toBe(1);
  });
});

describe("normalizeBoolean / normalizeSiteKey", () => {
  it("只认真正的布尔，其余回退", () => {
    expect(normalizeBoolean(false, true)).toBe(false);
    expect(normalizeBoolean("false", true)).toBe(true);
  });

  it("站点键为空时回退", () => {
    expect(normalizeSiteKey("zhilian", "boss")).toBe("zhilian");
    expect(normalizeSiteKey("  ", "boss")).toBe("boss");
  });
});
