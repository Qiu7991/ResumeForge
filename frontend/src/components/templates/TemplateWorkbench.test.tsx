// SPDX-License-Identifier: Apache-2.0
/**
 * 工作台「版式」页：助手入口、自制版式的列表/删除，以及**自制模板下线**的钉子。
 *
 * 2026-11 的改造把「模板」卡片整块撤掉了（导入 HTML / 导入参考模板 / 复制为新模板 / 内置
 * 模板缩略图墙 / 自制模板列表），只留「版式」。撤掉的东西最容易悄悄回来——把一个被删的
 * import 加回去、或者从旧分支合并时带回来，界面上就又多出两个点了没反应的按钮。所以这里
 * 既钉"还在的"（版式、自制版式、找助手），也钉"不该再出现的"。
 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { t } from "../../i18n";
import { TEMPLATE_CATALOG } from "../../test/resumeFixtures";
import type { ResumeTemplateDetail } from "../../types";
import TemplateWorkbench from "./TemplateWorkbench";

// 只拦真正会发请求的两个模块：
// - `api/resumes` 提供内置版式目录；
// - `api/resumeTemplates` 提供自制版式列表（点击/删除/复制在内置目录测试里不需要）。
const resumeApiMocks = vi.hoisted(() => ({
  fetchResumeTemplates: vi.fn(),
  previewResumeTemplate: vi.fn(),
}));
vi.mock("../../api/resumes", () => resumeApiMocks);

const templateApiMocks = vi.hoisted(() => ({
  listResumeTemplates: vi.fn(),
  deleteResumeTemplate: vi.fn(),
  fetchBuiltinTemplateSource: vi.fn(),
}));
vi.mock("../../api/resumeTemplates", () => templateApiMocks);

function templateDetail(overrides: Partial<ResumeTemplateDetail>): ResumeTemplateDetail {
  return {
    id: 1,
    name: "模板",
    kind: "format",
    description: "",
    enabled: true,
    source_name: "",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    html: "",
    config: {},
    ...overrides,
  };
}

/** 路径 + 查询串探针，用来断言"点了之后去了哪"。 */
function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

function renderWorkbench() {
  return render(
    <MemoryRouter>
      <AntdApp>
        <TemplateWorkbench />
        <LocationProbe />
      </AntdApp>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  resumeApiMocks.fetchResumeTemplates.mockReset().mockResolvedValue(TEMPLATE_CATALOG);
  resumeApiMocks.previewResumeTemplate.mockReset().mockResolvedValue("<html></html>");
  templateApiMocks.listResumeTemplates.mockReset().mockResolvedValue([]);
  templateApiMocks.deleteResumeTemplate.mockReset();
  templateApiMocks.fetchBuiltinTemplateSource.mockReset();
});

afterEach(() => {
  cleanup();
  // antd 的 confirm holder 挂在 body 上：不清掉会让下一条用例的
  // `.ant-modal-confirm-title` 断言读到上一条的残留。
  document.body.innerHTML = "";
});

describe("TemplateWorkbench 的求职助手入口", () => {
  it("「找求职助手制作」跳转时带上编码后的预填提问", async () => {
    renderWorkbench();

    // 图标会贡献一个可访问名片段，所以按子串匹配按钮名。
    fireEvent.click(await screen.findByRole("button", { name: /找求职助手制作/ }));

    await waitFor(() =>
      expect(screen.getByTestId("location").textContent).toBe(
        `/assistant?ask=${encodeURIComponent("帮我新建一个版式：")}`,
      ),
    );
  });

  it("版式行提供「找助手改这个模板」，并带上模板名", async () => {
    templateApiMocks.listResumeTemplates.mockResolvedValue([
      templateDetail({ id: 7, name: "压页版式", kind: "format" }),
    ]);
    renderWorkbench();
    await screen.findByText("压页版式");

    fireEvent.click(screen.getAllByRole("button", { name: "更多操作" })[0]);
    fireEvent.click(await screen.findByText("找助手改这个模板"));

    await waitFor(() =>
      expect(screen.getByTestId("location").textContent).toBe(
        `/assistant?ask=${encodeURIComponent("帮我调整格式模板「压页版式」：")}`,
      ),
    );
  });
});

describe("TemplateWorkbench 保留自制模板后的现状", () => {
  it("样式与版式两张卡都在，自制模板入口可用", async () => {
    renderWorkbench();

    expect(await screen.findByText(t("templatesUi.workbench.style.title"))).toBeInTheDocument();
    expect(screen.getByText(t("templatesUi.workbench.format.title"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /导入 HTML/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /导入参考模板/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /自制模板/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /自制版式/ })).toBeInTheDocument();
    // 内置样式缩略图墙保留（上游曾经把它藏起来）。
    expect(document.body.textContent ?? "").toContain("内置样式");
  });

  it("内置版式的标签行仍然渲染（目录里已有的预设）", async () => {
    renderWorkbench();

    // 标签来自 `format_presets`，是"点不了但看得见"的那部分信息。
    expect(await screen.findByText("标准")).toBeInTheDocument();
    expect(screen.getByText("紧凑")).toBeInTheDocument();
  });

  it("自制版式的列表与删除仍然可用", async () => {
    templateApiMocks.listResumeTemplates.mockResolvedValue([
      templateDetail({ id: 9, name: "一页版式", kind: "format" }),
    ]);
    renderWorkbench();
    await screen.findByText("一页版式");

    fireEvent.click(screen.getAllByRole("button", { name: "更多操作" })[0]);
    // 菜单项的可访问名会带上图标与 antd 的自动空格，按文案在节点上找更稳；
    // 这也是为了不给 `cjkRatchet` 的 tests 口径添一条中文断言。
    const deleteItem = await waitFor(() => {
      const found = Array.from(document.querySelectorAll('[role="menuitem"]')).find((node) =>
        (node.textContent ?? "").includes("删除"),
      );
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    fireEvent.click(deleteItem);

    // 删除仍走二次确认（不可撤销的模板删除保留确认），确认前不发请求。
    await waitFor(() => expect(document.querySelector(".ant-modal-confirm-title")).not.toBeNull());
    expect(templateApiMocks.deleteResumeTemplate).not.toHaveBeenCalled();
  });
});
