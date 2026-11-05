# 二开功能落点校对表（N1 交付物）

> 方法：以 `docs/fork-2.0-migration-inventory.md`（自 1.x 复制，写的是 1.x 路径）逐行对照
> 2.0 基线（tag `upstream-v2.0.0` = d893243，树清单 `runtime/upstream-tree.txt`，4266 文件）。
> 每行状态都有 grep / ls 证据（注明在备注列）。校对时间：2026-11-06 夜。
>
> 状态口径：**EXISTS** = 2.0 存在同名文件（fork 逻辑是否在内见备注）；
> **MOVED** = 功能在但路径变；**GONE** = 2.0 没有，需新建/移植。

## 1. 投递台与自动投递（清单 §2.1）

| 二开功能 | 2.0 实际落点 | 状态 | 备注（证据） |
|---|---|---|---|
| 投递队列（加入/编辑/排序/移出/批量移出） | `backend/app/api/apply_queue.py`、`backend/app/services/apply/_queue.py`、`frontend/src/components/apply/ApplyQueuePanel.tsx` | EXISTS | ls-tree 命中；上游已有完整队列 |
| 队列编辑/表格/筛选组件 | `frontend/src/components/apply/queue/QueueItemEditor.tsx`、`QueueTable.tsx`、`QueueFilterBar.tsx` | MOVED | 1.x 平铺在 components/apply/，2.0 移入 `queue/` 子目录（ls 命中） |
| 批次执行（熔断/暂停/限速/同公司只投一个） | `services/apply/task_apply.py`、`task_runner.py`、`_tasks.py` | EXISTS | ls-tree 命中；fork 增量（同公司互斥的 greeting 侧逻辑）待 N3 对照 |
| 失败三列（step/target/reason） | `models/apply.py:308-310`、`failure_taxonomy.py` | EXISTS | **上游已原生具备**（models/apply.py 注释引用迁移 0073 语义）；无需移植 |
| failure_category / failure_detail | `models/apply.py:302-304` | EXISTS | 上游已有，N2 的「若 2.0 没有」分支不触发 |
| **招呼语闸门**（greeting_confirmed） | 目标：models/apply.py、schemas/apply/config.py、`_queue.py`、`task_apply.py`、api/apply.py | GONE（符号级） | 全后端 grep `greeting_confirmed` = 0 命中；1.x `task_apply.py:455` 与 `_queue.py:90,214,243-261` 为移植源 → **N2（列）+ N3（逻辑）** |
| **greeting_unconfirmed 分类 + 批量确认 + 预检** | 目标：models/apply.py、failure_taxonomy.py、task_apply.py | GONE（符号级） | 2.0 FAILURE_CATEGORIES 10 类里无此二者 → **N3** |
| 招呼语按 JD 生成（基准模板/去学历） | `backend/app/prompts/apply_greeting.md` | EXISTS（需改造） | 2.0 已有该提示词但**无**「语气基准/去学历」节（grep 命中 1.x:13,76 vs 2.0 仅通用约束）；`jd_relevance.py` GONE → **N3** |
| `greeting_baseline` 设置项 | 目标：`schemas/apply/config.py`（现只到 default_greeting:34） | GONE | grep greeting_baseline 后端 = 0 → **N3** |
| 保存并确认 + 文案变→打回 | `_queue.py::update_queue_item`（2.0:219 存在） | EXISTS（需改造） | 函数在，无 confirm_greeting/打回逻辑 → **N3** |
| 编辑弹窗查看 JD | `queue/QueueItemEditor.tsx` | MOVED | 组件在，JD 查看块待 N7 对照 |
| BOSS 适配器 | `services/sites/boss_apply.py`、`boss_apply_scripts.py`、`boss_page.py`、`browser/interaction.py` | EXISTS | ls-tree 命中 |
| **点击前等 readyState=complete** | 目标 `boss_apply.py::_wait_document_complete` | GONE（符号级） | grep = 0 命中 → **N5（本轮范围外）** |
| **trusted_click 焦点仿真** | `browser/interaction.py::trusted_click`（2.0:37 存在） | EXISTS（需改造） | 无 `setFocusEmulationEnabled`（grep=0）→ **N5（本轮范围外）** |
| **job_closed 软跳过** | 目标 models/apply.py 等 | GONE（符号级） | grep job_closed = 0 → **N5（本轮范围外）** |
| 投递专用浏览器（open-url、登录态保留） | `services/browser/*`、`api/apply.py` | EXISTS | ls-tree 命中；运行时 browser_port 已置 9343（blocked.md B-1） |
| 失败诊断（弹窗/可见性/焦点/文档状态） | `boss_page.py::selector_diagnostic`（2.0:244） | EXISTS | **上游已原生具备** |
| 导出截断明确提示 | `application.py:438-439`、`api/resumes/layout_render_routes.py:234` | EXISTS（原生） | **2.0 已有 `X-Resume-Truncated(-At)` / `pages_needed`，不要带 1.x 旧实现**（§10.2） |

## 2. AI 求职（清单 §2.2，整体 fork 独有）

| 二开功能 | 2.0 实际落点 | 状态 | 备注 |
|---|---|---|---|
| sidecar 服务层 15 文件 | `backend/app/services/ai_jobs/` | GONE | 目录不存在（ls）→ **N6（本轮范围外）** |
| API + 前端页面 | `api/ai_jobs.py`、`pages/AiJobsPage.tsx`、`components/ai-jobs/*`、i18n aiJobs | GONE | 全部 grep/ls = 0 → **N6/N7（本轮范围外）** |
| `ai_job_link` 表 | 目标：新迁移 | GONE | N2 建表（本轮） |
| 与投递台双向互斥（409） | 目标：`task_runner.py` | GONE（符号级） | N6（本轮范围外） |

