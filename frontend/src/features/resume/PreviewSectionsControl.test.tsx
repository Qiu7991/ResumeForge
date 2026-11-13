// SPDX-License-Identifier: Apache-2.0
/** 预览里的「板块」快捷控制：隐藏与排序都回写 v2 document.sections。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeResumeDocument } from "../../test/documentHarness";
import { t } from "../../i18n";
import PreviewSectionsControl from "./PreviewSectionsControl";

afterEach(cleanup);

describe("PreviewSectionsControl", () => {
  it("隐藏专业技能并保持正文数据", async () => {
    const document = makeResumeDocument();
    const onApply = vi.fn();
    render(
      <AntdApp>
        <PreviewSectionsControl document={document} onApply={onApply} />
      </AntdApp>,
    );

    fireEvent.click(screen.getByRole("button", { name: t("workbench.sectionsVisibility.trigger") }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: t("workbench.sectionsVisibility.hide", { label: "专业技能" }),
      }),
    );

    expect(onApply).toHaveBeenCalledTimes(1);
    const next = onApply.mock.calls[0][0];
    const skills = next.sections.find((section: { key: string }) => section.key === "skills");
    expect(skills.hidden).toBe(true);
    expect(skills.entries.length).toBeGreaterThan(0);
  });
});
