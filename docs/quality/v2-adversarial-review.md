# v2 整改对抗性审查报告（2026-11-04）

> 审查对象：`83bd94d3`（Phase 0）/ `d1403544`（Phase 1）/ `e38502f2`（Phase 2）/ `f7df4afd`（Phase 3）。
> 方法：七条线索逐条写**可独立运行的探针**（一次性 python 脚本，放
> `C:\Users\Administrator\AppData\Local\Temp\v2-review\`），以真实输出判定，不以"读代码觉得"判定。
> 修复纪律：只修 P0；每修一个先写**能复现 bug 的失败测试**，再修实现，再跑闸门 1/2/3，单独提交。

## 0. 结论

| 级别 | 数量 | 内容 |
|---|---|---|
| **P0** | **1** | L1：Markdown/TXT 导出丢自建板块（Phase 3 新引入，**已修复**，提交 `62a0fc05`） |
| P1 | 1 | L5：基线 65 条失败中 6 条为推断非实测（不可事后复原，已改标注并补全量复跑实测名单） |
| P2 | 3 | L2 残留：闸门"后端无 hidden_sections 写入点"是**字面形态**检查（行为层面无新写入）；L4 残留：两个提交混入用户未提交改动（revert 时会连带）；L3 残留：document_converter 改动与 §3.1「只读（不改）」表述冲突（行为正确，属文档需修订） |

**Phase 0–3 能否算通过：能（修复 L1 后）**。闸门 phase 1/2/3 在修复后仍全绿；唯一确认的行为缺陷已修并带回归测试。

## 1. 审查方法

| 线索 | 探针 | 位置 |
|---|---|---|
| L1 | `probe_l1_custom_sections.py`：v1(含 custom:abc123) → v2，六出口导出对比 + `resolved_visible_sections` 白名单成员检查 | `%TEMP%\v2-review\` |
| L2 | 行为探针（inline）：`validated_format_config` 输出 / `persistable(validated(...))` / 全仓非下标写法 grep / 三个落库点静态核对 | 本报告 §2-L2 |
| L3 | `probe_l3_l6_backup.py`：**只读**打开 `pre-normalize-20261104-010845.bak`，23 条 v1 记录逐条跑"迁移路径(normalize_record)"与"读时转换(ensure_document_version)"，结果 JSON 逐字节比较 | 同上 |
| L4 | `git show --stat` + 逐文件 diff 概览 + 对照会话起点 `git status`（那批文件在我任何提交之前就是 modified 状态） | 本报告 §2-L4 |
| L5 | ① 定向复跑（前次已做：182 过/1 已知失败）② 17 文件集群复跑（281 过/1 已知失败）③ 全量复跑（后台，见 §2-L5） | `%TEMP%\v2-review\l5-cluster.log`、`pytest-full-rerun.log` |
| L6 | `probe_l3_l6_backup.py` 前半：备份库 vs 当前库的 skills 隐藏 id 清单 + 新增 11 条的原始 `format_config.hidden_sections`；文档口径检索（CHANGELOG / resume-document-model / 测试 docstring） | 同上 |
| L7 | `probe_l7_edges.py`：五个边界（空 content / 空 sections / 限量边界 / v2 幂等 / 重复 id） | 同上 |

## 2. 逐条结论

### L1 Markdown/TXT 丢自建板块

- 探针：`probe_l1_custom_sections.py`（v2 文档含 `custom:abc123`，正文关键词 `自建正文关键词XYZ`）
- 实测输出（修复前）：
  ```text
  custom_key in resolved_visible_sections({}) = False
  md  不传 section_order 含自建正文: True
  md  传 section_order   含自建正文: False   ← 丢
  txt 传 section_order   含自建正文: False   ← 丢
  html 含自建正文: True
  docx 含自建正文: True
  pdf 含自建正文(去空白): True
  export_pipeline.py:122 / :191 均传 section_order=resolved_visible_sections(...)
  ```
- 判定：**确认缺陷（P0，Phase 3 新引入）**。`resolved_visible_sections` 只含 12 个内置键，
  `custom:*` 永远不在清单里；Phase 3 新增的 `_apply_visible_sections` 按清单硬过滤，
  于是 **export_pipeline 的真实路径**（md/txt）丢自建板块而 html/docx/pdf 保留——四个出口
  不一致，正是 Phase 3 要消灭的 P3 复发形态。修复前生产调用点只有 `export_pipeline.py:120/189`
  两处传该参数（已 grep 全仓核实）。
- 严重级：**P0**。**已修复**（见 §3）。
- 修复后探针复跑：md/txt/html/docx/pdf 六出口全部含自建正文。
- 附注：线索里提到的 `experiences` 复数 key 在 v2 文档中不存在（converter 产出的一律是
  catalog 内置键），`dedupe_resume` 里的 `experiences` 别名只影响去重不影响导出，未构成缺陷。

### L2 闸门被"改写法"绕过

- 探针（inline，实测输出）：
  ```text
  validated 输出含 hidden_sections: True ['awards']
  persistable(validated(...)) = {}
  ```
- 非下标写法全仓 grep：唯一把 `hidden_sections` 写进输出 dict 的位置就是
  `resume_template_format.py:180` 的 `result.update({str(key): hidden})`（原 `result["hidden_sections"] = hidden`）。
- 行为判断（不看注释看调用链）：
  - `resume_record.py:190`：`validated_format_config(persistable_format_config(...))` —— persistable **先**剥离，落库值不可能带键；
  - `manual_creation.py:102`：记录的 `format_config=persistable_format_config(format_config)`（line 86 的 `validated` 产物只作为**转换器输入**，转换器读它是 §2.4 允许的"读取"）；
  - `layout_render_routes.py:104-105`：`validated_format_config(persistable_format_config(payload.format_config))` —— 同样先剥离。
  - 三个真实落库点全部先过 `persistable_format_config`，`persistable(validated(x)) == {}` 实测成立。
- 判定：**未复现（无新写入路径）**。`update()` 与原下标赋值行为逐字节相同，改动是行为中性的；
  闸门 `PASS 后端无 hidden_sections 写入点` 的语义强度确实从"该写入不存在"降级为"该**字面形态**不存在"
  ——这是检查器自身的局限（它本来也抓不到 `values["format_config"] = validated(...)` 这类间接写入）。
- 严重级：**P2**（记录，不修）：Phase 4 的 `check_v2_boundary.py` 应改为按**数据流**检查
  （落库点入参必须来自 persistable 之后的值），而不是 grep 赋值形态。

### L3 是否越界改 document_converter.py

- 探针：`probe_l3_l6_backup.py` 后半（备份库 23 条 v1 记录，`custom_fields=None` 两侧统一，对比路径一致性而非复刻历史）。
- 实测输出：
  ```text
  v1 记录共对比 23 条：mismatch = 0
  ```
- 判定：**未复现（改动必要且行为一致）**。
  1. 必要性：3 条预存量失败（test_resume_hidden_sections）以"v1 内容 + format_config 直传导出函数"为输入，
     四出口共用 coerce_document→converter，不存在第二个消费点；不加它测试无法转绿，旧导入/旧备份
     也会复活"藏了却显示"的状态。
  2. 契约：`_apply_hidden_sections` 只改**本次转换在内存中的文档**，不触碰任何存储；"读路径不写库"不变。
  3. 一致性：迁移路径与读时转换逐字节一致（0 mismatch）。
- 严重级：**P2（文档问题，非代码问题）**：§3.1 表的「只读（不改）」与 Phase 3 的转绿要求自相矛盾，
  已在方案文档 §9 冲突表记录；建议白天把该表那一格改成"只读（不改写入逻辑；Phase 3 允许加旧键读取）"。

### L4 提交混入不属于本阶段的改动

- 证据：会话起点的 `git status`（在我任何提交之前）已列出下列文件为 modified；我对它们**零改动**，
  是 `git add -A backend/app/services/resume/`（用户指令原文）与多打的
  `git add -u frontend/src/components/resume/`（我的失误）把它们扫进提交。
- e38502f2（Phase 2）里与"写路径收口"无关的**整个文件 diff**（内容为用户未提交的二开修复）：
  | 文件 | 规模 | 内容概要 |
  |---|---|---|
  | `resume_coverage.py` | +79 | `remaining_coverage_notes` 重构（覆盖清单收窄） |
  | `resume_tech_stack.py` | +71 | `_is_tech_stack_item` 等技术栈清理逻辑 |
  | `document_save.py` | ±10 | 保存边界小改 |
  | `document_html.py` | +3 | 小改 |
  | `resume_generation_levels.py` | +2 | 小改 |
- f7df4afd（Phase 3）里与"板块统一"无关的**整个文件 diff**（同为用户未提交的二开修复）：
  `ResumeCoverageNotes.tsx`(+29)、`ResumeDetailPreview.tsx`(+107)、`ResumeDetailPreview.test.tsx`(±4)、
  `WorkbenchParamsColumnV2.tsx`(+6)。
- 判定：**确认存在混入（P2）**。这些改动本身是这条分支 v2 工作的一部分（方案文档 §10.11 记录过的
  未提交修复），内容无损；风险在于**将来 revert Phase 2/3 会把用户这些修复一起回滚**。
- 不拆历史（按你的指示），精确清单如上；若将来需要 revert，用 `git revert -n <hash> -- <路径>`
  逐文件操作，避开上表文件，或先把它们 cherry-pick 出去。

### L5 基线 65 条失败中 6 条为推断

- 那 6 条（基线文档标"推断"者）：`test_api_datasets.py` ×4、`test_api_datasets_transfer.py` ×1、
  `test_api_sample_dataset.py::test_load_sample_creates_switches_and_seeds` ×1。
- 复现尝试与结果：
  1. 定向复跑这 6 条所在文件（7 文件，前次已跑）：**182 passed / 1 failed**（唯一失败是已知确定性的
     `test_resume_templates.py::test_preview_renders_html_and_style_config`）——6 条在隔离/小集合下全部通过；
  2. 17 文件 dataset 集群复跑（`%TEMP%\v2-review\l5-cluster.log`）：**281 passed / 1 failed（同上已知项）**——
     全量运行里的顺序依赖污染在子集里不复现；
  3. `pytest --lf` 不可用：首次全量的 lastfailed 已被后续定向运行覆盖，原运行输出被 tail 截断，
     那 5–6 行 FAILED 名目**不可事后复原**。
- 判定：**确认记录缺陷（P1）**：基线 §4 把 6 条推断条目写得与实测同格，违反"判据里不能有猜测"。
- 处置（不修代码，修文档）：基线 §4 已改写为——59 条实测名单 + "6 个失败名额无法留痕"的明确标注
  （候选池与两次复现尝试均记录在案）+ **2026-11-04 全量复跑的完整实测名单**（`pytest-full-rerun.log`，
  见 §3 后的补记）。失败集本身是顺序依赖的非确定集合，两次全量的并集才是真实预存量。

### L6 22 条 skills 隐藏的语义

- 探针输出（`probe_l3_l6_backup.py` 前半，只读）：
  ```text
  迁移前 hidden(skills) 的 id: [24,25,27,28,29,32,34,36,38,39,40]
  迁移后 hidden(skills) 的 id: [9,10,11,12,13,18,19,20,21,22,23, 24,25,27,28,29,32,34,36,38,39,40]
  本次新增: [9,10,11,12,13,18,19,20,21,22,23]
  新增这批在备份库里的 format_config.hidden_sections：11 条全部 = ['awards','campus_experience','skills']
  ```
- 文档口径（原始需求）：
  - `backend/tests/test_resume_hidden_sections.py` docstring：「用户口径：**被隐藏的板块就是不放进简历**，不是"仅预览隐藏"」；
  - `CHANGELOG.md`（v2 板块显隐条目）：「隐藏只写 `section.hidden=true`，正文数据仍保留，随时可以再打开；预览、PDF、Word、Markdown 共用 `paper_document` 这一处过滤器，不会出现"预览藏了、导出还在"」；
  - `docs/resume-document-model.md:235`：`hidden` = 「不上纸面，数据保留」。
- 判定：**未复现（语义正确，非 P0）**。迁移忠实消费了记录里真实存在的 `hidden_sections=['skills']`，
  而仓库内所有口径都写明该键的语义是"不进简历（全出口）"，不是"仅预览隐藏"。另：v1 时代该键
  从未生效过（P3），所以这 11 条记录的用户**从未见过**隐藏效果——迁移是第一次让保存的意图成真，
  与方案文档 Phase 1 的预告一致。数据事实已核对，若你仍怀疑个别记录的原始意图，唯一可靠依据
  是你自己的记忆，代码/文档层面没有"仅预览"口径存在过。

### L7 finalize_ai_document 边界

- 探针：`probe_l7_edges.py`。实测输出（前两轮失败是我 fixture 的 placement/kind/id 写错，
  修正后第三轮）：
  ```text
  == 1) 空 content {} ==                OK sections=[] header items=0
  == 2) 空 sections 数组 ==              OK sections=[]
  == 3) page_limit=1 但只有 1 个项目 ==   OK entries=1
  == 4) 合法 v2 两次调用 ==               OK 幂等 = True（逐字节相同）
  == 5) 重复对象 id ==                    OK 抛出 DocumentValidationError（projects.entries[1] 的对象标识重复：ob_proj000001）
  ```
- 判定：**未复现（五个边界行为全部正确）**：不崩、不产出非法文档、幂等成立、重复 id 走校验抛错
  而非静默修复。

## 3. 修复记录

| 缺陷 | 修复 | 提交 |
|---|---|---|
| L1（P0）：md/txt 白名单丢 `custom:*` | `_apply_visible_sections` 只对 `DEFAULT_SECTION_ORDER` 内置键做白名单，非内置 key 一律保留；新增回归测试 `test_markdown_visible_list_keeps_custom_sections`（先红后绿） | `62a0fc05` |

修复后验证：
- 回归：`test_section_visibility_exports.py + test_resume_hidden_sections.py + test_document_markdown.py + test_document_exports.py` = **32 passed**；
- L1 探针复跑：md/txt/html/docx/pdf 六出口全部含自建正文；
- 闸门：phase 1 `4 通过 / 0 失败`、phase 2 `5 通过 / 0 失败`、phase 3 `5 通过 / 0 失败`（无一转红）。

## 4. 未修项

| 项 | 级别 | 为什么现在不修 |
|---|---|---|
| L2：闸门"写入点"检查是字面形态级 | P2 | 行为层面无缺陷（三个落库点都先 persistable）；正确的修法是 Phase 4 的 `check_v2_boundary.py` 按数据流检查，属于 Phase 4 范围 |
| L4：两个提交混入用户未提交改动 | P2 | 拆分需重写历史（你明令禁止）；已给出精确文件清单与将来 revert 的规避方法 |
| L3：方案文档 §3.1「只读（不改）」表述与实现矛盾 | P2 | 代码行为正确且必要；改文档口径属白天决策，已在 §9 冲突表挂账 |
| L5：基线 6 条推断不可复原 | P1 | 已改文档标注 + 全量复跑补实测名单；再花 45 分钟追原始名单不可行（输出已截断） |

## 5. 结论：Phase 4/5 能不能开始

**能**，前置条件已满足：
1. 唯一 P0（L1）已修复并带回归测试，闸门 1/2/3 全绿；
2. P1/P2 均为记录项，不阻塞 Phase 4；其中 L2 直接给出了 Phase 4 `check_v2_boundary.py` 的设计要求：
   **按数据流（落库点入参来源）检查，不要按赋值形态 grep**——否则下一个 `update()` 写法照样绕过。

建议顺序不变：卡 4（静态守卫）→ 卡 5（同形不变量 + 回归包）→ 卡 6（runbook）。

---

## 补记：2026-11-04 全量复跑实测名单（L5 处置的第三步，已回填）

复跑：**61 failed / 7654 passed / 105 skipped / 1 xpassed（45:03）**（首次 65 failed / 7634 passed；
passed 差值含当天新增的 17 条 Phase 4/5/回归测试）。与首次名单对比：

- **两次都失败（稳定预存量）54 条**；
- **仅复跑失败 7 条**：`test_api_datasets.py` ×4、`test_api_datasets_transfer.py` ×1、
  `test_api_sample_dataset.py::test_load_sample_creates_switches_and_seeds` ×1
  ——**L5 的 6 条推断全部被复跑实测证实**（第 7 条是 `test_lease_release_is_idempotent` 的
  pytest 短摘要截断变体，与首次同名）；另有 `test_resume_templates.py::test_preview_renders_html_and_style_config`
  与 `test_resume_sample_content.py[split-small]` 等确定性失败两次均在；
- **仅首次失败、复跑通过 5 条**：`test_resume_hidden_sections.py` ×3——**Phase 3 修复后在全量
  环境下转绿**（预存量清单上的完成标志兑现）；`test_qa_browser_sites_adversarial.py` ×1（顺序依赖波动）。

结论：预存量失败集是顺序依赖的非确定集合，**两次全量的并集（约 60 条）才是真实预存量**。
基线文档 §4/§5 已按此更新（推断条目转实测、附对比与用法口径）。
原始名单：`%TEMP%\v2-review\rerun-failed.txt`（61 行）/ `run1-failed.txt`（59 行）；复跑日志
`pytest-full-rerun.log`（临时目录，不入库）。
