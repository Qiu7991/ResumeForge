# 简历通二开功能清单（迁移上游 2.0 用）

> 用途：把这套 fork 相对上游做过的改动记成一份可执行的迁移清单。将来要么把功能移植到
> 上游 2.0，要么直接在 2.0 上重新实现时，按这份清单逐项核对，不靠记忆。
>
> 基线：本地 `fix/v2-single-model`（版本 1.0.2 + 本地二开），上游 `v2.0.0`（2026-11-05）。
> 生成时间：2026-11-05。

## 0. 先看结论

- **不要点应用内的「去更新」**。上游更新器会下载 2.0 的整包覆盖程序文件；2.0 首次启动会把
  1.x 数据库整包归档后**用空库启动**（简历、岗位、队列、设置都不迁移）。
- 想保留这套二开，只有两条路：
  1. **移植**：在 2.0 分支上按本文档逐项重放（推荐先做数据层，再做投递/AI 求职）；
  2. **并行**：2.0 另装目录、另换端口，用数据副本体验；两边暂不合并。
- 上游 2.0 已经修掉了本地踩过的两个坑，移植时**直接用上游实现**，不要带旧代码：
  - `PATCH /api/resumes/{id}/layout` 的「局部更新」（只写请求里出现的键）；
  - 导出截断的如实上报（`X-Resume-Truncated` / `pages_needed`，PDF 也算）。

## 1. 上游 2.0.0 的硬变化（影响移植方式）

| 变化 | 对本地的影响 |
| --- | --- |
| 迁移链重置为单一 2.0 基线，74 条历史迁移删除 | 本地新增的 0069/0070/0075 等迁移无法再「叠」在链上；要写成 2.0 基线之后的迁移，或并入基线 |
| 1.x 库启动时整包归档、空库启动 | 想保留现有资料，必须单独写「1.x 归档包 → 2.0 新库」的导入脚本 |
| 1.x 备份包被 2.0 拒收；2.0 包 1.0.2 打不开 | 迁移期两边数据不互通，需一次性导出/导入 |
| `profile_facts`（补充事实）整套删除 | 移植画像/事实相关功能前先核对它用的是 `claims` 还是 `profile_facts` |
| `page_limit=0`（不限）成为语义值 | 移植投递/导出/存档链路时，所有 `x or 1` 都要改成 `x if x is not None else 1` |
| 更新前快照改为完整整包 | 升级前会自动归档，但**不等于**会把旧资料迁进 2.0 |

## 2. 二开功能清单

图例：**[新增]** = 上游没有、fork 独有；**[改造]** = 上游有基线、本地改过。

### 2.1 投递台与自动投递

