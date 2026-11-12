// SPDX-License-Identifier: Apache-2.0
import type { AdmissionResult, HardGateResult } from "./match";
import type { QueueStatus, TaskItemStatus, TaskKind, TaskStatus } from "./tasks";

// ===== ⑦ 队列 =====
export interface ApplyQueueItem {
  id: number;
  job_id: number | null;
  job_title: string;
  company: string;
  resume_id: number | null;
  resume_title: string;
  greeting: string;
  /**
   * 招呼语是否经用户确认。按岗位批量生成后为 false（待确认），在编辑弹窗里保存才置真。
   *
   * **可选**：缺失按"未确认"处理（判断写 `=== true`）——宁可多拦一条，也不把没看过的
   * 文案当成已确认发出去。
   */
  greeting_confirmed?: boolean;
  sort_order: number;
  status: QueueStatus;
  admission: AdmissionResult | null;
  hard_gate: HardGateResult | null;
  requires_confirm: boolean;
  /**
   * 这个岗位能不能自动投递：取决于**来源**是否能归属到某个招聘网站，与匹配结论无关。
   *
   * 为 false 时（手动录入、来源与投递链接都指不到站点的岗位）勾选框禁用、也不计入
   * 「待投递」——投递台只能驱动招聘网站上的岗位，强投只会得到一条失败记录。
   *
   * **可选**：缺失按"支持"处理（与后端默认同向），判断写 `=== false`，别写 `!x`。
   */
  apply_supported?: boolean;
  /**
   * 最近一次**投递执行**的结果（2026-11-12）。与 `status` 是两件事：
   * - `status` 回答"要不要投"（pending/skipped/done/failed 四态）
   * - 这三个字段回答"投了没有、成没成、什么时候投的"（来自投递记录）
   *
   * 未投过时 `last_apply_status` 为 null。
   */
  last_apply_status?: TaskItemStatus | null;
  last_apply_at?: string | null;
  /** 失败分类（稳定码，空串 = 未失败）。展示名在语言包里。 */
  last_failure_category?: string;
  created_at: string;
  updated_at: string;
}

export interface ApplyQueueAddItem {
  job_id: number;
  resume_id?: number | null;
  greeting?: string;
  confirm_real_gap?: boolean;
  confirm_unanalyzed?: boolean;
}

/**
 * 队列列表响应（P2-2）：列表**封顶 500 条**（按 sort_order 倒序取最新入队的），
 * `total` 是队列实际条数，`truncated` 表示还有更早的条目没展示——
 * 界面要提示用筛选/开始投递消化队列，而不是假装队列只有 500 条。
 */
export interface ApplyQueueList {
  items: ApplyQueueItem[];
  total: number;
  truncated: boolean;
}

/** 入队被 409 拦下时后端回传的结构化原因（用于逐条确认）。 */
export interface QueueConflictDetail {
  message: string;
  job_id?: number;
  gaps?: string[];
  unanalyzed?: boolean;
  /**
   * 岗位来源不是投递台支持的招聘网站。
   *
   * 这一类比 `unanalyzed` / `gaps` 更硬：那两类用户可以显式确认后放行，这一类**确认也没用**
   * ——投递时根本定位不到站点，所以界面只提示、不给"仍然加入"的按钮。
   */
  site_unsupported?: boolean;
  /** 被拦下的岗位（开始投递时可能不止一个）。 */
  job_ids?: number[];
  job_titles?: string[];
}

// ===== ⑧ 批次与记录 =====
export interface ApplyTask {
  id: number;
  kind: TaskKind;
  status: TaskStatus;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  skipped: number;
  current_step: string;
  stop_reason: string;
  config: Record<string, unknown>;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ApplyTaskItem {
  id: number;
  task_id: number;
  job_id: number | null;
  job_title: string;
  company: string;
  resume_id: number | null;
  resume_title: string;
  greeting: string;
  status: TaskItemStatus;
  failure_category: string;
  failure_detail: string;
  attempt: number;
  sort_order: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ApplyTaskDetail extends ApplyTask {
  items: ApplyTaskItem[];
}

export interface ApplyRecord {
  id: number;
  task_id: number;
  job_id: number | null;
  job_title: string;
  company: string;
  resume_title: string;
  greeting: string;
  status: TaskItemStatus;
  failure_category: string;
  failure_label: string;
  failure_detail: string;
  /**
   * #39：失败三段稳定码（后端 0073）。都是协议值，展示名与「你该怎么做」在前端语言包：
   * 在哪一步（opening/…/unknown）、卡在哪个控件（chat_input 等）、为什么失败
   * （site_changed / render_timeout / page_not_navigated 等）。可选：旧响应没有。
   */
  failure_step?: string;
  failure_target?: string;
  failure_reason?: string;
  attempt: number;
  created_at: string;
  finished_at: string | null;
}

/**
 * 一个投递批次及其全部记录：投递记录按批次分组展示的载体。
 *
 * 一次「开始投递」= 一个批次；用户一次性投 N 个岗位时，这 N 条记录同属一组。
 * 组头上的统计是该批次自己的账（不随筛选变化），组内是命中的记录。
 */
/** #39：组头同因聚合项——本批某个失败分类的条数（label 已由后端按枚举翻好）。 */
export interface ApplyFailureCount {
  category: string;
  label: string;
  count: number;
}

export interface ApplyRecordBatch {
  id: number;
  status: TaskStatus;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  skipped: number;
  message: string;
  created_at: string;
  finished_at: string | null;
  /**
   * 命中当前筛选的记录数（B4 按需加载）：轻量分页（include_items=false）不携带
   * items，组头用它展示「N 条记录」；展开时再拉明细。可选：旧响应里没有。
   */
  matched_count?: number;
  /**
   * #39：「只重试这 N 条」里的 N——命中当前筛选、状态为失败的记录数。
   * 与 matched_count 分开：后者含成功/跳过，能重投的只有失败的那些。
   */
  retryable_count?: number;
  items: ApplyRecord[];
  failure_summary: ApplyFailureCount[];
}

export interface GreetingPreview {
  greeting: string;
  /** no_resume：队列条目还没有可用简历，后端拒绝凭空编招呼语。 */
  source: "generated" | "queue" | "default" | "no_resume";
}
