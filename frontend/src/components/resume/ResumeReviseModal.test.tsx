/** ResumeReviseModal：模式文案、提交与错误路径。 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App as AntdApp } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResumeReviseModal from "./ResumeReviseModal";
import { reviseResume } from "../../api/resumes";
import type { ResumeDetail } from "../../types";

vi.mock("../../api/resumes", () => ({
  reviseResume: vi.fn(),
}));

/** 组件用 App.useApp() 取 message：渲染必须包在 AntdApp 里。 */
function renderModal(ui: React.ReactElement) {
  return render(<AntdApp>{ui}</AntdApp>);
}

function detail(overrides: Partial<ResumeDetail> = {}): ResumeDetail {
  return {
    id: 7,
    title: "示例简历",
    job_id: null,
    job_title: "",
    company: "",
    source: "ai",
    favorite: false,
    model: "",
    enhancement_enabled: false,
    enhancement_level: "balanced",
    note: "",
    template: "classic",
    format_name: "",
    format_config: {},
    page_limit: 1,
    font_scale: "standard",
    created_at: "2026-10-01T10:00:00",
    content: {} as ResumeDetail["content"],
    warnings: [],
    parse_error: "",
    ...overrides,
  } as ResumeDetail;
}

describe("ResumeReviseModal", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  it("switches the confirm label between targeted and full regenerate modes", () => {
    renderModal(<ResumeReviseModal open recordId={7} onClose={vi.fn()} onApplied={vi.fn()} />);

    expect(screen.getByRole("button", { name: "整体重新生成" })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/留空则整体重新生成/), {
      target: { value: "把总结改短" },
    });
    expect(screen.getByRole("button", { name: "按要求修改" })).toBeInTheDocument();
    expect(screen.getByText(/只会修改你明确提出的内容/)).toBeInTheDocument();
  });

  it("submits the instruction and hands the updated record back", async () => {
    vi.mocked(reviseResume).mockResolvedValue(
      detail({ content: { summary: "新的总结" } as ResumeDetail["content"] }),
    );
    const onApplied = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    renderModal(<ResumeReviseModal open recordId={7} onClose={onClose} onApplied={onApplied} />);

    fireEvent.change(screen.getByPlaceholderText(/留空则整体重新生成/), {
      target: { value: "把总结改短" },
    });
    fireEvent.click(screen.getByRole("button", { name: "按要求修改" }));

    await waitFor(() => {
      expect(reviseResume).toHaveBeenCalledWith(7, "把总结改短");
    });
    await waitFor(() => {
      expect(onApplied).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("submits empty instructions as a full regenerate", async () => {
    vi.mocked(reviseResume).mockResolvedValue(detail());
    renderModal(<ResumeReviseModal open recordId={7} onClose={vi.fn()} onApplied={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "整体重新生成" }));

    await waitFor(() => {
      expect(reviseResume).toHaveBeenCalledWith(7, "");
    });
  });

  it("surfaces backend errors instead of closing", async () => {
    vi.mocked(reviseResume).mockRejectedValue(new Error("请先在「设置」页配置大模型 API"));
    const onClose = vi.fn();
    renderModal(<ResumeReviseModal open recordId={7} onClose={onClose} onApplied={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "整体重新生成" }));

    expect(await screen.findByText(/配置大模型/)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows a live wait indicator and keeps the dialog open while generating", async () => {
    let resolveRevise!: (value: ResumeDetail) => void;
    vi.mocked(reviseResume).mockReturnValue(
      new Promise<ResumeDetail>((resolve) => {
        resolveRevise = resolve;
      }),
    );
    const onClose = vi.fn();
    renderModal(<ResumeReviseModal open recordId={7} onClose={onClose} onApplied={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "整体重新生成" }));

    // 生成中要给"在跑"的明确反馈：等待秒数会走，取消被禁用，关闭入口收起。
    expect(await screen.findByText(/正在生成…（已等待 \d+ 秒）/)).toBeInTheDocument();
    expect(screen.getByText(/通常需要 20–60 秒/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /取\s*消/ })).toBeDisabled();
    expect(screen.queryByLabelText("Close")).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    resolveRevise(detail());
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("reports how long the generation took when it succeeds", async () => {
    vi.mocked(reviseResume).mockResolvedValue(detail());
    renderModal(<ResumeReviseModal open recordId={7} onClose={vi.fn()} onApplied={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "整体重新生成" }));

    // 成功提示带上耗时，用户能确认这一轮确实跑过，而不是看到了旧内容。
    expect(await screen.findByText(/已重新生成简历内容（用时 \d+ 秒）/)).toBeInTheDocument();
  });
});
