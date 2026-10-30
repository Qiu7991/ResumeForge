/** 模型用量与单价接口（/api/usage）。 */
import type {
  UsagePricingIn,
  UsagePricingOut,
  UsagePricingRecordListOut,
  UsagePricingRecordOut,
  UsageRecordListOut,
  UsageSummaryOut,
} from "../types/usage";
import { request } from "./client";

export function fetchUsageSummary(
  params: { task?: string; since?: string } = {},
): Promise<UsageSummaryOut> {
  const query = new URLSearchParams();
  if (params.task) query.set("task", params.task);
  if (params.since) query.set("since", params.since);
  const suffix = query.toString();
  return request("/usage/summary" + (suffix ? "?" + suffix : ""));
}

/** 最近若干条逐次调用记录（只含数字与枚举）。 */
export function fetchUsageRecords(limit = 100): Promise<UsageRecordListOut> {
  return request(`/usage/records?limit=${limit}`);
}

export function fetchUsagePricing(): Promise<UsagePricingOut> {
  return request("/usage/pricing");
}

/** 保存一份新单价（每百万 token、三档），保存后立即生效。 */
export function saveUsagePricing(payload: UsagePricingIn): Promise<UsagePricingOut> {
  return request("/usage/pricing", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function fetchUsagePricingRecords(): Promise<UsagePricingRecordListOut> {
  return request("/usage/pricing/records");
}

export function activateUsagePricingRecord(recordId: number): Promise<UsagePricingOut> {
  return request(`/usage/pricing/records/${recordId}/activate`, { method: "POST" });
}

export function deleteUsagePricingRecord(recordId: number): Promise<{ ok: boolean }> {
  return request(`/usage/pricing/records/${recordId}`, { method: "DELETE" });
}

export function renameUsagePricingRecord(
  recordId: number,
  name: string,
): Promise<UsagePricingRecordOut> {
  return request(`/usage/pricing/records/${recordId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}
