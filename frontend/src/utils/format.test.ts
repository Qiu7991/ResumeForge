// SPDX-License-Identifier: Apache-2.0
/** 时间格式：收录时间这类同分钟多条的数据要精确到秒。 */
import { describe, expect, it } from "vitest";
import { formatDateTime, formatDateTimeSeconds } from "./format";

describe("formatDateTimeSeconds", () => {
  it("保留秒，分钟版不保留", () => {
    const iso = "2026-11-01T12:00:55.123456";
    expect(formatDateTimeSeconds(iso)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:55$/);
    expect(formatDateTime(iso)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it("空值仍然是一个占位符", () => {
    expect(formatDateTimeSeconds(undefined)).toBe("-");
  });
});
