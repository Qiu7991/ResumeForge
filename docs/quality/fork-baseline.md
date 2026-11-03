# v2 整改基线（2026-11-03 深夜采集）

> 本文档由 Phase 0（基线固化与备份）生成。
> 后续任何阶段出现测试失败，先与第 4 节对照：**已在此列的算预存量，不在的算本次引入。**

## 1. 环境

| 项 | 值 |
|---|---|
| 分支 | `fix/v2-single-model`（自 `feat/ai-jobs-sidecar-20261102` @ `93913237` 切出，携带未提交二开改动） |
| HEAD 短哈希 | `93913237` |
| Python | 3.12.10（`backend/.venv`） |
| Node | v24.18.1 |
| 数据库 | `backend/data/resume_forge.db`，123,387,904 字节 |
| journal_mode | `wal` |
| integrity_check | `ok` |
| 备份文件 | `backend/data/resume_forge.db.pre-v2-normalize-20261103-235326.bak`（`integrity=ok`，`resume_record=40`，由 `v2_gate.py --backup` 的 SQLite backup API 生成，非 cp） |

## 2. 后端

### alembic
- `heads: ['0075_ai_job_link']`（单头 ✓）
- 迁移目录：`backend/migrations/versions`，共 77 个文件

### 迁移文件前缀重复清单

| 前缀 | 文件 |
|---|---|
| `0069` | `0069_apply_greeting_confirm.py`、`0069_profile_field_placement.py` |
| `0070` | `0070_failure_taxonomy.py`、`0070_resume_generation_plan.py` |

其余 75 个文件前缀唯一；`revision` 字符串本身唯一，alembic 正常工作。

### 版本分布（`resume_record.content.version`）

| 范围 | v1 | v2 |
|---|---|---|
| live（`deleted_at IS NULL`） | **9** | **3** |
| 含软删（全量 40 条） | **23** | **17** |

- 损坏 JSON：0（全量 `json.loads` 通过）
- `format_config` 列含 `hidden_sections`：**12 条**（live 6：id 9–13、24；软删 6：id 18–23），值均为 `['awards','campus_experience','skills']`
- `content` JSON 内部不含 `format_config`（它在独立列里）

### pytest 全量

- 结果：**65 failed / 7634 passed / 105 skipped / 1 xpassed**（2689.77s ≈ 44:49）
- 失败清单逐条见第 4 节。
- 交叉验证：另跑了一次 `pytest -q --lf --tb=line`（56 条选中）：**11 failed / 45 passed**。
  - 45 条"全量中失败、隔离复跑通过"的属**测试间状态污染导致的顺序依赖失败**（集中在 dataset 作用域系列）；
  - 11 条隔离运行也失败的为**确定性失败**（名单与真实报错见第 4 节）。

## 3. 前端

| 命令 | 结果 |
|---|---|
| `npm run test` | Test Files：7 failed / 641 passed（648）；Tests：**33 failed** / 4605 passed / 1 skipped（4639） |
| `npm run typecheck` | **通过**（`tsc --noEmit` 无输出） |
| `npm run lint` | **0 errors / 14 warnings** |
| `npm run build` | **成功**（built in 1.06s，仅 chunk 体积警告） |

前端失败清单见第 4 节（共 33 条）。完整原始日志在 `frontend/runtime/vitest-baseline.log`（去 ANSI 版 `vitest-baseline-clean.log`，本地文件，不入库）。

## 4. 预存量失败清单

> 后续任何阶段出现失败，先来这里对照：已在此列的算预存量，不在的算本次引入。
>
> ⚠️ **来源与口径说明（待人工判断）**：这 65 条后端失败全部是分支起点的预存量，不是 v2 整改引入。
> 全量运行的输出经过 tail 截断，65 条中 59 条有名目；其余 **6 条**按执行顺序位置（summary 头部被截）与 pytest
> 缓存交叉比对推断为表中"（推断）"标记的三组，单独复跑均通过，属顺序依赖失败，**具体归属待人工判断**。
> 另有 8 条 pytest 缓存遗留条目**不计入本次 65**（上一次会话遗留或本轮被 skip）：`test_apply_browser_manager.py ×1`、
> `test_resume_template_store.py ×2`、`test_resume_templates.py ×4`（本文件另有 1 条在 65 内）、
> `test_resume_generate_base.py ×1`（该文件已删除，纯陈旧缓存）。如后续看到它们失败，同样按预存量对照。

### 后端（65 条）

**确定性失败（11 条，`--lf` 隔离复跑仍失败，报错为实测原文）**

