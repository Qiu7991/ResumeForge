/** 模型用量汇总与单价（/api/usage）：只含数字与枚举，不含任何正文。 */

export interface UsageBucketOut {
  key: string;
  calls: number;
  retries: number;
  /** null = 存在未知用量（不是 0）。 */
  prompt_tokens: number | null;
  cache_hit_tokens: number | null;
  cache_miss_tokens: number | null;
  cache_unknown_calls: number;
  completion_tokens: number | null;
  total_tokens: number | null;
  duration_ms: number | null;
  unknown_token_calls: number;
  finish_reasons: Record<string, number>;
}

export interface UsageCostOut {
  estimated: boolean;
  currency: string;
  amount: number | null;
  reason: string;
}

export interface UsageSummaryOut {
  dataset_id: string | null;
  records: number;
  since: string | null;
  tasks: UsageBucketOut[];
  models: UsageBucketOut[];
  totals: UsageBucketOut;
  unknown_token_records: number;
  cost: UsageCostOut;
}

/** 一份单价（每百万 token）：输入拆缓存命中 / 未命中，输出一档。 */
export interface UsagePricingIn {
  name: string;
  input_cache_hit_per_million: number | null;
  input_cache_miss_per_million: number | null;
  output_per_million: number | null;
  currency: string;
}

export interface UsagePricingOut {
  configured?: boolean;
  input_cache_hit_per_million: number | null;
  input_cache_miss_per_million: number | null;
  output_per_million: number | null;
  currency: string;
  source?: string;
  record_id?: number | null;
  name?: string;
}

export interface UsagePricingRecordOut {
  id: number;
  name: string;
  input_cache_hit_per_million: number | null;
  input_cache_miss_per_million: number | null;
  output_per_million: number | null;
  currency: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface UsagePricingRecordListOut {
  items: UsagePricingRecordOut[];
  count: number;
}

export interface UsageRecordOut {
  id: number;
  task: string;
  model: string;
  finish_reason: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  duration_ms: number | null;
  retries: number;
  created_at: string | null;
}

export interface UsageRecordListOut {
  items: UsageRecordOut[];
  count: number;
}