## 3. 岗位广场 / 采集 / 导入（清单 §2.3）

| 二开功能 | 2.0 实际落点 | 状态 | 备注 |
|---|---|---|---|
| 按链接/当前页导入 JD | `api/job_import.py` | GONE | 2.0 的 JD 导入走 `api/jobs.py`（语义不同）→ 无对应任务卡，**本轮不移植，记待办** |
| 页内悬浮收录扩展 | `services/browser/extension/` | GONE | 同上，记待办 |
| 招聘平台派生列与筛选 | `services/job/platform.py` | GONE | 同上，记待办 |
| 城市筛选/秒级时间/类型按 JD 推断 | `api/jobs.py` EXISTS；`job_sorting.py` EXISTS；`job_type_infer.py` GONE | EXISTS/GONE | 推断器无卡，记待办 |
| CSV 批量导入 | `services/job/job_csv.py`、`api/jobs.py` | EXISTS | **上游已原生具备**（grep 命中 + tests/test_job_csv.py）；`bh_import/` 是工作区脚本不入仓 |

## 4. 简历生成 / 制作台（清单 §2.4）

| 二开功能 | 2.0 实际落点 | 状态 | 备注 |
|---|---|---|---|
| v2 字段级文档模型 | `schemas/resume*`、`services/resume/document_*` | EXISTS（原生） | 2.0 原生 v2，无需移植 |
| 模板 17→18 套 / 自制样式模板 | — | DROPPED | 2.0 已移除该 UI（计划 §10.3），放弃 |
| 隐藏板块/条目头布局/短字段位置 | — | EXISTS（原生） | 2.0 字段级文档原生支持（§10.2） |
| 匹配报告（resume_generation_plan） | 2.0 有 `api/job_match.py` + `job_match*.py` + `job_match_analysis` 表（准入用） | GONE（plan 表） | 上游是**匹配分析**，fork 是**生成证据映射**（不同功能）；`resume_generation_plan` 表 → **N2 建表**，服务层 → **N8（本轮范围外）** |
| 画像导入 | `scripts/import_portrait.py`、`prompts/portrait_extract.md` | GONE | **N8（本轮范围外）**；目标改写：无 profile_facts，写 claims/资料字段 |
| 生成结果去重限量 | `services/resume/resume_dedupe.py` | GONE | **N8（本轮范围外）** |
| 覆盖清单「从资料补上这段」 | `services/resume/resume_coverage.py`、`resume_coverage_notes.py` | EXISTS | 2.0 已有 coverage 两文件；fork 的收窄语义待 N8 对照 |
| 「显示技术栈」开关 | 目标：设置项 + 生成后处理 | GONE | **N8（本轮范围外）** |
| 底稿模式按 JD 修订 | `services/resume/*` | EXISTS | 细节对齐属 N8，本轮不动 |
| v2 单模型整改（v1 读路径清零） | `scripts/v2_gate.py` | GONE | 1.x QA 工具，**不移植**（2.0 无 v1 读路径问题）；后续 grep 抽查即可 |

## 5. 设置 / 系统（清单 §2.5）

| 二开功能 | 2.0 实际落点 | 状态 | 备注 |
|---|---|---|---|
| 自定义「打招呼语基准」 | `ApplySettingsModal.tsx` EXISTS、`schemas/apply/config.py` EXISTS | GONE（符号级） | greeting_baseline 见 §1 → N3 |
| 侧栏可收起 / 批量操作卡 | `AppShell`/`BaseLayout`/`SettingsPage.tsx` | EXISTS | 2.0 导航已变（N7 对照），本轮不动 |
| 更新检查与公告条 | `services/update_check.py` | EXISTS | 上游已有 |

## 6. 2.0 已原生具备、不要移植（汇总）

1. `PATCH /api/resumes/{id}/layout` 局部更新（§10.2）。
2. 导出截断如实上报：`X-Resume-Truncated` / `X-Resume-Truncated-At` / `pages_needed`（application.py:438-439）。
3. 失败三列 `failure_step/target/reason` + `failure_category/failure_detail`（models/apply.py:302-310）。
4. 隐藏板块 / 条目头三布局 / 短字段位置（字段级文档原生）。
5. `page_limit=0`「不限」语义（移植代码里禁止 `page_limit or 1`，闸门 phase 2 强制）。
6. `selector_diagnostic` 失败诊断（boss_page.py:244）。
7. CSV 批量导入（job_csv.py + test_job_csv.py）。
8. 队列三组件基础版（components/apply/queue/）。

## 7. 统计与 GONE 清单

- EXISTS（含「EXISTS 需改造」）：**29** 条；MOVED：**2** 条；GONE：**12** 条（不含 DROPPED 1 条）。
- GONE 且本轮做：`greeting_confirmed`×2 列（N2）、`ai_job_link`（N2）、`resume_generation_plan`（N2）、
  greeting 闸门/分类/基准/队列打回（N3）、`jd_relevance.py`（N3）。
- GONE 且本轮范围外（N5–N8）：BOSS 三修复、ai_jobs 全家桶、resume_dedupe、import_portrait、
  portrait_extract.md、显示技术栈开关。
- GONE 且无任务卡（记待办）：`api/job_import.py`、`browser/extension/`、`platform.py`、`job_type_infer.py`。
- 不移植：`scripts/v2_gate.py`（1.x QA 工具）、模板扩展（DROPPED）。
