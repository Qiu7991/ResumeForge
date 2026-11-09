// SPDX-License-Identifier: Apache-2.0
/** v2「显示板块」：隐藏只写 section.hidden，不改正文数据。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeResumeDocument } from "../../test/documentHarness";
import { t } from "../../i18n";
import SectionVisibilityPanel from "./SectionVisibilityPanel";

afterEach(cleanup);

describe("SectionVisibilityPanel", () => {
  it("点隐藏只把 section.hidden 置真，内容仍保留", () => {
    const document = makeResumeDocument();
    const onChange = vi.fn();
    render(
      <AntdApp>
        <SectionVisibilityPanel document={document} onChange={onChange} />
      </AntdApp>,
    );

    const button = screen.getByRole("button", {
      name: t("workbench.sectionsVisibility.hide", { label: "专业技能" }),
    });
    fireEvent.click(button);

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0];
    const skills = next.sections.find((section: { key: string }) => section.key === "skills");
    expect(skills.hidden).toBe(true);
    expect(skills.entries.length).toBe(
      document.sections.find((section) => section.key === "skills")?.entries.length,
    );
  });
});