| 功能 | 类型 | 代码落点 | 数据/配置 |
| --- | --- | --- | --- |
| 投递队列（加入/编辑/排序/移出/批量移出） | [改造] | `backend/app/api/apply_queue.py`、`backend/app/services/apply/_queue.py`、`frontend/src/components/apply/ApplyQueuePanel.tsx`、`queue/*` | `apply_queue_item` |
| 批次执行（逐条、熔断、暂停/继续/停止、限速、同公司只投一个） | [改造] | `backend/app/services/apply/task_apply.py`、`task_runner.py`、`_tasks.py` | `apply_task`、`apply_task_item` |
| 失败三列（step / target / reason）与分类 | [改造] | `failure_taxonomy.py`、`models/apply.py` | `apply_task_item.failure_step/target/reason` |
| **招呼语闸门**（有文案≠已确认；未确认不发送） | [新增] | `task_apply.py`、`_queue.py`、`api/apply.py`、`QueueItemEditor.tsx`、`QueueTable.tsx` | `greeting_confirmed`（迁移 0069） |
| **招呼语待确认** 独立失败分类 + 批量确认 + 开始前预检 | [新增] | `models/apply.py`、`failure_taxonomy.py`、`task_apply.py`、`ApplyQueuePanel.tsx`、`QueueFilterBar.tsx` | 无迁移（字符串分类） |
| 招呼语按 JD 生成：基准模板、去学历、项目相关度排序 | [新增/改造] | `backend/app/prompts/apply_greeting.md`、`services/job/jd_relevance.py`、`job_match_context.py`、`api/apply.py` | 设置项 `greeting_baseline` |
| 编辑弹窗「保存并确认」；换简历后按「文案是否也变了」决定是否打回未确认 | [新增] | `_queue.py::update_queue_item`、`QueueItemEditor.tsx` | — |
| 编辑弹窗内查看岗位 JD | [新增] | `QueueItemEditor.tsx`、`styles/apply.css`、i18n `applyQueue.editor.jd*` | — |
| BOSS 适配器：可信点击、跨页导航、聊天页/对话框两形态、新标签页收养 | [改造] | `services/sites/boss_apply.py`、`boss_apply_scripts.py`、`boss_page.py`、`browser/interaction.py` | — |
| **点击前等页面装载完**（修「点了没反应」） | [新增] | `boss_apply.py::_wait_document_complete` | — |
| **点击前焦点仿真**（修 Ego 多窗口下 `visibilityState=hidden`） | [新增] | `browser/interaction.py::trusted_click` | — |
| **岗位已关闭**软跳过分类（`job_closed`） | [新增] | `models/apply.py`、`failure_taxonomy.py`、`task_apply.py`、`boss_apply.py`、`boss_apply_scripts.py` | 无迁移 |
| 投递专用浏览器（Ego Lite / Chrome，登录态跨重启保留） | [改造] | `services/browser/*`、`api/apply.py`（open-url）、`ApplySettingsModal.tsx` | 端口 9333、profile 目录 |
| 失败诊断带弹窗/可见性/焦点/文档状态 | [新增] | `boss_page.py::selector_diagnostic` | — |
| 导出被截断时明确提示 | [新增] | `ExportOptionsModal.tsx`、`api/resumes.ts`（解析 `X-Resume-Overflow` / `Pages-Needed`） | — |

### 2.2 AI 求职（BossHunter sidecar，整体 fork 独有）

| 功能 | 代码落点 | 备注 |
| --- | --- | --- |
| 引擎连接三态、启动前六项检查、实例采纳 | `backend/app/services/ai_jobs/*`、`api/ai_jobs.py`、`components/ai-jobs/ConnectionCard.tsx`、`PreflightPanel.tsx` | 引擎不随仓库分发 |
| 任务启停/轮询、闸门（`AI_JOBS_ALLOW_SEND`）、busy 自愈 | `ai_jobs/tasks.py`、`gate.py`、`manager.py` | 环境变量控制发送 |
| 岗位池同步、五维评分、招呼语编辑/确认、回复收件箱、运行记录 | `ai_jobs/job_sync.py`、`greeting.py`、`replies.py`、`status.py`、`components/ai-jobs/*` | 迁移 **0075** `ai_job_link` 表 |
| 简历 DOCX 同步（内容哈希缓存） | `ai_jobs/resume_sync.py` | — |
| 与投递台双向互斥（409） | `ai_jobs/tasks.py`、`services/apply/task_runner.py` | — |

> 2.0 移植注意：`0075` 是「只加一张表」的增量迁移，在 2.0 里必须改成基线之后的新迁移；
> 前端的 `AiJobsPage` / `components/ai-jobs` 可以整体搬，但 2.0 的导航、i18n 命名空间与
> 数据集上下文可能已变，需要跟一遍。

### 2.3 岗位广场 / 采集 / 导入

