import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App as AntdApp } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import UsagePricingCard from "./UsagePricingCard";

const api = vi.hoisted(() => ({
  fetchUsageSummary: vi.fn(),
  fetchUsagePricing: vi.fn(),
  fetchUsagePricingRecords: vi.fn(),
  saveUsagePricing: vi.fn(),
  activateUsagePricingRecord: vi.fn(),
  deleteUsagePricingRecord: vi.fn(),
}));
vi.mock("../../api/usage", () => api);

function renderCard() {
  return render(
    <AntdApp>
      <UsagePricingCard />
    </AntdApp>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UsagePricingCard", () => {
  it("显示调用次数与 token；未配置单价时说明不估算费用", async () => {
    api.fetchUsageSummary.mockResolvedValue({
      dataset_id: "main",
      records: 3,
      since: null,
      tasks: [
        {
          key: "job_match",
          calls: 3,
          retries: 0,
          prompt_tokens: 300,
          cache_hit_tokens: null,
          cache_miss_tokens: null,
          cache_unknown_calls: 0,
          completion_tokens: 90,
          total_tokens: 390,
          duration_ms: 1200,
          unknown_token_calls: 0,
          finish_reasons: { stop: 3 },
        },
      ],
      models: [],
      totals: {
        key: "total",
        calls: 3,
        retries: 0,
        prompt_tokens: 300,
        cache_hit_tokens: null,
        cache_miss_tokens: null,
        cache_unknown_calls: 0,
        completion_tokens: 90,
        total_tokens: 390,
        duration_ms: 1200,
        unknown_token_calls: 0,
        finish_reasons: { stop: 3 },
      },
      unknown_token_records: 0,
      cost: {
        estimated: false,
        currency: "",
        amount: null,
        reason: "未配置模型价格，不估算费用",
      },
    });
    api.fetchUsagePricing.mockResolvedValue({
      configured: false,
      input_cache_hit_per_million: null,
      input_cache_miss_per_million: null,
      output_per_million: null,
      currency: "CNY",
    });
    api.fetchUsagePricingRecords.mockResolvedValue({ items: [], count: 0 });

    renderCard();

    expect(await screen.findByText(/共 3 次模型调用/)).toBeInTheDocument();
    expect(screen.getByText(/未配置模型价格，不估算费用/)).toBeInTheDocument();
    expect(screen.getByText(/job_match：3 次/)).toBeInTheDocument();
  });

  it("三档单价全空时拒绝保存，不发请求", async () => {
    api.fetchUsageSummary.mockResolvedValue({
      dataset_id: "main",
      records: 0,
      since: null,
      tasks: [],
      models: [],
      totals: {
        key: "total",
        calls: 0,
        retries: 0,
        prompt_tokens: 0,
        cache_hit_tokens: null,
        cache_miss_tokens: null,
        cache_unknown_calls: 0,
        completion_tokens: 0,
        total_tokens: 0,
        duration_ms: 0,
        unknown_token_calls: 0,
        finish_reasons: {},
      },
      unknown_token_records: 0,
      cost: { estimated: false, currency: "", amount: null, reason: "未配置模型价格，不估算费用" },
    });
    api.fetchUsagePricing.mockResolvedValue({
      configured: false,
      input_cache_hit_per_million: null,
      input_cache_miss_per_million: null,
      output_per_million: null,
      currency: "CNY",
    });
    api.fetchUsagePricingRecords.mockResolvedValue({ items: [], count: 0 });

    renderCard();

    fireEvent.click(await screen.findByRole("button", { name: /保存为新单价/ }));

    await waitFor(() =>
      expect(screen.getByText(/至少填写一档单价/)).toBeInTheDocument(),
    );
    expect(api.saveUsagePricing).not.toHaveBeenCalled();
  });
});
