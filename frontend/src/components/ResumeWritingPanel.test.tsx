/** 简历写作增强面板：操作切换、调用接口、结果展示与回填。 */
import { App as AntdApp } from "antd";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResumeWritingPanel from "./ResumeWritingPanel";

const apiMocks = vi.hoisted(() => ({
  rewriteStar: vi.fn(),
  generatePhrases: vi.fn(),
  polishResumeText: vi.fn(),
  translateResumeText: vi.fn(),
}));

vi.mock("../api/resumeWriting", () => apiMocks);

function renderPanel(onApply: (text: string) => void = vi.fn()) {
  return render(
    <AntdApp>
      <ResumeWritingPanel resumeId={7} initialText="负责后端服务开发" onApply={onApply} />
    </AntdApp>,
  );
}

beforeEach(() => {
  for (const mock of Object.values(apiMocks)) mock.mockReset();
});

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("ResumeWritingPanel", () => {
  it("STAR 改写调用接口、展示结果并可回填", async () => {
    apiMocks.rewriteStar.mockResolvedValue({ result: "负责后端服务开发，性能提升 30%" });
    const onApply = vi.fn();
    renderPanel(onApply);

    fireEvent.click(screen.getByRole("button", { name: /生\s*成/ }));

    expect(await screen.findByText(/性能提升 30%/)).toBeInTheDocument();
    expect(apiMocks.rewriteStar).toHaveBeenCalledWith(7, "负责后端服务开发");

    fireEvent.click(screen.getByRole("button", { name: "回填" }));
    expect(onApply).toHaveBeenCalledWith("负责后端服务开发，性能提升 30%");
    // 回填后输入框也要跟着变成结果，否则框里还显示旧文字，用户会以为没生效。
    expect(screen.getByLabelText("写作输入文本")).toHaveValue("负责后端服务开发，性能提升 30%");
  });

  it("直接编辑输入框会通知父组件，这段文字就是个人总结", () => {
    const onTextChange = vi.fn();
    render(
      <AntdApp>
        <ResumeWritingPanel
          resumeId={7}
          initialText="旧的总结"
          onApply={vi.fn()}
          onTextChange={onTextChange}
        />
      </AntdApp>,
    );

    const box = screen.getByLabelText("写作输入文本");
    expect(box).toHaveValue("旧的总结");
    fireEvent.change(box, { target: { value: "新的总结" } });

    // 父组件靠这个回调把改动写进表单；丢掉它就会出现"改完保存却没变化"。
    expect(onTextChange).toHaveBeenCalledWith("新的总结");
    expect(box).toHaveValue("新的总结");
  });

  it("话术生成展示三种版式", async () => {
    apiMocks.generatePhrases.mockResolvedValue({
      star: "STAR 改写结果",
      resume: "简历话术",
      interview: "口述内容",
    });
    renderPanel();

    fireEvent.click(screen.getByText("话术生成"));
    fireEvent.click(screen.getByRole("button", { name: /生\s*成/ }));

    expect(await screen.findByText("STAR 改写结果")).toBeInTheDocument();
    expect(screen.getByText("简历话术")).toBeInTheDocument();
    expect(screen.getByText("口述内容")).toBeInTheDocument();
    expect(apiMocks.generatePhrases).toHaveBeenCalledWith(7, "负责后端服务开发", [
      "star",
      "resume",
      "interview",
    ]);
  });

  it("接口报错时透出中文错误", async () => {
    apiMocks.rewriteStar.mockRejectedValue(new Error("STAR 改写失败：模型未返回有效结果"));
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /生\s*成/ }));

    expect(await screen.findByText(/STAR 改写失败/)).toBeInTheDocument();
  });
});
