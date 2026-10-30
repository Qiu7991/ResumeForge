/**
 * 内置样式缩略图墙：每个内置样式一张真实渲染的缩略图，点开看大图。
 *
 * 这里测的是「一眼能看出区别」这件事本身：标签变成缩略图之后，如果渲染失败就退化成
 * 占位、用户又回到了盲选——所以失败路径也要钉死。
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BuiltinStyleGallery from "./BuiltinStyleGallery";

const apiMocks = vi.hoisted(() => ({ previewResumeTemplate: vi.fn() }));

vi.mock("../../api/resumes", () => apiMocks);

const ITEMS = [
  { name: "classic", label: "经典", description: "简洁黑白" },
  { name: "modern", label: "现代", description: "强调色标题" },
];

beforeEach(() => {
  apiMocks.previewResumeTemplate.mockReset();
});

afterEach(cleanup);

describe("BuiltinStyleGallery", () => {
  it("为每个内置样式渲染一张缩略图，并按名字请求真实渲染结果", async () => {
    apiMocks.previewResumeTemplate.mockResolvedValue("<html><body>简历</body></html>");
    render(<BuiltinStyleGallery items={ITEMS} />);

    expect(screen.getByRole("button", { name: "预览「经典」样式效果" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "预览「现代」样式效果" })).toBeInTheDocument();

    await waitFor(() => expect(apiMocks.previewResumeTemplate).toHaveBeenCalledTimes(2));
    expect(apiMocks.previewResumeTemplate).toHaveBeenCalledWith({
      template_name: "classic",
      font_scale: "small",
      page_limit: 1,
    });
    expect(await screen.findByTitle("经典 样式缩略图")).toBeInTheDocument();
  });

  it("点击缩略图打开大图预览", async () => {
    apiMocks.previewResumeTemplate.mockResolvedValue("<html><body>简历</body></html>");
    render(<BuiltinStyleGallery items={ITEMS} />);

    fireEvent.click(screen.getByRole("button", { name: "预览「现代」样式效果" }));

    expect(await screen.findByTitle("内置样式大图预览")).toBeInTheDocument();
    expect(await screen.findByText("强调色标题")).toBeInTheDocument();
  });

  it("单张缩略图渲染失败时退化成占位，不影响其它样式", async () => {
    apiMocks.previewResumeTemplate.mockRejectedValue(new Error("渲染失败"));
    render(<BuiltinStyleGallery items={ITEMS} />);

    await waitFor(() => expect(apiMocks.previewResumeTemplate).toHaveBeenCalledTimes(2));
    // 两个按钮都还在——失败不该把整块墙打掉。
    expect(screen.getByRole("button", { name: "预览「经典」样式效果" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "预览「现代」样式效果" })).toBeInTheDocument();
  });

  it("按分类分组展示，缺省分类归入「其他」", async () => {
    apiMocks.previewResumeTemplate.mockResolvedValue("<html><body>简历</body></html>");
    render(
      <BuiltinStyleGallery
        items={[
          { name: "classic", label: "经典", category: "通用", description: "稳重的通用款式" },
          { name: "modern", label: "现代", category: "通用", description: "适合互联网岗位" },
          { name: "cpp", label: "C/C++ 系统", category: "系统与底层", description: "信息密度高" },
          { name: "custom", label: "无分类样式", description: "没给分类" },
        ]}
      />,
    );

    // 分组标题与计数都在。
    expect(screen.getByText("通用")).toBeInTheDocument();
    expect(screen.getByText("系统与底层")).toBeInTheDocument();
    expect(screen.getByText("其他")).toBeInTheDocument();
    // 四个卡片都渲染出来了（分组不吞条目）。
    await waitFor(() => expect(apiMocks.previewResumeTemplate).toHaveBeenCalledTimes(4));
    for (const label of ["经典", "现代", "C/C++ 系统", "无分类样式"]) {
      expect(screen.getByRole("button", { name: `预览「${label}」样式效果` })).toBeInTheDocument();
    }
  });
});
