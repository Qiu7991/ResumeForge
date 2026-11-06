# N8 简历侧 · 对抗审查报告（R7）

> 分支 `feat/resume-side` · 审查对象：R2 去重 / R3 技术栈开关 / R5 画像导入 / R4 覆盖清单
> 口径：每条给「攻击方式 → 观察到 → 判定 → 证据」。**A/B 两类必须全 PASS**；
> C/D 至少各有一条 PASS 证据。
> **未修改任何被测代码让审查通过**（唯一一次改动是 B③ 打出真实缺口后修实现，
> 并补了一条回归测试锁定它——见 B③）。

## 结论

| 类 | 攻击点 | 结果 |
|---|---|---|
| **A 去重误删** | 3 种数据 | **3/3 PASS** |
| **B 技术栈泄漏** | 3 条写路径 + 开关打开对照 | **4/4 PASS**（其中 B③ 首轮 **FAIL** → 已修） |
| C 画像导入污染 | 对账 / 重复 / 覆盖 | **3/3 PASS** |
| D 覆盖清单补全 | 补 A 不误加 B / 复发 | **2/2 PASS** |

---

## A 类：去重误删

攻击：造三种数据喂给 `resume_dedupe.dedupe_resume`。

| # | 攻击方式 | 观察到 | 判定 |
|---|---|---|---|
| A① | 同一项目写两遍（`AI 简历工作台` 一条带 description、一条带 highlights） | `2 → 1`，`names=['AI 简历工作台']` | **PASS**：只留一条 |
| A② | 内容相似但不同（`CreatorDistill 创作者内容分析系统` vs `CreatorDistill 爆款拆解语料库`，共享品牌名） | `2 → 2` | **PASS**：都保留（不做模糊判断） |
| A③ | 用户手动加的条目（`name` 为空白的半成品）+ 一条正常条目 | `2 → 2`，`names=['', '正常项目']` | **PASS**：不删 |

原始输出：

```
===== A 类：去重误删 =====
① 两条完全相同: 2 → 1  names=['AI 简历工作台']
② 内容相似但不相同: 2 → 2  names=['CreatorDistill 创作者内容分析系统', 'CreatorDistill 爆款拆解语料库']
③ 用户手动加的条目（无身份）: 2 → 2  names=['', '正常项目']
```

补充证据（E15 / 不截断，来自 `tests/test_resume_dedupe.py::test_dedupe_does_not_truncate_quantity`）：
8 个项目 + 6 条经历输入，全部无重复 → 输出仍是 8 / 6。

```
$ pytest tests/test_resume_dedupe.py -q  → 6 passed
```

**判定：A 类全 PASS。**

---

## B 类：技术栈泄漏（开关关闭时）

攻击：在开关为 `False` 的状态下，走三条不同的写路径，然后在**读回**（GET 详情）的内容上
统计"会上纸面的技术栈项"。

| # | 写路径 | 观察到的可见技术栈项 | 判定 |
|---|---|---|---|
| B① | AI 生成（`resume_record.save_record`，SSE 与后台 runner 共用） | **0** | **PASS** |
| B② | 手工保存（`PUT /api/resumes/{id}/content` → `document_save.save_content`） | **0**（status 200） | **PASS** |
| B③ | 手写/底稿创建（`POST /api/resumes/manual` → `create_manual_resume_record`） | **0**（status 201） | **首轮 FAIL → 已修 → PASS** |
| B④ | 对照组：开关**打开**后同样走 B③ | **1**（保留） | **PASS**（说明不是"无条件删"） |

原始输出：

```
偏好: {'show_tech_stack': False}
① AI 生成 (save_record): 0
② 手工保存 PUT status: 200
② 手工保存 可见技术栈: 0
③ 手写创建 status: 201
③ 手写创建 可见技术栈: 0

偏好: {'show_tech_stack': True}
开关打开 → 手写创建可见技术栈: 1
已复原: {'show_tech_stack': False}
```

### B③ 的 FAIL 与修复（本轮唯一一次改实现）

**攻击方式**：新建一份手写简历（`source="manual"`, `draft=true`），内容里带
`tech_stack: ["React","FastAPI"]`。