| 测试文件 | 测试名 | 失败原因（一句话） |
|---|---|---|
| tests/test_assistant_prompt_budget.py | test_worst_case_prompt_estimate_stays_bounded | 系统提示固定成本回涨到 23836 字符（应 ≤ 23800） |
| tests/test_candidate_import.py | test_import_falls_back_to_default_job_type_when_candidate_has_none | job_type 缺省回退得到「社招」，断言期望「校招」 |
| tests/test_file_size_budget.py | test_production_files_stay_under_line_budget | 12 个生产文件超过 500 行预算（api/apply.py=526、api/jobs.py=590、generation_plan.py=613 等） |
| tests/test_preflight.py | test_every_prompt_loaded_by_code_is_covered_by_the_checklist | generation_plan.md 未纳入提示词完整性检查清单 |
| tests/test_preflight.py | test_prompt_files_in_the_repository_are_all_listed | generation_plan.md、portrait_extract.md 没进完整性清单 |
| tests/test_qa_browser_sites_adversarial.py | test_frontend_production_code_has_no_hardcoded_site_names | 前端写死「boss直聘/直聘」（types/job.ts、JobTable.tsx、JobFilterBar.tsx 共 6 处） |
| tests/test_resume_hidden_sections.py | test_html_preview_omits_hidden_sections | P3 证据：隐藏板块「校园经历」仍出现在 HTML 预览（转换器不读 hidden_sections） |
| tests/test_resume_hidden_sections.py | test_markdown_and_txt_omit_hidden_sections | P3 证据：同上，Markdown/TXT 出口仍出现 |
| tests/test_resume_hidden_sections.py | test_word_document_omits_hidden_sections | P3 证据：同上，Word 出口仍出现 |
| tests/test_resume_sample_content.py | test_each_template_fits_one_page_and_is_mostly_full[split-small] | split/small 模板一页填充率 63.8%（断言下限 0.65） |
| tests/test_resume_templates.py | test_preview_renders_html_and_style_config | 模板预览渲染失败：'resume' is undefined |

**顺序依赖失败（48 条，`--lf` 隔离复跑通过；根因均为数据集作用域/租约/切换的状态污染，P6 集群）**

| 测试文件 | 条数 | 失败原因（一句话） |
|---|---|---|
| tests/test_collection_archive.py | 15 | 集合包导出/校验和/恢复受数据集激活状态污染（15 条：export_all ×2、roundtrip、lists_counts、tampered/missing/all_broken/nested、legacy、old_collection ×4、malformed、restored_survive） |
| tests/test_dataset_scope.py | 11 | 数据集租约/切换互斥状态污染（held_lease、acquire_lease、lease_release、frozen_session、failed_preview、missing_target、rows_isolated、concurrent_switches、apply/job_match/resume_generate runner ×3） |
| tests/test_dataset_scope_stream.py | 5 | SSE 流租约状态污染（assistant_stream ×2、sse_generate ×3） |
| tests/test_dataset_activation_compensation.py | 3 | 数据集激活补偿状态污染（failed_switch_retry、recovery_pointer、adopt_engine） |
| tests/test_dataset_request_identity.py | 3 | 请求作用域身份状态污染（stale_tab、scope_before_a_b_a、scope_mismatch） |
| tests/test_api_sample_dataset.py | 3 | 样例数据集加载/切换受数据集状态污染（idempotent、older_seed、never_touches） |
| tests/test_assistant_proposals_endpoint.py | 2 | A/B 数据集切换后 proposal 状态污染（stale_proposal、other_scope） |
| tests/test_qa_adversarial_20261019.py | 2 | 集合导入路径穿越拒绝用例受状态污染（traversal_entry、traversal_member） |
| tests/test_backup_active_main_compatibility.py | 1 | 导出全部 roundtrip 受激活数据集指针状态污染 |
| tests/test_career_scenarios.py | 1 | scenario id 按数据集解析受切换状态污染 |
| tests/test_task_start_dataset_race.py | 1 | 任务提交与 runner 启动的数据集竞态受状态污染 |
| tests/test_w21_dataset_offline.py | 1 | inflight 请求阻塞切换用例受状态污染 |

**首次未能留痕、后经 2026-11-04 复跑实测证实的 6 条（对抗审查 L5 闭环）**

> 首次全量的输出被 tail 截断，65 条中 59 条有完整名目，其余 6 个失败名额当时按执行顺序
> 位置 + 缓存交叉比对推断（见下方候选表）。2026-11-04 全量复跑（61 failed / 7657 passed）
> 的实测名单**恰好包含这 6 条**——推断转实测，预存量定性成立。

| 测试文件 | 条数 | 失败原因（一句话） | 复跑实测 |
|---|---|---|---|
| tests/test_api_datasets.py | 4 | 数据集激活/切换全局状态泄漏（activate、created_and_activated、delete_refuses、writes_not_leak） | ✓ 复跑仍失败 |
| tests/test_api_datasets_transfer.py | 1 | 数据集 round-trip 迁移受状态污染（preserves_every_kind） | ✓ 复跑仍失败 |
| tests/test_api_sample_dataset.py::test_load_sample_creates_switches_and_seeds | 1 | 样例数据集建立+切换+播种受状态污染 | ✓ 复跑仍失败 |

## 5. 2026-11-04 全量复跑补记（对抗审查 L5 的第三步）

