// SPDX-License-Identifier: Apache-2.0
/** StatusBadge：状态标签 + 非 BOSS 平台只读标识（P2-7）。 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import StatusBadge from "./StatusBadge";

afterEach(() => cleanup());

describe("StatusBadge", () => {
  it("maps engine statuses to labels", () => {
    render(<StatusBadge job={{ status: "ready", source_platform: "boss" }} />);
    expect(screen.getByText("待确认")).toBeTruthy();
  });

  it("marks read-only platforms per backend-derived flag", () => {
    render(<StatusBadge job={{ status: "scored", source_platform: "zhilian", platform_read_only: true }} />);
    expect(screen.getByText("已评分")).toBeTruthy();
    expect(screen.getByText(/只读平台/)).toBeTruthy();
  });

  it("does not mark BOSS as read-only", () => {
    render(<StatusBadge job={{ status: "sent", source_platform: "boss", platform_read_only: false }} />);
    expect(screen.queryByText(/只读平台/)).toBeNull();
  });

  it("unknown status falls back to the generic label", () => {
    render(<StatusBadge job={{ status: "mystery", source_platform: "boss" }} />);
    expect(screen.getByText("其他状态")).toBeTruthy();
  });
});