**首轮观察到**（修复前直接探测）：

```
manual_creation 引用 strip_resume_tech_stack: False
manual_creation 引用 show_tech_stack: False
manual_creation 走 save_content: False
转换后（未 strip）可见技术栈项: 1
tech_stack item placement: ['trail']        ← 会上纸面
```

**根因**：`create_manual_resume_record` 走 `_validated_content` →
`prepare_document_for_save_with_report`，**不经过** `document_save.save_content`
（后者是给"已存在记录"的 PUT 用的）。R3 的挂点只覆盖了 save_content，漏了创建路径。
1.x 也有同样缺口（`manual_creation.py` 里 0 处 `include_tech_stack`）——这不是移植错误，
是两边都有的洞，被本轮审查打出来了。

**修复**（`backend/app/services/resume/manual_creation.py::_validated_content`）：
转换完成后读偏好，关闭则 `strip_resume_tech_stack(content)`。方向与其它路径一致
（只隐藏 `placement=hidden` + `hidden_from="trail"`，不删 `values`）。

**修复后观察到**：

```
③ 手写创建 status: 201
③ 手写创建 可见技术栈: 0
```

读回内容里技术栈项仍在，只是隐藏：

```json
{"kind":"list","key":"tech_stack","label":"","values":["React","FastAPI"],
 "hidden_values":[],"placement":"hidden","hidden_from":"trail"}
```

**回归测试**：`tests/test_tech_stack_preference.py::test_manual_creation_strips_tech_stack_when_off`
（走真实 HTTP `POST /api/resumes/manual`，断言 `visible_tech_stack_count == 0` 且
数据仍在 `placement == "hidden"`）。

**判定：B 类 4/4 PASS**（含这次 FAIL→修→PASS 的完整证据链）。

> 说明：计划卡 R7 原文的第三条路径是「底稿模式」。2.0 **没有**底稿模式
> （`base_resume_id` 在 2.0 schema 里不存在，`grep` 0 命中；那是 1.x 独有功能，
> 见 `docs/fork-2.0-resume-baseline.md`）。因此取 2.0 现状下最接近的第三条路径
> ——手写/底稿创建（`source=manual` + `draft`），并把 1.x 的 `resume_tech_stack.py`
> 里"v2 文本项里的「技术栈/工具：」行"用例一并纳入测试
> （`test_strip_cleans_v2_text_items_with_tech_stack_lines`）。

---

## C 类：画像导入污染（只 dry-run，未 apply）

### C① 对账准确（5 个项目）

| 项 | 观察到 | 判定 |
|---|---|---|
| 源行数 | 摘要 `{"projects": 5, "experiences": 0, "skills": 0}` | **PASS** |
| 预计写入 | 新增 5 条，逐条列出：项目一~项目五 | **PASS** |
| 跳过原因 | `skipped_claims: []`、`education_skipped` 空 | **PASS** |
| 等级映射 | A→已确认 / B→已确认 / C→**不采用** / 空→待确认 | **PASS** |
| 承担程度 | 原样保留（负责模块 / 参与 / 项目负责人 / 主导方案或交付） | **PASS** |
| sources 带 entry_id | `True` | **PASS** |
| dry-run 零写入 | 计划前后 `profile_entry` 项目条目数 `0 → 0` | **PASS** |

```
源项目数: 5 | 摘要: {"projects": 5, "experiences": 0, "skills": 0}
预计新增资料条目: 5 → ['项目一', '项目二', '项目三', '项目四', '项目五']
预计更新已有条目: 0
预计新增事实: 5 | 跳过: []
承担程度/A-C 映射: [('项目一 · ', '已确认', '负责模块'), ('项目二 · ', '已确认', '参与'),
                   ('项目三 · ', '不采用', '参与'), ('项目四 · ', '已确认', '项目负责人'),
                   ('项目五 · ', '待确认', '主导方案或交付')]
sources 带 entry_id: True
dry-run 前后项目条目数: 0 → 0（必须相等）
```

### C② 不产生重复条目

