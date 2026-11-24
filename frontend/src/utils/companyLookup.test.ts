// SPDX-License-Identifier: Apache-2.0
/** 公司名 → 风鸟链接（工商全名直达详情页，品牌短名走搜索页）。 */
import { describe, expect, it } from "vitest";

import { companyLookupName, isFullCompanyName, riskbirdUrl } from "./companyLookup";

describe("riskbirdUrl", () => {
  it("工商全名生成公司详情页链接", () => {
    // URL 格式是实测确认的：ent/{全名}.html，不需要 entid。
    const name = "广州示例传媒科技有限公司";
    expect(isFullCompanyName(name)).toBe(true);
    expect(riskbirdUrl(name)).toBe(
      `https://www.riskbird.com/ent/${encodeURIComponent(name)}.html`,
    );
  });

  it("括号等特殊字符被正确编码", () => {
    // 公司名里常有全角括号，裸拼会让 URL 断在第一个特殊字符上。
    const url = riskbirdUrl("示例网络科技（广州）有限公司");
    expect(url).not.toBeNull();
    expect(url).toContain("%EF%BC%88"); // （ 的 UTF-8 编码
    expect(url).toContain(".html");
  });

  it("品牌短名走风鸟「查公司」搜索页，避免 /ent/ 落空白页", () => {
    for (const shortName of ["示例品牌", "示例科技", "示例公司", "示例电商科技", "示例"]) {
      expect(isFullCompanyName(shortName)).toBe(false);
      expect(riskbirdUrl(shortName)).toBe(
        `https://www.riskbird.com/search/company?keyword=${encodeURIComponent(shortName)}`,
      );
    }
  });

  it("截断名不给链接", () => {
    // `广州市示例国际贸...` 去掉三点是 `广州市示例国际贸`，风鸟照样查不到。
    // 给一个必然失败的链接比不给更差——用户会以为功能坏了。
    expect(riskbirdUrl("广州市示例国际贸...")).toBeNull();
    expect(riskbirdUrl("广州市示例国际贸…")).toBeNull();
  });

  it("界面噪声文本不给链接", () => {
    // 后端解析详情页时可能命中导航菜单「公司」。
    expect(riskbirdUrl("公司")).toBeNull();
    expect(riskbirdUrl("查看")).toBeNull();
  });

  it("空串或单字碎片不给链接", () => {
    expect(riskbirdUrl("a")).toBeNull();
    expect(riskbirdUrl("")).toBeNull();
    expect(riskbirdUrl(null)).toBeNull();
  });
});

describe("companyLookupName", () => {
  it("返回清理过的名字或 null", () => {
    expect(companyLookupName("  广州示例传媒科技有限公司  ")).toBe("广州示例传媒科技有限公司");
    expect(companyLookupName("  示例  ")).toBe("示例");
    expect(companyLookupName("x")).toBeNull();
  });
});