- 结果：**61 failed / 7654 passed / 105 skipped / 1 xpassed（45:03）**（首次：65 failed / 7634 passed）。
  注：passed 数还包含 11-04 白天新增的 17 条 Phase 4/5/回归测试。
- 与首次全量的名单对比：
  - **两次都失败（稳定预存量）54 条**；
  - **仅复跑失败 7 条**：即上表 6 条（推断转实测）+ `test_dataset_scope.py::test_lease_release_is_idempotent`
    的截断变体（与首次同名，pytest 短摘要截断造成字符串不同，实为同一条）；
  - **仅首次失败、复跑通过 5 条**：`test_resume_hidden_sections.py` ×3（**Phase 3 修复生效，全量转绿**）、
    `test_qa_browser_sites_adversarial.py` ×1、`test_dataset_scope.py::test_lease_release_is_idempotent` ×1（同上截断变体）。
- 结论：预存量失败集是**顺序依赖的非确定集合**，两次全量的**并集（约 60 条）**才是真实预存量；
  单次名单只能当快照。判据用法不变：先查本表与两次名单的并集，不在并集里的才算本次引入。
- 完整实测名单：`%TEMP%\v2-review\rerun-failed.txt`（61 行）与 `run1-failed.txt`（59 行）；
  复跑原始日志 `pytest-full-rerun.log`（本机临时目录，不入库）。

### 前端（33 条）

| 测试文件 | 测试名 | 失败原因（一句话） |
|---|---|---|
| src/pages/ProfilePage.test.tsx | （13 条，见下方根因） | 页面渲染即崩：`api/profile` 的 vi.mock 未定义 `getGenerationPreferences` 导出 |
| src/pages/ProfilePage.webform.test.tsx | （7 条，同上根因） | 同上 |
| src/pages/ProfilePage.webform.customFields.test.tsx | （7 条，同上根因） | 同上 |
| src/pages/ResumesPage.generalEntry.test.tsx | 「AI 生成」打开通用简历生成弹窗（job=null），不改动列表筛选 | 元素断言失败（Unable to find role=tab 等） |
| src/pages/ResumesPage.generalEntry.test.tsx | 场景建议卡只提供入口，不按场景过滤已有简历 | 同上 |
| src/i18n/cjkRatchet.test.ts | src 的含 CJK 行数不超过基线 | 含 CJK 行数超过 ratchet 基线（'Legacy total increased'） |
| src/i18n/cjkRatchet.test.ts | tests 的中文 ByText 断言行数不超过基线 | 同上（tests 目录） |
| src/theme/antdDeprecatedProp.test.ts | 业务代码里没有 Alert message= / notification message: / btn: | 使用了 antd @deprecated 文案属性 |
| src/theme/inlineColorGuard.test.ts | style={{...}} 里不写死颜色（例外逐条登记） | 内联样式写死颜色未登记例外（GenerationPlanStage.tsx border/borderLeft、ProfileGenerationPreferences.tsx 等 4 处） |

ProfilePage 系列的 27 条具体测试名（根因相同，均为 `getGenerationPreferences` mock 缺失导致渲染崩溃）：

- ProfilePage.test.tsx（13）：默认显示简历资料，切换后显示独立的网申资料板块 / 原有网申字段并入统一的网申资料板块 / 切换资料分页不会丢失当前编辑状态 / 表单有更改后挂上 beforeunload 监听，刷新/关闭不再静默丢稿 / 保存全部成功后移除 beforeunload 监听 / 非编辑态下条目的日期选择框跟随表单禁用 / 默认展开每个分区，点标题可收起 / 「全部收起」一键收回，再点「全部展开」一键展开 / 挂载后注册编辑入口，点它等同于点页头的「编辑资料」 / 进入编辑态后注销，取消编辑也不再弹回来（点过就算提醒过了） / 关掉之后本次进入不再注册 / 离开这一页（卸载）时注销，回来才会重新提醒 / 打字不再重渲整页，也不再重渲简历资料的日期字段
- ProfilePage.webform.test.tsx（7）：渲染出「网申资料」区块，并说明它不进简历 / 查看态只显示已填的项，不铺一屏空标签 / 敏感项不显示「只存本机」标签 / 编辑态所有字段都可输入（含空的那些） / 简历资料校验失败时不提交网申资料，页面停在编辑态并给出提示 / 全部合法时保存成功并退出编辑态 / 保存全部资料时，网申资料也跟着存一次
- ProfilePage.webform.customFields.test.tsx（7）：编辑态可以新增自定义网申字段并随资料一起保存 / 编辑态可以修改自定义字段名并保留原值 / 删除自定义字段后不会再提交它 / 可新增多条教育补充记录，删除后按剩余顺序保存 / 新增自定义字段不会冲掉还没保存的多条记录 / 先点编辑资料、之后才打开网申资料，取消一次后仍能正常提交 / 编辑置脏时挂上悬浮球保存桥，保存成功后收起
