// SPDX-License-Identifier: Apache-2.0
/** 公司名 → 风鸟链接。 */
import { describe, expect, it } from "vitest";

import { companyLookupName, riskbirdUrl } from "./companyLookup";

describe("riskbirdUrl", () => {
  it("工商全名生成公司详情页链接", () => {
    // URL 格式是实测确认的：ent/{全名}.html，不需要 entid。
    const name = "广州示例传媒科技有限公司";
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

  it("太短的品牌名不给链接", () => {
    // 风鸟按工商全名索引，两个字基本查不到。
    expect(riskbirdUrl("示例")).toBeNull();
    expect(riskbirdUrl("")).toBeNull();
    expect(riskbirdUrl(null)).toBeNull();
  });
});

describe("companyLookupName", () => {
  it("返回清理过的名字或 null", () => {
    expect(companyLookupName("  广州示例传媒科技有限公司  ")).toBe("广州示例传媒科技有限公司");
    expect(companyLookupName("示例")).toBeNull();
  });
});
