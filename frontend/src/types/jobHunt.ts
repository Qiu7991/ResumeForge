// SPDX-License-Identifier: Apache-2.0
/**
 * 自研求职采集（/api/job-hunt）的类型。
 *
 * `job_hunt_backend` 是新旧后端的总开关：sidecar = 既有 HTTP 代理（默认），
 * native = 工作通自研采集（services/job_hunt）。新老并存，删旧要等 native 稳定。
 */

export type JobHuntBackend = "sidecar" | "native";

export interface JobHuntConfig {
  job_hunt_backend: JobHuntBackend;
}

export interface JobHuntPlatform {
  key: string;
  name: string;
}

export interface JobHuntStatus {
  backend: JobHuntBackend;
  platforms: JobHuntPlatform[];
}

/** 采集到的一张岗位卡片（后端 `JobStub` 的投影）。 */
export interface JobHuntStub {
  title: string;
  company: string;
  location: string;
  /** 站点原样薪资（BOSS 是字体编码乱码）。 */
  salary_raw: string;
  /** 还原后的明文薪资；无法还原时与 salary_raw 相同。 */
  salary_decoded: string;
  salary_decoded_ok: boolean;
  url: string;
  posted_at: string;
}

/** 入库账目：inserted + skipped_duplicate 应等于采到的卡片数（errors 除外）。 */
export interface JobHuntPersistLedger {
  inserted: number;
  skipped_duplicate: number;
  errors: string[];
}

export interface JobHuntCollectResult {
  stubs: JobHuntStub[];
  pages_fetched: number;
  duplicates: number;
  stopped_reason: string;
  errors: string[];
  resumed_from_page: number;
  persisted: JobHuntPersistLedger;
  /** 被黑名单挡掉的条数。 */
  blocked: number;
  /** 有新增岗位且开启分析时的后台任务 id（hex 字符串）。 */
  analyze_task_id: string | null;
}

export interface JobHuntBlocklist {
  companies: string[];
  keywords: string[];
}

export interface JobHuntCollectRequest {
  site_key: string;
  keywords?: string;
  city?: string;
  max_pages?: number;
  city_code?: string;
  resume?: boolean;
  /** 是否写进岗位广场（默认 true）。 */
  persist?: boolean;
  /** 是否对本次新增岗位触发一次分析（默认 true；服务端 force=false 不重复评分）。 */
  analyze?: boolean;
}

/** 五维评分中的单项。 */
export interface ScoredComponent {
  key: string;
  label: string;
  score: number;
  limit: number;
  evidence: string;
}

/** 语义评分结果（后端 `semantic_score` 子键的投影）。 */
export interface SemanticScore {
  total: number;
  raw_total: number;
  components: ScoredComponent[];
  /** 命中封顶规则（technical_required / sales_acquisition_core / weak_core_transfer）。 */
  caps: string[];
  /** JD 明确必备但未获证据支持的项。 */
  hard_gaps: string[];
  role_summary: string;
  reason: string;
  missing: string;
  ok: boolean;
  error: string;
  /** JD 要求 ↔ 简历证据的逐条比对。 */
  skill_compare: SkillMatch[];
  /** 评分时用的简历（便于同一岗位对比不同简历）。 */
  resume_id: number | null;
  resume_title: string;
}

/** JD 要求的一条技能与简历的比对结果。 */
export interface SkillMatch {
  skill: string;
  /** matched = 有直接证据；partial = 相邻/部分覆盖；missing = 未体现。 */
  status: "matched" | "partial" | "missing";
  resume_evidence: string;
}

/** 采集任务状态（与后端 collect_task.py 的取值一致）。 */
export type CollectTaskStatus = "running" | "paused" | "completed" | "stopped" | "failed";

export interface CollectTaskSnapshot {
  task_id: string;
  site_key: string;
  keywords: string;
  city: string;
  max_pages: number;
  status: CollectTaskStatus;
  current_page: number;
  collected: number;
  message: string;
  error: string;
  blocked: number;
  stopped_reason: string;
  stub_count: number;
  finished: boolean;
  /**
   * 采集之后的阶段（2026-11-11 方案 3）："" → collected → staged → filling_jd → scoring。
   *
   * 用来让用户看见"采完之后还在干什么"。之前只有 running/finished 两态，
   * 采完那一瞬间看起来就像停了。
   */
  stage?: CollectTaskStage;
  /** 落进备选岗位暂存区的条数（评分与导入都以这些候选为准）。 */
  candidate_count?: number;
  /** 与正式岗位/暂存区重复而跳过的条数。 */
  duplicates?: number;
  /** 用户选了但没能生效的筛选项（快照里认不出的标签），界面要如实显示。 */
  unapplied_filters?: string[];
  /** 本地二次筛选（经验/学历标签）挡掉的条数。 */
  tag_filtered?: number;
  /** 多关键词进度：当前第几个 / 共几个、当前关键词。 */
  keyword_index?: number;
  keyword_total?: number;
  keyword?: string;
  /** 补 JD 的处理进度：已处理 / 总数（补 JD 限速，界面上要能看到几分之几）。 */
  jd_done?: number;
  jd_total?: number;
  /** 补 JD 成功的条数。 */
  jd_filled?: number;
  /** 是否已把评分任务交给后台（为真时前端才开始轮询分数）。 */
  score_started?: boolean;
}

/** 采集任务在采完之后的阶段（协议值，中文文案在语言包里）。 */
export type CollectTaskStage = "" | "collected" | "staged" | "filling_jd" | "scoring";

export interface CollectTaskResult extends CollectTaskSnapshot {
  stubs: JobHuntStub[];
}