| 功能 | 类型 | 代码落点 |
| --- | --- | --- |
| 按链接 / 当前页导入 JD，页内悬浮「收录到简历通」扩展 | [新增] | `api/job_import.py`、`services/browser/extension/*`、`frontend/src/components/jobs/JobImportModal.tsx` |
| 招聘平台派生列与筛选（不加库列） | [新增] | `services/job/platform.py`、`frontend/src/features/jobs/*` |
| 城市筛选、收录时间精确到秒、批量删除、类型按 JD 推断（默认社招） | [新增/改造] | `api/jobs.py`、`services/job/job_sorting.py`、`job_type_infer.py`、`JobsPage.tsx` |
| CSV 批量导入（BossHunter ready 岗位灌入） | [改造] | `services/job/job_csv.py`、`api/job_import.py`、`bh_import/import_ready_jobs.py`（工作区脚本） |

### 2.4 简历生成 / 制作台二开

| 功能 | 类型 | 代码落点 |
| --- | --- | --- |
| v2 字段级文档模型 + 旧简历内存转换 | [改造] | `schemas/resume*`、`services/resume/document_*`、前端 `components/resume-editor/*` |
| 模板库扩展（17→18 套，含 scholar）与自制样式模板 | [新增] | `services/resume/resume_templates*`、模板目录 |
| 隐藏板块 / 隐藏字段 / 条目头三布局 / 短字段位置 | [新增] | `document_view.py`、`paper_document`、`EntryLayoutPanel.tsx` |
| **匹配报告**（JD 要求 → 证据映射，plan_id 进生成） | [新增] | `api/job_match.py`、`services/job/job_match*`、迁移 **0070** `resume_generation_plan` |
| **画像导入**（Markdown → 资料库 + 事实现金） | [新增] | `scripts/import_portrait.py`、`prompts/portrait_extract.md` |
| 「从资料补上这段」/ coverage_notes 收窄 / 生成结果去重限量 | [新增] | `services/resume/resume_dedupe.py`、`resume_coverage*`、前端清单组件 |
| 简历生成偏好「显示技术栈」开关（默认关） | [新增] | 设置项 + 生成后处理（清空 `tech_stack`） |
| 底稿模式按 JD 修订、沿用底稿版式 | [改造] | `services/resume/*`、`GenerateResumeModal.tsx` |
| v2 单模型整改（v1 读路径清零、`v2_gate.py`） | [改造] | `docs/fork-v2-compatibility-plan.md`、`scripts/v2_gate.py` |

### 2.5 设置 / 系统

| 功能 | 代码落点 |
| --- | --- |
| 自定义「打招呼语基准」 | `ApplySettingsModal.tsx`、`api/apply.py`、`schemas/apply/config.py` |
| 侧栏可收起、批量操作卡（生成/导出两套参数） | `AppShell`/`BaseLayout`、`SettingsPage.tsx` |
| 更新检查与公告条（读上游 Release） | `services/update_check.py`、`useUpdateAnnouncement.ts`（上游 1.0.2 已有） |

## 3. 数据结构增量（相对上游 1.0.2）

| 增量 | 说明 | 2.0 处理 |
| --- | --- | --- |
| `apply_queue_item.greeting_confirmed` / `apply_task_item.greeting_confirmed` | 迁移 0069；历史行「有文案即已确认」回填 | 写成 2.0 基线后的新迁移 |
| `resume_generation_plan` 表 | 迁移 0070；匹配报告 plan_id | 同上 |
| `ai_job_link` 表 | 迁移 0075；岗位↔引擎映射 + 招呼语快照 | 同上 |
| `apply_task_item.failure_step/target/reason` | 失败三列（迁移 0073/0077） | 同上（2.0 已有 `X-Resume-Truncated` 等口径，注意对齐） |
| 失败分类字符串扩展（`greeting_unconfirmed` / `job_closed`） | 无迁移（纯字符串，允许值在代码里） | 直接带过去，改动小 |

> 本地库当前 head = `0075_ai_job_link`；`0076/0077` 文件存在但未落库（历史遗留）。
> 2.0 里不要试图「修链」，直接把需要的表/列写进 2.0 基线之后的新迁移。