`plan_portrait` 按 `(category, 规范化 subject, 规范化 title)` 判重，
且资料条目按身份名 + 包含式匹配（`_find_entry(..., allow_contains=True)`）合并。
实测：库里已有同名项目时，计划把它们归到 `updated` 而不是 `created`
（见 C③ 的 `更新计数: ['项目一']`）。

### C③ 不覆盖已有描述

攻击：先造一条"用户手改过 description"的项目，再拿一份同名但 description 不同的画像去计划。

```
已有条目: 15ea38592db94ce79f689fdc | description = 用户手改过的描述——导入不许覆盖它。
计划写入的 description = 用户手改过的描述——导入不许覆盖它。
是否保住了用户原描述: True
空字段是否被补上（highlights）: True
更新计数: ['项目一']
已回滚（读取库后未写）
```

**PASS**：只补空字段，用户改过的描述一个字没动。（该探测在事务里做，最后 `rollback()`，
库里没有留下这条测试条目。）

**判定：C 类 3/3 PASS。全程只 dry-run / 只 rollback，未执行 `--apply`。**

---

## D 类：覆盖清单补全

### D① 补 A 成功且不误加 B / 补完即更新

用 2.0 既有的确定性补入链路（`POST /api/resumes/{id}/append-profile-entries`），
逐条对上卡片要求的三个期望：

| 期望 | 覆盖它的既有测试 | 结果 |
|---|---|---|
| 补 A 成功且内容正确（逐字落库） | `test_append_creates_section_and_writes_verbatim_text` | passed |
| 只补点名的条目，不动其它分区 | `test_append_keeps_other_sections_and_clears_warnings` | passed |
| 补完立即生效、重复点不产生第二条 | `test_append_twice_skips_and_does_not_bump_revision` | passed |
| 生成时已写过的条目不再重复补 | `test_append_skips_entry_already_written_by_generation` | passed |

```
$ pytest tests/test_append_profile_entries.py -q -k "creates_section or keeps_other or twice_skips or already_written"
4 passed, 10 deselected
```

"不误加 B" 的口径由 `test_append_keeps_other_sections_and_clears_warnings` 与
`test_append_twice_skips_*` 共同锁定：请求只带 A 的 entry_id，B 不会被顺带写进正文；
补过的条目在第二次请求里进 `skipped` 而不是再写一遍。

### D② 补入后技术栈不复发（1.x 点名的复发路径）

攻击：一份技术栈已隐藏的简历，把带 `placement=trail` 技术栈的文档再次落库
（模拟"从资料补上这段"把资料原值 clone 进正文的路径）。

```
开关: {'show_tech_stack': False}
创建后可见技术栈: 0
（未过滤时这份内容可见技术栈: 2 ）      ← 落库前的输入确实带着 2 项 trail 技术栈
save_content 后 status: 200
save_content 后可见技术栈: 0 （必须 0）
```

**PASS**：`save_content` 里的技术栈兜底把补入路径也覆盖了——"生成时藏好了 → 补一段 →
又露出来"这条复发路径被堵住。

**判定：D 类 2/2 PASS。**

---

## 审查期间发现并处置的问题汇总

| # | 问题 | 严重度 | 处置 |
|---|---|---|---|
| 1 | B③ 手写/底稿创建路径绕过技术栈开关（1.x 同样存在） | **中**（用户可见：新建手写简历技术栈照样出现） | 已修 `manual_creation._validated_content` + 回归测试 |
| 2 | 计划书把画像导入目标写成 `profile_facts`，实际 1.x 写的是 `ClaimRecord` | 文档偏差 | 已在 baseline / progress / R5 记录，按代码为准 |
| 3 | 计划书 R7 的「底稿模式」在 2.0 不存在 | 文档偏差 | 第三条路径改用 2.0 现状的"手写/底稿创建" |
| 4 | 内置分区（项目/经历）缺条目时只能走 AI 修订 | 低（交互差异） | DEFERRED-3，未移植 |

## 未做的事（明确声明）

- 未执行 `import_portrait.py --apply`（计划 §9.4；真数据迁移留人工）。
- 未修改任何测试断言使审查通过。
- 未修改 `scripts/fork_gate.py`（phase_9 建好之后一个字未动）。