## 4. 迁移路线

### 路线 A：功能移植到 2.0（推荐）

顺序（每步都能独立验收）：

1. **先建 2.0 基线**：用 2.0 源码 + 空库跑起来，确认本地环境（Python 3.12、Node、端口 8005）可用。
2. **数据结构**：把 0069/0070/0075 与失败三列改写成 2.0 基线之后的新迁移；跑 `alembic upgrade head` 与 2.0 的 schema 测试。
3. **投递台（不含 BOSS 适配器）**：队列/批次/失败分类/招呼语闸门/导出提示。用 `v2_gate.py` 与 `tests/test_apply_*` 做回归。
4. **BOSS 适配器**：`services/sites/boss_*` + `browser/interaction.py`（重点带上焦点仿真与页面装载等待）。用 `tests/test_apply_boss_adapter*`、`test_boss_apply*`。
5. **AI 求职 sidecar**：表 + 服务 + API + 前端页面；先只读（连接/状态/岗位池），再接任务与发送闸门。
6. **简历侧二开**：匹配报告/画像导入/去重/技术栈开关——这部分与 2.0 的 `profile_facts` 删除、`page_limit=0` 语义冲突最多，放最后。
7. **前端**：2.0 的导航/i18n/组件结构已变，按页面整体搬，不要逐文件 diff。

### 路线 B：并行运行

- 2.0 另建目录（例如 `简历通-2.0/`），端口改 8010/5174，数据目录独立；
- 本地 1.x 继续用；需要对比时两边都开；
- 不共享 `backend/data`（2.0 会归档旧库）。

## 5. 已知风险清单

1. **数据**：2.0 空库启动是设计，不是 bug；迁移前必须导出 1.x（`导出全部数据集`）或备份 `backend/data/resume_forge.db`。
2. **迁移链**：2.0 只认 epoch=2 的库；把 fork 的迁移文件直接拷进 2.0 会让启动闸门拒启。
3. **`page_limit=0`**：fork 里多处 `x or 1` 会把「不限」折成 1 页；移植时按 2.0 的 `x if x is not None else 1`。
4. **`profile_facts`**：2.0 删除；画像导入若依赖它，要改到 `claims`/资料条目。
5. **`PATCH /layout`**：fork 的版本是「全量替换」，只传一项会重置其它项（本次已用「传全量」规避）；2.0 已改成局部更新，移植时直接用 2.0 的。
6. **导出截断**：fork 的提示条件曾用被夹到上限的 `pages`（永不触发）；2.0 有 `X-Resume-Truncated`，直接接。
7. **BOSS 反自动化**：`visibilityState=hidden` 与「按钮在、处理器没绑」是两个真实故障；移植时两段修复（焦点仿真、等 `complete`）都要带，否则投递会回到「点了没反应」。

## 6. 验收命令

```bash
# 后端（在 backend/ 下，用项目 venv）
./.venv/Scripts/python.exe -m pytest tests/test_apply_*.py -q
./.venv/Scripts/python.exe -m pytest tests/test_boss_apply*.py tests/test_apply_boss_adapter*.py -q

# 前端
cd frontend && npm run typecheck && npx vitest run src/components/apply src/i18n
npm run build

# v2 单模型闸门（fork 专用）
python scripts/v2_gate.py --all
```

## 7. 近期修复（2026-11-05，移植时别丢）

1. 招呼语「有字未确认」独立成 `greeting_unconfirmed`；工具栏批量确认；开始投递前预检。
2. BOSS 点击前等 `readyState=complete`（修「处理器没绑」）；`Emulation.setFocusEmulationEnabled`（修 `hidden`）；「职位已关闭」软跳过。
3. 导出截断如实提示（`overflow` / `pages_needed`）；照片缩小以适配 1 页。
4. 队列编辑弹窗可查看岗位 JD。
5. 简历 52 重写为 2 页/1 页版本（内容改动，非代码）。
