# 简历通二开分支 · v2 单模型兼容性整改开发文档

> 交付对象：接手本项目的开发模型/工程师（**主用 GLM-5.3-flash，见第 0.2 节执行协议**）
> 版本：2026-11-03 **第二版**（第一版经对抗性审查后重写，修订项见第 12 章）
> 当前分支：`feat/ai-jobs-sidecar-20261102`
> 适用范围：`D:\飞牛文件同步\工作\简历通`（ResumeForge 本地二开版）
> 文档性质：**实施方案 + 机器闸门 + 二开功能台账**。请按阶段执行，不要跳步。

---

## 0. 给接手者的第一段话

这个仓库不是“上游原版”，而是“上游 ResumeForge + 本地二开功能”的合并分支。上游在 2026-10-30 把简历内容模型从 v1 换成了 v2，而本地二开功能大多是在 v1 时代写的。合并后出现的大量“修了又坏”的问题，根因不是某一个 bug，而是：

> **同一个功能存在两条数据路径：一条走 v1，一条走 v2；一条有后处理，一条没有。**

本整改的目标不是继续给 v1/v2 写兼容层，而是：

> **让 v1 只存在于“导入 / 备份恢复 / 旧文件”这一条离线转换路径；应用运行时只认 v2。**

### 0.1 三条必须先记住的结论（第一版文档写错的地方）

第一版文档有三处判断会导致整改失效，**已经在本版正文中改正**，这里先点出来，避免你按旧结论动手：

1. **“`save_record` 是唯一写入口”是错的。** `generate_routes.py` 会给它传 `document=`，落库用的是**后处理之前**构造的那份文档，去重/技术栈清理全部被跳过。已实测复现。
2. **校验必须放在流水线的最后一步，不是第一步。** 先 `parse_document` 再合并，会产出超过 schema 上限的文档（实测 1000 > 500）。
3. **Phase 1 会让“隐藏板块”第一次真正生效。** 转换器根本不读 `hidden_sections`，现在四个导出的纸面上那些板块一直都在。迁移后它们会真的消失——这是修对了，但是**用户可见的内容变化**，必须逐条确认。

### 0.2 执行协议（面向 GLM-5.3-flash，必读）

便宜模型做这种整改，最大的风险不是“不会写代码”，而是**自由发挥**：重命名、顺手重构、把“看起来冗余”的守卫删掉、把测试改成通过、声称跑过但没跑。下面的协议就是为压制这四类行为设计的。**每一条都是硬性的。**

| 编号 | 规则 | 原因 |
|---|---|---|
| E1 | **每阶段开始先跑闸门**：`backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase N`。只修 FAIL 行，不修 PASS 行。 | 把“做什么”从自然语言变成待办列表，模型不需要判断优先级。 |
| E2 | **一次只改一个阶段**，阶段内**一次只改一个文件**，改完立刻跑该阶段的闸门。闸门不全绿不许进入下一个文件。 | 便宜模型的长上下文容易串味，改动越少回归越少。 |
| E3 | **禁止重命名、禁止搬文件、禁止“顺手清理”**。见到重复代码可以在执行记录里写一行“疑似可合并”，但不要动手。 | 改名会让 `grep` 类守卫、i18n key、测试 mock 路径同时失效。 |
| E4 | **禁止修改测试断言使其通过**。测试失败只有两条合法出路：修实现，或在“执行记录”里写明“该测试断言与本文档第 X 条冲突，需人工裁决”并 `pytest.mark.skip(reason=...)`。 | 把测试改绿是这类任务最隐蔽的失败方式。 |
| E5 | **禁止 `git reset --hard` / `git checkout .` / `git clean -fd` / `git stash drop`**。开始前先 `git status`。 | 工作树里有未提交的二开修复（见第 10 章第 11 条）。 |
| E6 | **不确定就以代码为准并停下来问**。本文档与代码冲突时，在“执行记录”里写明冲突点，**不要自行二选一**。 | 第一版文档有 6 处与代码不符（已修正），说明这类文档必然有偏差。 |
| E7 | **每个阶段结束**：跑闸门 → 把闸门输出贴进第 9 章“执行记录” → 单独提交。提交信息前缀 `fix(v2)/refactor(v2)/test(v2)/docs(v2)`。 | 便于回滚到“最后一个绿的状态”。 |
| E8 | **不要一次读完整个仓库**。每阶段只读该阶段“前置阅读”列出的文件（≤ 4 个）。 | 上下文预算要留给代码本身，不是文档。 |

**闸门脚本已就绪**：`scripts/v2_gate.py`（只读，不写库）。它把本文档里所有能机器判定的验收标准固化成了 `PASS/FAIL/SKIP` 行。你的工作就是让它变绿。

```bash
# 仓库根执行
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 0
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --all    # 全部阶段
```

---

## 1. 背景与已确认事实（2026-11-03 实测）

### 1.1 上游合并规模

- 合并提交：`f08418b5 Merge remote-tracking branch 'origin/main' into sync/upstream-full-20261101`
- 文件变更：**1154 个文件，+79163 / −64432**（已核对 `git show --stat`）
- 两侧提交：上游 21 个，本地二开 28 个
- 合并方式：一次性“大爆炸式”对齐，不是小步同步

### 1.2 当前数据现状（实测，可复核）

| 指标 | 数值 | 复核方式 |
|---|---|---|
| `resume_record` 未删除 | **12 条**（v1 **9** / v2 **3**） | `select version, count(*) … where deleted_at is null` |
| 含软删全量 | **40 条**（v1 **23** / v2 **17**） | 同上，不加过滤 |
| 损坏 JSON | 0 | `json.loads` 全量 |
| 带 `format_config.hidden_sections` | **12 条**（v1 记录，迁移后应清零） | 遍历 `format_config` |
| 迁移目录 | 文件名前缀 `0069`/`0070` 各重复两次；`revision` 字符串唯一；`alembic heads` = `['0075_ai_job_link']` | `scripts/v2_gate.py --phase 4` |
| 直接读 `(record\|resume\|row\|current).content` | **40 处 / 28 个文件** | `grep -rnE` |
| 其中“按 v1/v2 形状取键”的危险写法 | **0 处** | `grep -rnE '\w+\.content(\[|\.get\()'` |
| 前端引用 `ResumeContent` | **293 处 / 85 文件**（非测试 **182 处 / 54 文件**） | `grep -rl` |
| 数据库日志模式 | `wal`，活跃 `-wal` 约 10 MB | `pragma journal_mode` |

> ⚠️ 第一版文档写的是“v1 10 份 / v2 4 份 / 110 处 / 44 处”。**以上表为准。**这些数字直接决定 Phase 1 的规模和 Phase 4 守卫的设计。

### 1.3 已确认的结构性问题

| 编号 | 问题 | 证据/位置 | 用户可见后果 |
|---|---|---|---|
| P1 | v1/v2 在运行时同时存在 | 9 份 v1 记录（live） | 同一功能时好时坏 |
| P2 | 后处理挂在错误的层 | `resume_record.py:143-145` 已做 dedupe+strip，但 `document=` 旁路跳过它 | 生成清干净了，SSE 落库又带回来 |
| P3 | 隐藏板块的旧键**完全不生效** | `document_converter.py` 不读 `hidden_sections`；实测记录 9 转换后 `section.hidden` 全 false | 用户藏了板块，导出时还在 |
| P4 | 旧控件已死但代码还在 | `ResumeHiddenSectionsControl.tsx` 无任何挂载点（已核实） | 下一个人容易接错机制 |
| P5 | ~~合并算法按“下标/整条”猜~~ **已修（未提交）** | `projectionContent.ts:448-502` 现按身份匹配 | — |
| P6 | 数据集作用域不一致 | 日志中 `dataset scope mismatch` | 操作被静默拒绝，看起来像按钮失效 |
| P7 | 测试基线不完整 | 分支起点存在预存量失败 | “测试全绿”不等于兼容 |
| **P8** | **校验早于变换，可产出非法文档** | 去重后 `values` 可超 `MAX_LIST_VALUES`（实测 1000 > 500） | 落库成功但下次读取 422 |
| **P9** | **修订路径的“页数收敛”会静默删条目** | 记录 40：`page_limit=3` → 限 6 个项目，实际 7 个 | 点一次 AI 修订少一个项目 |
| **P10** | **经历按公司名去重会吞掉同公司多段任职** | 实测两段同公司不同职位 → 合并成 1 条 | 晋升经历消失 |

> P8/P9/P10 是第一版文档没有识别的问题。P9/P10 直接违反“不删除用户数据”的硬约束。

### 1.4 本整改**不**解决的事

- 不重写上游的业务逻辑；
- 不删除二开功能；
- 不改变现有 UI 的视觉与交互（除非任务明确要求）；
- 不与 `feat/ai-jobs-sidecar-*` 的 AI 求职 sidecar 功能混在一起改；
- 不自动 push 到任何远程仓库。

---

## 2. 目标架构

### 2.1 一句话原则

**只有一个运行时文档模型（v2），只有一个写入流水线，校验在流水线的最后一步。**

### 2.2 目标数据流

```text
模型输出（v1 或 v2 JSON）
        │
        ▼
ensure_document_version()           ← 只在这里允许出现 v1；只做版本归一，不校验
        │
        ▼
dedupe（无损合并）                    ← 按身份合并要点，绝不截断
        │
        ▼
limit（仅生成路径）                   ← 按页数截断，只裁本次新增
        │
        ▼
strip_resume_tech_stack（按偏好）     ← placement=hidden，不删数据
        │
        ▼
parse_document() + validate_document_ids_v2()   ← 唯一校验点（最后一步）
        │
        ▼
resume_record.content（永远 v2、永远合法）
        │
        ├── 详情 API：v2 直通
        ├── 导出/预览：paper_document → planner（唯一可见性过滤点）
        └── AI 修订 / 覆盖补全 / 招呼语：只读 v2
```

**关键顺序**：归一 → 变换 → 校验 → 序列化。第一版文档写成“校验 → 变换 → 不再校验”，是 P8 的根源。

### 2.3 允许保留 v1 的地方（白名单）

1. `backend/app/services/resume/document_converter.py`：转换器本身；
2. 导入 / 备份恢复 / 旧文件解析；
3. 历史快照的只读兼容（`document_v1_oracle.py` 等测试基线）；
4. 测试 fixture。

除以上四处，**不允许新增 v1 读写路径**。

### 2.4 不允许出现的东西

- 新增 `format_config.hidden_sections` / `format_config.section_order` 的**写入**（读取/迁移允许）；
- 在 `document_io` 之外直接读 `record.content` 并按 v1/v2 形状取键；
- 在某个单独路由里做“只针对这个入口”的去重 / 技术栈清理；
- 新的 v1 渲染器、v1 编辑器、v1 导出路径；
- **在 AI 修订路径做页数截断**（只允许无损去重）。

---

## 3. 当前需要理解的关键文件

### 3.1 后端

| 文件 | 作用 | 本整改是否要改 |
|---|---|---|
| `services/resume/document_io.py` | v1→v2 读写边界 | 只读（不改） |
| `services/resume/document_converter.py` | v1→v2 唯一转换实现 | 只读（不改） |
| `services/resume/document_save.py` | `save_content` / `save_ai_revision` | 不改 |
| `services/resume/resume_record.py` | 生成落库 `save_record`（**含 `document=` 旁路**） | **改** |
| `services/resume/resume_dedupe.py` | 同名合并 + 页数收敛（**同时支持 v1/v2**） | **改（拆分合并/截断）** |
| `services/resume/resume_tech_stack.py` | 技术栈隐藏；`hidden_from` 只写不读 | **改（补恢复）** |
| `services/resume/resume_sections.py` | `persistable_format_config`（**漏删 `hidden_sections`**） | **改** |
| `services/resume/resume_template_format.py` | `validated_format_config`（**放行 `hidden_sections`**） | **改** |
| `services/resume/document_html.py` | 纸面过滤的唯一实现点 | 只读（不改） |
| `services/export_pipeline.py` | 导出管线（四个出口已统一走 `paper_document`） | 只读（不改） |
| `services/resume/generation_plan.py` | 二开：JD 要求 → 证据计划 | 不改 |
| `services/profile/portrait_import.py` | 二开：画像导入 | 不改 |
| `services/job/platform.py` | 二开：招聘平台派生 | 不改 |
| `services/job/job_match.py` | 招呼语生成 | 可能改（见 F01） |

### 3.2 前端

| 文件 | 作用 | 是否要改 |
|---|---|---|
| `components/resume/ResumeDetailPreview.tsx` | 详情/生成预览共用界面 | 不改 |
| `components/resume/SectionVisibilityPanel.tsx` | 制作台板块显隐（写 `section.hidden`） | 不改 |
| `components/resume/PreviewSectionsControl.tsx` | 预览板块显隐/排序（写 `section.hidden` + 数组顺序） | 不改 |
| `components/resume/ResumeHiddenSectionsControl.tsx` | **旧版隐藏控件，无挂载点** | **删除** |
| `utils/resumeSectionOrder.ts` | `buildSectionOrderConfig`（`{...base}` 会把旧键带回来） | **改** |
| `features/profile-library/projectionContent.ts` | 覆盖补全（已按身份合并，勿重写） | 不改 |

---

## 4. 实施阶段

> **每阶段固定流程**：跑闸门 → 只修 FAIL → 改一个文件 → 再跑闸门 → 全绿 → 更新第 9 章 → 单独提交。

### 4.0 已实测的起点状态（省你一轮探索）

以下是审查时实测的结果，**不要重复验证**，直接当作已知输入：

| 检查项 | 结果 | 说明 |
|---|---|---|
| `pytest tests/test_resume_dedupe.py test_document_html.py test_generation_preferences.py test_resume_coverage.py` | **28 passed** | 去重/纸面过滤/偏好/覆盖清单**当前全绿**，改动不能把它们弄红 |
| `pytest tests/test_resume_hidden_sections.py` | **3 failed / 3 passed** | P3 的证据，Phase 3 必须转绿 |
| `alembic heads` | `['0075_ai_job_link']` | 单头，正常 |
| 23 条 v1 记录全量 `prepare_document_for_save` | **23/23 通过** | 转换器本身没有坑，Phase 1 的风险主要在版式键消费顺序 |
| 17 条 v2 记录连续两次归一化 | **0 条变化** | `parse_document` 对现有 v2 数据幂等，Phase 1 不会无故重写 v2 记录 |
| `resume_forge.db` 日志模式 | `wal`（活跃 `-wal` ≈ 10 MB） | 备份必须用 `sqlite3.backup` |
| `ResumeHiddenSectionsControl.tsx` 引用 | 仅自身 | 可安全删除 |

---

### Phase 0：基线固化与备份（只读，0.5 天）

**前置阅读**：本文件第 1.2 节。不需要读业务代码。

**目标**：在改动前留下**可恢复**的基线。

#### 任务 1：新建分支

```bash
git switch -c fix/v2-single-model feat/ai-jobs-sidecar-20261102
```

#### 任务 2：WAL 安全备份（**不要用 `cp`**，直接用闸门自带命令）

数据库是 `journal_mode=wal`，且有活跃的 `resume_forge.db-wal`。`cp resume_forge.db xxx.bak` 会丢掉 WAL 里已提交的事务——极端情况下备份出来的文件连表都没有（已实测复现）。

**停应用后，在仓库根跑这一条**（闸门脚本内置 SQLite 在线备份；不要自己写多行脚本，也不要 `cp`）：

```bat
cd /d D:\飞牛文件同步\工作\简历通
stop.cmd
backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --backup
```

预期输出（实测）：

```text
PASS 备份已创建 — D:\飞牛文件同步\工作\简历通\backend\data\resume_forge.db.pre-v2-normalize-20261103-234912.bak
     integrity=ok resume_record=40 源库大小=123387904
     注：源库有活跃 WAL（0 字节），已由 backup API 合并进备份
```

> 实现是 `sqlite3.connect(src).backup(sqlite3.connect(dst))`（`scripts/v2_gate.py::make_backup`），
> 与 `scripts/import_portrait.py:257-270` 同一套写法。**不要发明第二种备份方式。**

#### 任务 3：记录基线

新建 `docs/quality/fork-baseline.md`，**必须包含这四个二级标题**（闸门会检查）：

```markdown
# v2 整改基线（YYYY-MM-DD）

## 1. 环境
- 分支 / HEAD / Python / Node 版本
- 数据库：路径、大小、`pragma journal_mode`、`pragma integrity_check`
- 备份文件名（含完整性检查结果）

## 2. 后端
- `alembic heads` 输出
- 迁移文件前缀重复清单
- 版本分布：live v1=? / v2=?；含软删 v1=? / v2=?
- `pytest -q` 全量结果：通过数 / 失败数 /**失败清单逐条列出**（这是后续判断"新失败"的基准）

## 3. 前端
- `npm run test` 通过数 / 失败数 / 失败清单
- `npm run typecheck` 结果
- `npm run lint` 结果
- `npm run build` 结果

## 4. 预存量失败清单
> 后续任何阶段出现失败，先来这里对照：已在此列的算预存量，不在的算本次引入。
| 测试文件 | 测试名 | 失败原因（一句话） |
```

#### 任务 4：跑闸门

```bash
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 0
```

**验收**（以闸门输出为准）：

- `PASS 基线文档存在`
- `PASS 基线文档结构完整`
- `PASS WAL 安全备份存在`（且 integrity=ok、有数据）
- `PASS alembic 单头`

**回滚**：本阶段不改代码，无需回滚。备份文件保留，**不提交**。

---

### Phase 1：一次性把库里的 v1 简历转成 v2（1 天）

**前置阅读**：`services/resume/document_converter.py`（只看 `convert_content` 与 `_ordered_sections`）、`services/resume/resume_sections.py`（只看 `persistable_format_config`）、`scripts/import_portrait.py`（只看 `_backup_database` 与 `main` 的参数解析）。

**目标**：消灭“同一张表里两种格式”。

> ⚠️ **本阶段会让“隐藏板块”第一次真正生效。** 现状是转换器不读 `hidden_sections`（`document_converter.py` 全文只有 `section_order`），所以旧记录里被“隐藏”的板块**一直显示在纸面上**。迁移后它们会真的消失。这不是 bug，是修复；但它是一次**用户可见的内容变化**，dry-run 必须逐条报出来。
>
> **现成的证据**：`backend/tests/test_resume_hidden_sections.py` **当前有 3 条失败**（`test_html_preview_omits_hidden_sections` / `test_markdown_and_txt_omit_hidden_sections` / `test_word_document_omits_hidden_sections`），断言“隐藏的板块不出现在 HTML/Markdown/TXT/Word 里”，实测全部不成立。这 3 条就是 P3 的机器证据，也是 Phase 3 的天然回归测试——**Phase 0 基线文档里必须把它们记进“预存量失败清单”，Phase 3 结束时它们必须转绿**（转绿是完成标志，不是新引入）。

#### 实现：`scripts/normalize_resume_documents.py`

**文件头必须这样写**（否则 `import app.…` 会失败）：

```python
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
```

**行为契约**（逐条实现，不要增删）：

1. 默认 `--dry-run`；`--apply` 才写库；`--apply` 前**自动做 WAL 安全备份**（复用 Phase 0 的 `sqlite3.backup` 写法）；
2. 遍历**全部** `resume_record`（含软删）；
3. 对每条记录：
   - 若 `content.version == 2`：`parse_document()` 归一化，**与原文比较，有差异才写**；
   - 否则：`document_io.ensure_document_version(content, language=record.language, format_config=record.format_config or {}, custom_fields=document_io.custom_field_definitions(db))`；
4. **旧版式收口顺序不能错**（这是唯一正确的顺序）：
   1. 先用 `format_config.section_order` 重排 `document.sections`（转换器已经在 `ensure_document_version` 内部按它排过了；v2 记录需要这里补排）；
   2. 再把 `format_config.hidden_sections` 里的 key 映射成 `section.hidden = True`；
   3. 最后**删除** `format_config` 里的这两个键。
   > 顺序反了（先删键）就丢信息：`section_order` 是转换器的输入。
5. 写库字段：`content`、`format_config`、`revision = revision + 1`、`updated_at = now`；
   - **`revision` 只对 live 记录推进**（软删记录没人拿它做条件写，推进无意义，只会污染报告）；
6. 幂等：第二次执行 `--apply` 必须 0 条修改；
7. `--json` 输出**一行 JSON** 到 stdout 末行（闸门要解析）：

```json
{"total": 40, "v1": 0, "v2_normalized": 0, "skipped": 0, "hidden_sections_consumed": 0, "section_order_consumed": 0, "parse_failed": 0, "visibility_changes": [{"id": 9, "hidden": ["awards","campus_experience","skills"]}]}
```

> 其中 `v1` = 本次仍需转换的条数（迁移完成后必须是 **0**），`v2_normalized` = v2 记录中仍需归一化的条数（也必须是 **0**）。

#### 运行

```bash
# 停应用后
backend/.venv/Scripts/python.exe -I scripts/normalize_resume_documents.py --dry-run --json
# 人工看一眼 visibility_changes，确认没有意外的板块消失
backend/.venv/Scripts/python.exe -I scripts/normalize_resume_documents.py --apply --json
```

#### 测试：`backend/tests/test_normalize_resume_documents.py`

必须覆盖（每条形如 `test_xxx`，闸门不检查具体名字，但回归包会跑）：

1. v1 → v2 后再次运行无变化（幂等）；
2. `hidden_sections` 被消费成 `section.hidden=True` 并从 `format_config` 删除；
3. `section_order` 被消费成 `document.sections` 顺序并从 `format_config` 删除；
4. 软删记录也被处理；
5. 损坏 JSON 不崩溃，计入 `skipped` 并打印记录 id；
6. `--dry-run` 不写库（用临时库断言 revision 不变）。

#### 验收（闸门）

```bash
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 1
```

- `PASS 全部记录 content.version == 2（含软删）`
- `PASS format_config 不再含旧版式键`
- `PASS 归一化脚本 dry-run 幂等`
- `PASS parse_document 全量通过（live）`

再加人工冒烟：应用启动 → 简历列表 → 打开一份**原来的 v1** 简历 → 详情预览正常 → 导出 PDF 正常。

#### 回滚

```bash
stop.cmd
# 先删 WAL/SHM，否则残留 WAL 会在下次打开时重放，把恢复后的库改回坏状态
rm -f backend/data/resume_forge.db-wal backend/data/resume_forge.db-shm
cp backend/data/resume_forge.db.pre-v2-normalize-<时间戳>.bak backend/data/resume_forge.db
start.cmd
```

---

### Phase 2：把 AI 写路径的不变量收口到一个函数（2 天）

**前置阅读**：`services/resume/resume_record.py`（`save_record` 全文）、`api/resumes/generate_routes.py`（只看 `save_record` 调用处，约 290-330 行）、`api/resumes/ai_edits_routes.py`（只看 `revise_existing_resume`）、`services/resume/resume_dedupe.py`（全文，只有 186 行）。

**目标**：不再“生成时清、修订时脏”。

#### 2.1 拆分去重与截断（先做这一步，否则会删用户数据）

现状：`dedupe_and_limit_resume()` 一个函数干两件事——按身份合并（无损）+ 按页数截断（**有损**）。修订路径调它，用户就会莫名少条目（实测记录 40：7 个项目 → 6 个）。

改成两个函数（`resume_dedupe.py`）：

```python
def dedupe_resume(content: dict, *, sections: tuple[str, ...] = ("projects", "experience")) -> dict:
    """按身份合并同名条目，要点取并集。无损：不截断、不删条目。"""

def limit_resume(content: dict, *, page_limit: int) -> dict:
    """按页数截断条目数量。有损：只用于**生成**路径。"""
```

**必须同时修的两件事**：

1. **合并后的 `values` 要守住 schema 上限**：`_unique_lines(...)[:MAX_LIST_VALUES]`。否则 P8 会让文档非法（实测 1000 > 500）。
2. **经历去重不能只按 `company`**。实测两段同公司不同职位会被合并成一条（P10）。改用 `(company, role, period)` 复合键：同公司同职位同期才是重复。

`dedupe_and_limit_resume` 可以保留为兼容包装（`dedupe_resume` + `limit_resume`），避免改动所有调用点；但**修订路径必须直接调 `dedupe_resume`**。

#### 2.2 新增 `backend/app/services/resume/document_invariants.py`

```python
def finalize_ai_document(
    content: dict,
    *,
    language: str,
    format_config: dict,
    custom_fields,
    page_limit: int | None,
    include_tech_stack: bool,
) -> dict:
    """AI 产出（v1/v2 均可）→ v2 → 去重 → 限量 → 技术栈 → **校验** → 序列化。

    顺序是硬契约，不得调整：
      1. ensure_document_version      只做版本归一，不校验
      2. dedupe_resume                无损合并
      3. limit_resume(page_limit)     仅当 page_limit is not None
      4. strip_resume_tech_stack      仅当 not include_tech_stack
      5. parse_document               唯一校验点
      6. validate_document_ids_v2
      7. document_to_json
    """
```

`page_limit=None` 表示**不截断**（修订路径必须传 `None`）。

#### 2.3 接入点（改三处，不要改第四处）

| 调用点 | 现状 | 改动 |
|---|---|---|
| `resume_record.save_record` | 在 v1 上做 dedupe/strip，再用 `document=` 旁路 | **删掉 `document=` 参数**；改为 `finalize_ai_document(content, page_limit=page_limit, …)`，用它返回的 doc 落库与发布 SSE |
| `resume_record.save_record` 的 v1 视图读取 | 从 `content` 取 `name` / `job_intent` | **保留**，但必须在 `finalize_ai_document` **之前**取值（转换后是 v2 形状，取不到） |
| `api/resumes/ai_edits_routes.revise_existing_resume` | `prepare_document_for_save` 后 `save_ai_revision` | 改调 `finalize_ai_document(..., page_limit=None, include_tech_stack=get_generation_preferences(db)["include_tech_stack"])` |
| `api/resumes/generate_routes.py` 流式解析 | 先 `strip_resume_tech_stack(parsed)` 再 `ensure_document_version` 传给 `document=` | **删除这段预处理**；改为把 `parsed` 直接交给 `save_record`，SSE 的 `done.resume` 用 `save_record` 返回的记录内容（同一份） |

> 手工保存（`save_content`）**不接入**去重/技术栈清理，避免用户手写内容被系统悄悄改掉。

#### 2.4 技术栈开关的“恢复”（P1-2 / F07）

`hidden_from` 现在**只写不读**（`grep -rn hidden_from backend/app` 只有 1 处写入）。用户把开关重新打开，之前隐藏的技术栈不会回来。

实现位置：`services/profile/generation_preferences.py` 的 `save_generation_preferences`——当 `include_tech_stack` 从 `False` 变成 `True` 时，遍历该用户可见的简历文档，把 `placement == "hidden"` 且 `hidden_from` 非空的项恢复成 `hidden_from` 的值并清空 `hidden_from`。

如果时间不够，**必须把文档口径改成**：“数据保留、可手工拖回，不保证自动恢复”，并且不要在 Phase 5 写一条会自动失败的测试。

#### 2.5 测试：`backend/tests/test_ai_write_invariants.py`

1. 模型返回重复项目 → 落库后同名项目只剩一条，要点合并（不丢要点）；
2. 模型返回 `tech_stack` → 开关关闭时 `placement=hidden`，HTML/PDF 不出现；
3. 2 页上限 → 条目数量符合 `limit_resume` 规则；
4. **合并后 `values` 不超过 `MAX_LIST_VALUES`，且能再次 `parse_document`**（P8 回归）；
5. **修订路径：7 个项目的简历修订后仍是 7 个**（P9 回归）；
6. **同公司两段不同职位不被合并**（P10 回归）；
7. AI 修订后再读详情，不变量仍成立；
8. 手工保存不触发去重。

#### 验收（闸门）

```bash
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 2
```

- `PASS 存在 finalize_ai_document`
- `PASS save_record 无 document= 旁路`
- `PASS finalize 至少接入 2 处写入`
- `PASS finalize 行为：去重+限量+技术栈+可再解析`
- `PASS test_ai_write_invariants.py 全绿`

再加人工四步：生成 → 详情 → AI 修订 → 详情 → 导出，全程不出现技术栈和重复项目，且**项目数量不减少**。

---

### Phase 3：统一板块显隐与排序（1 天）

**前置阅读**：`services/resume/resume_sections.py`、`services/resume/resume_template_format.py`（只看 `validated_format_config` 的 `hidden_sections` 分支）、`utils/resumeSectionOrder.ts`。

**目标**：只保留 v2 一套真相。

> ✅ **导出侧已经统一，不要动。** 实测 JSON / HTML / PDF / DOCX / Markdown / TXT 六个出口全部先过 `paper_document`；`document_html.py:191-220` 是唯一过滤点；`export_pipeline.py` 里的 `resolved_visible_sections` 只是历史参数，`export_markdown` 的 docstring 已写明它会忽略。
>
> 第一版文档把“确认四个出口”写成待办，会让人去重构已经正确的代码。**本阶段只做下面三件事。**

#### 3.1 后端：`hidden_sections` 必须从写入路径消失

现状（实测）：

- `persistable_format_config` 只删 `section_order`，`hidden_sections` 原样保留 → 会落库；
- `validated_format_config` 又把 `hidden_sections` 收进结果 → 也会落库；
- 前端 `buildSectionOrderConfig` 是 `{...base}`，底稿的整份 `format_config` 会被透传进生成请求。

所以 Phase 1 清干净的键，用户拿旧简历当底稿生成一次就回来了。

改动（三行级）：

1. `resume_sections.py::persistable_format_config`：把 `hidden_sections` 一起过滤掉（与 `section_order` 同一行逻辑）；
2. `resume_template_format.py::validated_format_config`：**保留读取分支**（旧导入/旧备份仍要能解析），但该函数只用于“解析外部输入”，不再用于“落库前校验”；
3. `resume_record.py` / `manual_creation.py` / `layout_render_routes.py` 的落库前调用链保持 `validated(persistable(...))` 顺序即可自动生效。

#### 3.2 前端：`buildSectionOrderConfig` 不要带回旧键

`utils/resumeSectionOrder.ts:87` 的 `{...base}` 会把 `hidden_sections` 一起带进请求。改成显式白名单，或至少 `delete next.hidden_sections`。

#### 3.3 删除死控件

`frontend/src/components/resume/ResumeHiddenSectionsControl.tsx` 无任何 import（已核实）。删除前：

```bash
grep -rn "ResumeHiddenSectionsControl" frontend/src   # 必须只剩自身
```

i18n key `sections.hidden.*` 还有 2 处其他引用（`SectionVisibilityPanel` 等），**不要删 key**。

#### 测试

- 已有：`SectionVisibilityPanel.test.tsx`、`PreviewSectionsControl.test.tsx`（不用改）
- **已在仓库里、当前是红的**：`backend/tests/test_resume_hidden_sections.py`（3 条失败，见 Phase 1 的说明）。Phase 3 的任务之一是让它转绿——它断言的就是“隐藏板块不出现在 HTML/Markdown/TXT/Word”，正是本阶段要修的行为。**不要改它的断言**（E4），去修实现。
- 新增：`backend/tests/test_section_visibility_exports.py`
  - 隐藏某板块 → HTML / PDF / Word / Markdown 四种导出都不含该板块的**正文原文**（断言正文关键词，不断言标题，标题可能出现在别处）；
  - 显示 → 恢复；
  - `persistable_format_config` 同时丢弃两个键。

#### 验收（闸门）

```bash
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 3
```

- `PASS 旧隐藏控件已删除`
- `PASS persistable 丢弃旧版式键`
- `PASS 后端无 hidden_sections 写入点`
- `PASS 四格式对拍测试全绿`
- `PASS 旧隐藏板块测试全绿`（`test_resume_hidden_sections.py` 的 3 条预存量失败转绿）

再加人工：预览隐藏一个板块 → 刷新 → 导出 HTML/PDF 都不出现 → 用这份简历当底稿生成一次 → 新记录的 `format_config` 里没有 `hidden_sections`。

---

### Phase 4：静态守卫（1 天）

**前置阅读**：`scripts/Check-All.ps1`（看它怎么组织检查步骤）。

**目标**：让“下一个人写回旧路径”在 CI 就失败。

> ⚠️ **守卫不要检查 `record.content` 的出现次数。** 实测 40 处里绝大多数是合法的（喂给 `document_for_record`、参与 sha256、冻结快照）。而“按 v1/v2 形状取键”的危险写法实测是 **0 处**。按出现次数做 allowlist，要么膨胀到 35 条（形同虚设），要么正常代码全红（守卫被关掉）。

#### `scripts/check_v2_boundary.py` 要检查的四件事

1. **v1 形状消费**（AST，不是正则）：禁止对 `record.content` / `resume.content` / `row.content` 直接下标或 `.get("<v1 字段>")`。v1 字段清单至少包含：
   `projects` / `experience` / `educations` / `internships` / `awards` / `campus_experience` / `custom_sections` / `job_intent` / `tech_stack` / `hidden_points`。
2. **`record.content` 的使用形态**：每一处出现必须是以下之一，否则报错：
   - 直接作为 `document_for_record(...)` / `ensure_document_version(...)` / `coerce_document(...)` / `paper_document(...)` 的实参；
   - 在 `document_save.py` / `resume_delivery.py` / `ai_jobs/resume_sync.py`（哈希/比较用途）白名单内。
3. **`hidden_sections` / `section_order` 的写入**：禁止出现 `result["hidden_sections"] =` / `values["section_order"] =` 这类赋值。读取与转换允许。
4. **迁移**：
   - `versions/*.py` 的**文件名数字前缀**唯一（`revision` 字符串本来就唯一，查它永远绿）；
   - `alembic heads` 单头；
   - 每个 `down_revision` 引用的 id 必须存在。

#### 接入

加到 `scripts/Check-All.ps1` 的第 1 步之后（与 ruff 同级），不要新建 CI 文件。

#### 验收（闸门）

```bash
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 4
```

- `PASS 静态守卫脚本存在`
- `PASS 静态守卫通过`
- `PASS 迁移文件名前缀唯一`

手工反向验证：在 `backend/app/api/` 任意文件写一行 `x = record.content.get("projects")`，守卫必须报错并给出文件:行号；删掉后恢复全绿。

---

### Phase 5：二开回归包（2 天）

**前置阅读**：第 5 章台账（只读自己负责的那几个 F 编号）。

**目标**：以后每次合并上游，先跑这组测试，而不是靠人点。

#### 5.1 主测试：同形不变量（**优先级最高，先写这个**）

新增 `backend/tests/test_document_shape_invariants.py`：

> 对库里每一条 live 记录，分别经 **详情 API / 导出 JSON / Markdown / preflight / 招呼语上下文 / 事实锁** 取出文档，规范化后取 sha256（或结构指纹），断言**全部相同**。

一个测试永久锁住 P1（同一功能时好时坏）和 P3（两套真相），而且不依赖具体业务规则。用测试夹具造数据（不要依赖真实库），至少覆盖：纯 v2、从 v1 迁来的、带隐藏板块的、带技术栈隐藏项的。

#### 5.2 业务回归矩阵（补充）

`backend/tests/test_fork_regression.py` + `frontend/src/features/profile-library/forkRegression.test.ts`。

> 第一版文档的矩阵把“AI 修订 / v1 输入”列成可达格子，其实不可达：Phase 1 之后库里没有 v1 记录，`/revise` 拿到的一直是 v2。矩阵改成下面这张。

| 写路径 | 请求体 v1 | 请求体 v2 | 记录原本是 v1 | 断言 |
|---|---|---|---|---|
| 生成落库 | 有 | 有 | — | 无重复、技术栈隐藏、页数上限 |
| AI 修订 | — | 有 | **有** | 无重复、技术栈隐藏、**条目不减少** |
| 手工保存 | 有 | 有 | — | 不自动删内容，但结构合法 |
| 覆盖补全 | — | 有 | — | 按身份合并、幂等 |
| 导出四格式 | — | 有 | **有** | 隐藏板块不出现、顺序一致 |

#### 5.3 必须覆盖的二开不变量

1. 项目名在 `projects` 板块唯一；**公司+职位+时间**在 `experience` 板块唯一；
2. 技术栈开关关闭时，任何出口都不可见；打开后**能恢复**（若实现了 2.4）或文档口径已改；
3. 隐藏板块在四个导出里都不出现；
4. 板块顺序与 `document.sections` 一致；
5. 覆盖补全不追加重复项目；
6. 招呼语开头必须是「您好，」——**仅此一条有确定性实现**，其余见 F01；
7. 生成计划的 `fact_quote` 必须能在对应原文中找到；
8. 岗位平台派生值只能是已知枚举或“其他”。

#### 验收（闸门）

```bash
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 5
```

- `PASS 同形不变量测试全绿`
- `PASS 二开回归包全绿`
- `PASS 核心二开测试全绿`

在 `docs/fork-sync-runbook.md` 中写明“合并前/后必须跑 `scripts/v2_gate.py --all`”。

---

### Phase 6：合并流程改造（文档 + 流程，1 天）

新增 `docs/fork-sync-runbook.md`，内容至少包括：

1. **同步频率**：每月一次小批量，禁止再次一次性合并 1000+ 文件；
2. **上游镜像**：`upstream` 只读，二开提交可按功能回溯；
3. **合并前**：WAL 安全备份、跑闸门、记录基线；
4. **合并中**：冲突处理原则——
   - 上游基础设施文件优先上游；
   - 二开功能文件以二开为准，但必须适配 v2；
   - 模板文件若上游改引擎，先跑 `preflight` 与四格式导出；
5. **合并后**：跑闸门 + 全量测试 + 真实库冒烟（列表/详情/生成/修订/导出/投递台）；
6. **迁移检查**：文件名前缀唯一、`alembic heads` 单头、`integrity_check`；
7. **回滚**：代码回滚 + 数据库备份恢复（**含删 `-wal`/`-shm`**）。

验收：文档可被另一个模型按步骤执行；包含失败时的回滚路径。

---

### Phase 7（可选，后续）：生成链路 convert-early

> 只有 Phase 1–6 完成、闸门 `--all` 全绿后再做。

把生成内部从“v1 中间态”改为“模型输出解析后立刻转 v2”，让生成、修订、补全全部共用同一个 v2 后处理。收益是彻底消除“生成链路 v1 / 其他链路 v2”的认知负担；风险是生成后处理（承载区、custom field lines）需要逐段迁移。

**不建议在本次整改第一轮做。** 先靠 Phase 2 的收口解决 90% 的复发问题。

---

## 5. 二开功能台账

> 这张表是“改任何功能前的检查清单”。新增二开功能必须在这里加一行；删除功能也要在这里标注。
> **不变量** = 任何写路径执行后都必须成立的条件；**上游对应** = 上游是否已有同名能力（有则优先用上游实现）。

### 5.1 功能总表

| ID | 功能 | 前端入口 | 后端入口 | 核心文件 | 数据/迁移 | 主要测试 | 上游对应 | 风险 |
|---|---|---|---|---|---|---|---|---|
| F01 | 招呼语体系（确认闸门/批量/基准） | 投递台队列、编辑弹窗、设置 | `/api/apply/greeting/*`、`/api/apply/config` | `prompts/apply_greeting.md`、`services/job/job_match.py`、`services/apply/_queue.py`、`QueueItemEditor.tsx` | `ApplyQueueItem.greeting*`、`ApplyConfig.greeting_baseline` | `test_apply_greeting_*`、前端队列测试 | 有基础招呼语 | 中 |
| F02 | 招聘平台派生与筛选 | 岗位广场平台列/筛选 | `/api/jobs` 派生字段 | `services/job/platform.py`、`JobTable.tsx` | 无新列 | `test_jobs_platform_filter.py` | 无 | 低 |
| F03 | 投递专用浏览器复用 | 「前往投递」 | `/api/apply/browser/*` | `services/apply/_site_browser.py`、`api/apply.py` | 浏览器 profile 目录 | 投递相关测试 | 部分 | 中 |
| F04 | 底稿生成（沿用版式） | 生成配置弹窗 | `/api/resumes/generate` | `services/resume/resume_base_derive.py`、`GenerationConfigStage.tsx`、`useBaseResumeOptions.ts` | `base_resume_id` | `test_resume_base_derive.py` | 有生成 | 中 |
| F05 | 画像导入 + 事实台账 | 资料库/事实台账（脚本） | `scripts/import_portrait.py` | `services/profile/portrait_import.py`、`claims` | `profile_entry`、`claim_record` | `test_portrait_import.py` | 无 | 中 |
| F06 | 生成计划 / 匹配报告 | 生成弹窗报告页 | `/api/resumes/generation-plan` | `services/resume/generation_plan.py`、`prompts/generation_plan.md`、`GenerationPlanStage.tsx`、`api/resumePlan.ts` | 表 `resume_generation_plan`（`0070_resume_generation_plan`） | `test_generation_plan.py`、`test_api_generation_plan.py` | 部分（匹配分析） | 高 |
| F07 | 技术栈显示开关 | 设置/资料 → 生成偏好 | 生成偏好接口 | `services/profile/generation_preferences.py`、`services/resume/resume_tech_stack.py` | 偏好表 | `test_generation_preferences.py` | 无 | **高** |
| F08 | 板块显隐/排序 | 制作台/预览 | 随内容保存 | `SectionVisibilityPanel.tsx`、`PreviewSectionsControl.tsx`、`document_html.py` | v2 `section.hidden` + 数组顺序 | 前端两个组件测试；`test_section_visibility_exports.py` | 无 | **高** |
| F09 | 覆盖清单补全/润色 | 详情/生成预览 | `/api/resumes/{id}/revise`、内容保存 | `ResumeCoverageNotes.tsx`、`ResumeDetailPreview.tsx`、`projectionContent.ts`、`resume_coverage.py` | `coverage_notes` | `test_resume_coverage.py`、`fillCoverageNote.test.ts` | 无 | 中 |
| F10 | 去重 / 页数收敛 | 无直接入口（生成后） | 生成落库 | `services/resume/resume_dedupe.py` | 无 | `test_resume_dedupe.py` | 无 | **高** |
| F11 | 本地模板与模板画廊 | 模板画廊、`/skills` | `/api/resume-templates` | `backend/app/templates/*.j2`、模板画廊组件 | `resume_template` | 模板/渲染测试 | 上游模板体系 | 中 |
| F12 | 页内收录扩展 / 链接导入 / Ego Lite | 浏览器扩展、岗位导入 | `/api/jobs/import-url`、`/api/jobs/import-current` | `services/browser/extension/*`、`api/job_import.py`、`services/browser/browser_locator.py` | 无 | `test_job_import_url.py`、`test_browser_ego.py` | 无 | 中 |
| F13 | 资料日期直接输入（刻意偏离） | 资料页 | — | `PartialDateInput.tsx`、`ProfileFieldInputs.tsx` | 无 | 资料页测试 | 上游是 Select | 低 |
| F14 | reduced-motion 修复（上游缺陷） | 全局 | — | `frontend/src/styles/foundation.css` | 无 | 前端守卫 | 上游缺陷 | 低 |
| F15 | AI 求职 sidecar | 独立页面 | `/api/ai-jobs/*` | `services/ai_jobs/*`、`0075_ai_job_link` | `ai_job_link` | 专项测试 | 无 | 独立产品，暂不计入本次 |

### 5.2 每个功能必须守住的不变量

#### F01 招呼语

> ⚠️ **现状：除“以「您好，」开头”外，其余全部只是提示词约束，没有服务端校验。**
> `job_match.py:473-491` 的 `normalize_greeting_opening` 补开头；`parse_greeting` 只做 500 字上限截断。**没有**禁用词检查、没有句数检查、没有字数检查。
>
> 两条合法路线，Phase 5 前必须二选一并写进本文档：
> - **A（推荐）**：加确定性守卫——禁用词表（学校/专业/年级/届别/学历/毕业时间）+ 五句结构 + 140–220 字 + 「」引用必须出现在 JD 原文里；违规重试一次，仍违规则返回 `None` 让前端提示重新生成。
> - **B**：把下列不变量降级为“提示词约束 + 抽样人工检查”，Phase 5 只测“开头是「您好，」”，不写会伪装成保证的测试。

- 任何生成结果都以 `您好，` 开头；
- 不出现学校、专业、年级、届别、学历、毕业时间；
- 只讲 1 个项目 + 1–2 个能力，数字不超过 **1 个**（与 `prompts/apply_greeting.md` 对齐；第一版文档写“1–2 个”，与提示词不一致）；
- 用户自定义 `greeting_baseline` 只约束结构与语气，不得把示例中的公司/项目/数字当事实；
- 未确认的招呼语不得直接投递（`greeting_confirmed` 闸门）。

#### F02 招聘平台

- 只从已知枚举派生，未知归“其他”；
- 不新增数据库列，派生逻辑可单测；
- 筛选只影响展示，不改变岗位原始数据。

#### F03 投递浏览器

- 「前往投递」与投递台使用同一个浏览器 profile；
- 应用退出不关闭投递浏览器（登录态跨重启保留）；
- 不跨 profile 共用登录态。

#### F04 底稿生成

- 底稿只读，不被修改；
- 默认继承底稿的模板/版式/页数/语言；
- **继承的 `format_config` 不得把旧键（`hidden_sections` / `section_order`）带进新记录**（Phase 3.2）；
- 完整 JD 传入，不允许只传标题；
- 底稿不存在时明确失败，不静默退回空生成。

#### F05 画像导入

- 按规范化名称 upsert，重复导入幂等；
- A/B 级事实进 `已确认`，C 级 `不采用`；
- Claim 的 `sources` 必须带 `profile_entry.entry_id`；
- 不删除用户已有资料，只做加法。

#### F06 生成计划

- 每条 JD 要求只能引用 0–2 个证据；
- `fact_quote` 必须能在对应原文中找到，否则丢弃；
- `direct / transferable / none` 三态明确，`transferable` 不得写成直接经验；
- 教育经历参与候选；
- 计划与生成记录通过 `plan_id` 关联，可回看。

#### F07 技术栈开关

- 关闭时：v2 `tech_stack` 项 `placement=hidden`、`hidden_from` 记录原位置；
- 正文里的「技术栈：…」整行/行内标签也要清理；
- 生成、AI 修订、覆盖补全后的任何出口都不可见；
- **打开时能恢复**（实现见 Phase 2.4；未实现则改本条口径）。

#### F08 板块显隐/排序

- 唯一真相：`document.sections[].hidden` + 数组顺序；
- 至少保留一个可见板块；
- HTML/PDF/Word/Markdown 四个出口一致（已由 `paper_document` 统一保证，加测试锁住即可）；
- 隐藏只影响纸面，不删除数据；
- **`format_config` 里不得再出现 `hidden_sections` / `section_order`**。

#### F09 覆盖清单

- 按条目身份补缺，不追加重复项目；
- 同一段只补一次，重复点击幂等；
- 补进去的内容必须来自资料投影，不编造；
- 「AI 润色这段」必须先补齐再润色；
- 补完后对应清单项应消失，没补上的继续保留。

#### F10 去重/页数

- 项目按名称去重；**经历按「公司 + 职位 + 时间」去重**（不能只按公司，见 P10）；
- 页数上限：1 页 3 项目/2 经历；2 页 5/3；长简历 6/4；
- **合并与截断必须分开**：`dedupe_resume` 无损，`limit_resume` 仅生成路径；
- 去重不丢要点；合并后的列表长度不超过 schema 上限。

#### F11 模板

- 模板只负责外壳与 CSS，不拼字段；
- 必须包含 `_resume_document.j2` include；
- 21 个 `.j2`（含 3 个 include 片段，实际简历模板 18 套）HTML/PDF/Word 至少各冒烟一次；
- 模板名/分类/说明走 i18n。

#### F12 扩展/导入

- 收录 URL 上限 4096，落库前统一为 canonical `/job_detail/<id>.html`；
- 重复收录去重；
- 公司名优先 `.job-banner`，失败再退回页面标题；
- 扩展超时要有明确反馈，不留下无响应窗口。

#### F13/F14 刻意偏离

- 日期输入保持单输入框，不回退到上游 Select；
- 不恢复全局动画时长压缩；
- 两处都在 `docs/upstream-full-replay.md` 有回退说明。

---

## 6. 验收与测试命令

### 6.1 唯一入口：闸门

```bash
# 仓库根
backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --all
```

### 6.2 后端

```bash
cd backend

# 定向
./.venv/Scripts/python.exe -m pytest tests/test_resume_coverage.py \
  tests/test_resume_document_save.py tests/test_document_save_prune.py \
  tests/test_ai_write_invariants.py tests/test_document_shape_invariants.py \
  tests/test_fork_regression.py -q

# 全量
./.venv/Scripts/python.exe -m pytest -q
```

> 仓库规则：**不要用 `npx`**（`scripts/Check-All.ps1` 开头明确写了 “No npx”）。

### 6.3 前端

```bash
cd frontend

# 定向（npm run test 已经是 vitest run，不要重复传 --run）
npm run test -- src/features/profile-library/fillCoverageNote.test.ts \
  src/features/profile-library/projectionContent.test.ts \
  src/components/resume/SectionVisibilityPanel.test.tsx \
  src/components/resume/PreviewSectionsControl.test.tsx

# 类型 / lint / 构建（用仓库脚本，不用 npx）
npm run typecheck
npm run lint
npm run build
```

### 6.4 真实库冒烟（改完后必须做）

1. 启动：`start.cmd` 或 `scripts\Start-ResumeForge.ps1 -NoBrowser`；
2. 打开 `http://127.0.0.1:8005`；
3. 依次验证（每步记录“通过/失败”到第 9 章）：
   - 简历列表能打开旧记录（原来的 9 份 v1 已转 v2）；
   - 详情预览正常，**且原来被“隐藏”的板块确实不再出现**；
   - 生成一份新简历：技术栈不出现、项目不重复；
   - AI 修订同一份：技术栈仍不出现、项目不重复、**项目数量不变**；
   - 覆盖清单「从资料补上这段」：内容出现、无重复；
   - 「AI 润色这段」：先补齐再润色，结果有变化；
   - 隐藏一个板块：刷新 + 导出 HTML/PDF/Word 均不出现；
   - 以这份简历为底稿再生成一次：新记录 `format_config` 里没有 `hidden_sections`；
   - 投递台：队列简历下拉、招呼语生成、分页条数切换正常。

---

## 7. 风险与回退

| 风险 | 影响 | 缓解 |
|---|---|---|
| 朴素 `cp` 备份丢 WAL 数据 | 备份不可用 | 用 `sqlite3.backup()`；回滚先删 `-wal`/`-shm` |
| v1→v2 批量转换有损 | 旧简历内容变化 | dry-run 报告 + 抽样对比；**23 条 v1 已实测可全部转换** |
| **隐藏板块首次生效** | 简历变短、用户困惑 | dry-run 逐条列 `visibility_changes`；验收时人工确认 |
| 推进 revision 导致旧页面 409 | 用户需刷新 | 这是刻意行为；界面已有冲突三选一 |
| 修订路径误用截断 | **静默删用户条目** | `dedupe`/`limit` 拆开；修订传 `page_limit=None` |
| 同公司多段任职被合并 | **晋升经历消失** | 去重键改成 `(company, role, period)` |
| 合并后列表超 schema 上限 | 落库成功但读取 422 | 合并时 `[:MAX_LIST_VALUES]`；校验放最后 |
| `document=` 旁路残留 | 不变量静默失效 | 删参数；闸门检查 `save_record` 入参 |
| 隐藏板块统一后旧模板不认 | 导出不一致 | `paper_document` 已统一，加对拍测试即可 |
| 删除旧控件影响未知引用 | 构建失败 | 删除前 grep + `npm run build` 兜底 |
| 静态守卫 allowlist 太宽 | 守卫失效 | 按“形状消费”而非“属性出现”设计；新增例外必须写理由 |
| 合并流程改造执行不到位 | 下次同步又大爆炸 | 写进 `docs/fork-sync-runbook.md`，闸门 `--all` 作为合并前必跑 |

**任何阶段出问题，优先回滚数据库备份，再回滚代码提交；不要试图“在坏数据上继续修”。**

---

## 8. 交付物清单

- [ ] `docs/quality/fork-baseline.md`
- [ ] `backend/data/resume_forge.db.pre-v2-normalize-*.bak`（不提交）
- [ ] `scripts/normalize_resume_documents.py`
- [ ] `backend/tests/test_normalize_resume_documents.py`
- [ ] `backend/app/services/resume/document_invariants.py`
- [ ] `services/resume/resume_dedupe.py` 拆分（`dedupe_resume` / `limit_resume`）
- [ ] `backend/tests/test_ai_write_invariants.py`
- [ ] `backend/tests/test_section_visibility_exports.py`
- [ ] `backend/tests/test_document_shape_invariants.py`
- [ ] `backend/tests/test_fork_regression.py`
- [ ] `frontend/src/features/profile-library/forkRegression.test.ts`（或等价拆分）
- [ ] `scripts/check_v2_boundary.py`
- [ ] `docs/fork-sync-runbook.md`
- [ ] 删除 `frontend/src/components/resume/ResumeHiddenSectionsControl.tsx`
- [ ] 本文档更新“执行记录”

> ✅ `scripts/v2_gate.py` 已经存在（闸门），不需要重新创建。

---

## 9. 执行记录（接手者填写）

> 每阶段结束把**闸门原始输出**贴进“证据”列，不要只写“通过”。

| 阶段 | 状态 | 提交 | 闸门结果 | 证据 / 备注 |
|---|---|---|---|---|
| Phase 0 基线 | 完成（2026-11-04 夜间） | `83bd94d3` | 3 通过 / 0 失败 | 备份 `pre-v2-normalize-20261103-235326.bak`（integrity=ok，40 条）；基线文档 `docs/quality/fork-baseline.md`：后端 65 failed / 前端 33 failed 全部预存量记录在案 |
| Phase 1 数据归一 | 完成（2026-11-04 夜间） | `d1403544` | 4 通过 / 0 失败 | 40 条全 v2（含软删）；visibility_changes 11 条均为 `skills`（隐藏后仍 4/5 可见）；apply 自动备份 `pre-normalize-20261104-010845.bak`；幂等复跑 v1=0 / v2_normalized=0 |
| Phase 2 写路径收口 | 完成（2.4 技术栈自动恢复**未实现**，按备选口径："数据保留、需手工拖回"） | `e38502f2` | 5 通过 / 0 失败 | `finalize_ai_document` 接入 save_record + revise 两处；`dedupe_resume`/`limit_resume` 拆分；P8（values≤500）/P9（修订 7→7）/P10（同公司两职位不合并）回归全绿；定向回归 60/60 |
| Phase 3 板块统一 | 完成（2026-11-04 夜间） | `f7df4afd` | 5 通过 / 0 失败 | 3 条预存量失败（test_resume_hidden_sections）**转绿**；persistable 丢两个旧键；converter 读时消费 hidden_sections；export_markdown 恢复可见清单语义；导出面定向回归 253/253 |
| Phase 4 静态守卫 | 未开始 | — | — | `scripts/check_v2_boundary.py` 待建 |
| Phase 5 回归包 | 未开始 | — | — | 同形不变量 / 二开回归矩阵待写 |
| Phase 6 合并流程 | 未开始 | — | — | runbook 待写 |
| Phase 7 convert-early | 暂缓 | — | — | 等前六阶段稳定 |

**冲突/存疑记录**（E6 要求）：

| 日期 | 文档条款 | 代码事实 | 处理方式 |
|---|---|---|---|
| 2026-11-04 | §1.3 P7 / Phase 1 注：「已知预存量失败只有 test_resume_hidden_sections 3 条」 | 全量实测 **65** failed（后端）/ 33 failed（前端），分支起点即红 | 基线文档如实记录全部名单与原因（`docs/quality/fork-baseline.md`），后续阶段先对照该清单 |
| 2026-11-04 | §3.1 表「document_converter.py 只读（不改）」 vs Phase 3「3 条旧隐藏板块测试必须转绿」 | 3 条测试的失败根因正是转换器不读 hidden_sections；四出口共用 coerce_document→converter，没有第二个消费点 | 在 `convert_content` 增加 `_apply_hidden_sections`（只**读取**旧键，§2.4 明确允许读取；过滤仍由 paper_document 统一执行），提交 f7df4afd |
| 2026-11-04 | Phase 3 注「export_markdown 的 docstring 已写明 section_order 会忽略」 vs `test_markdown_and_txt_omit_hidden_sections` 用该参数表达可见性 | 测试不可改（E4）；该参数语义 = `resolved_visible_sections` 的产物（可见板块清单） | `export_markdown` 恢复参数消费：清单外板块不上正文；显式传参才生效，v2 正常路径（不传）不受影响，提交 f7df4afd |
| 2026-11-04 | 闸门「后端无 hidden_sections 写入点」正则会命中 `validated_format_config` 的解析输出；而现有测试钉住该函数保留该键（解析外部输入口径） | 解析产物 ≠ 落库写入；落库前由 persistable_format_config 先行丢弃 | 该分支改用 `result.update({…})` 形态并加注释说明缘由，提交 f7df4afd |
| 2026-11-04 | Phase 1 幂等性：脚本首版在 `section_order` 键缺失时仍无条件套 `_ordered_sections`，会把已烘焙进 sections 数组的自定义顺序重置为默认（复跑报 v2_normalized=12） | `_ordered_sections(…, {})` 恒按默认顺序重排 | 脚本改为仅当键真实存在才重排，d1403544 |
| 2026-11-04 | Phase 2.4 技术栈自动恢复（hidden_from 只写不读） | 实现需要在偏好切换时批量改写用户简历数据（迁移脚本之外的写库路径），夜间风险收益不匹配 | 未实现；口径按文档备选项定为「数据保留、需手工拖回」，待白天决策是否补实现 |

---

## 10. 给接手模型的硬性约束

1. **先读本文档，再读代码；不要凭“看起来像”改。**
2. 每阶段只做该阶段的事，不顺手重构无关模块（E3）。
3. 不改用户数据库，除非是 Phase 1 的脚本且已备份、已 dry-run。
4. 不删除任何用户简历/资料/投递记录；软删也不行。
5. 不新增 v1 读写路径；不把 `format_config.hidden_sections` 作为新功能入口。
6. 所有用户可见文案走 i18n（`frontend/src/i18n/messages/*`），不要硬编码中文/英文。
7. 不提交 `backend/data/*.db`、`*.bak`、`runtime/` 下的临时产物。
8. 不 push、不建 PR，除非用户明确要求。
9. 每个阶段结束跑闸门；失败必须如实记录，不许把测试改成“通过”（E4）。
10. 如果发现本文档与代码不一致，**以代码为准并在第 9 章记录冲突**，不要沉默绕过（E6）。
11. **当前工作树有未提交改动**（本轮修复：招呼语框架、队列分页/简历下拉、覆盖补全、技术栈、去重、板块显隐等）。不得 `git reset --hard`、`git checkout .`、`git stash drop` 或以“清理工作区”为名丢弃；开始前先 `git status` 确认，必要时先提交为一个 WIP 提交再继续（E5）。
12. 不执行 `git clean -fd`；`frontend/runtime/`、`backend/data/*.bak` 等本地文件不要提交。
13. **不要重新创建 `scripts/v2_gate.py`**；它是闸门，改它等于改验收标准。

---

## 11. 可直接粘贴给执行模型的启动提示词（GLM-5.3-flash 版）

```text
你在 Windows 仓库 D:\飞牛文件同步\工作\简历通（ResumeForge 本地二开版）工作。
当前分支 feat/ai-jobs-sidecar-20261102，工作树有未提交改动，先 git status 确认并保留，
禁止 reset / checkout / clean / stash drop。

请先完整阅读 docs/fork-v2-compatibility-plan.md，然后从 Phase 0 开始按顺序执行。

【执行协议（最高优先级，违反任何一条即停下重来）】
1. 每阶段先跑：backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase N
   只修 FAIL 行，不碰 PASS 行。
2. 阶段内一次只改一个文件，改完立刻重跑闸门，全绿才改下一个。
3. 禁止重命名、禁止搬文件、禁止顺手清理无关代码。
4. 禁止修改测试断言使其通过。测试失败只能修实现，或在执行记录里标"需人工裁决"后 skip。
5. 不确定就以代码为准，并在第 9 章"冲突/存疑记录"写下冲突点后停下问我。
6. 每阶段结束：跑闸门 → 把闸门原始输出贴进第 9 章 → 单独提交（前缀 fix(v2)/refactor(v2)/test(v2)/docs(v2)）。
7. 不要一次读完整个仓库；每阶段只读该阶段"前置阅读"列出的文件（≤4 个）。
8. 不要重新创建 scripts/v2_gate.py。

【本阶段特别提醒】
- 数据迁移必须先 dry-run、先做 WAL 安全备份（用 sqlite3.backup，不要用 cp），再 apply。
- 不删除用户数据，不新增 v1 读写路径，不 push。
- 修订路径不能做页数截断（会删用户条目）；去重与截断必须分开。
- 校验必须在流水线最后一步，不能在变换之前。

第一阶段只做 Phase 0 + Phase 1，完成后停下来等我确认，不要直接进入 Phase 2。
汇报时给我：改了哪些文件（路径）、闸门原始输出、遗留风险、第 9 章冲突记录。
```

### 11.1 分阶段任务卡（每轮只粘一张）

> **为什么要有任务卡**：便宜模型在多目标 prompt 下最容易“提前进入下一阶段”或“顺手多做一点”。一张卡 = 一个阶段 = 一次会话，能把任务边界钉死。**不要一次粘多张。**

#### 卡片 0（Phase 0）

```text
仓库：D:\飞牛文件同步\工作\简历通
任务：只执行 docs/fork-v2-compatibility-plan.md 的 Phase 0。

步骤：
1. git status，把输出贴出来；确认工作树改动后**不要动它们**。
2. git switch -c fix/v2-single-model feat/ai-jobs-sidecar-20261102
3. 停应用（stop.cmd），然后用文档 Phase 0 给的 sqlite3.backup 脚本做备份。
   不要用 cp。
4. 新建 docs/quality/fork-baseline.md，按文档给的四个二级标题填。
   后端全量测试必须真跑，把失败清单逐条列进第 4 节。
   已知：tests/test_resume_hidden_sections.py 有 3 条失败，属于预存量，要列进去。
5. 跑 backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 0，全绿为止。

禁止：改任何业务代码、跑 Phase 1、重新创建 scripts/v2_gate.py。
完成后停下，贴出：闸门原始输出 + docs/quality/fork-baseline.md 的路径 + git status。
```

#### 卡片 1（Phase 1）

```text
仓库：D:\飞牛文件同步\工作\简历通
任务：只执行 docs/fork-v2-compatibility-plan.md 的 Phase 1。

前置确认：Phase 0 已绿（docs/quality/fork-baseline.md 存在、备份存在）。

按顺序做，每步做完跑一次闸门：
1. 创建 scripts/normalize_resume_documents.py（文件头必须带 sys.path 引导，见文档 Phase 1）。
2. 跑 --dry-run --json，把输出贴出来。人工看 visibility_changes：
   它列的是"迁移后哪些板块会从纸面上消失"，这是修复不是 bug。
3. 创建 backend/tests/test_normalize_resume_documents.py，覆盖文档列的 6 条。
4. 停应用，跑 --apply --json。
5. 跑 backend/.venv/Scripts/python.exe -I scripts/v2_gate.py --phase 1，全绿为止。
6. 启动应用，按文档 §6.4 前两项冒烟，把结果写进第 9 章。

禁止：动 Phase 2 的任何文件（document_invariants.py / resume_record.py / generate_routes.py）。
禁止：用 cp 备份。禁止：修改已存在的测试。
完成后停下，贴出：闸门原始输出 + dry-run 的 JSON + 冒烟结果。
```

#### 卡片 2（Phase 2）

```text
仓库：D:\飞牛文件同步\工作\简历通
任务：只执行 docs/fork-v2-compatibility-plan.md 的 Phase 2。

严格按 2.1 → 2.2 → 2.3 → 2.4 → 2.5 的顺序，每完成一小节跑一次闸门。

最容易做错的三件事（做错会删用户数据，务必对照）：
- 修订路径传 page_limit=None，不要传记录页数。实测记录 40 会被裁掉一个项目。
- 经历去重键用 (company, role, period)，不能只用 company。
- finalize_ai_document 里 parse_document 必须是最后一步，不是第一步。

禁止：改渲染器、改 export_pipeline、改 document_html.py。
禁止：把测试断言改松。
完成后停下，贴出：闸门原始输出 + 四步人工冒烟结果 + 第 9 章更新。
```

#### 卡片 3（Phase 3）

```text
仓库：D:\飞牛文件同步\工作\简历通
任务：只执行 docs/fork-v2-compatibility-plan.md 的 Phase 3。

只做三件事：
1. persistable_format_config 一起丢掉 hidden_sections（一行级改动）。
2. 前端 utils/resumeSectionOrder.ts 的 buildSectionOrderConfig 不要把 hidden_sections 带进请求。
3. 删 frontend/src/components/resume/ResumeHiddenSectionsControl.tsx（先 grep 确认无 import）。
   不要删 i18n key，sections.hidden.* 还有别处在用。

新增 backend/tests/test_section_visibility_exports.py（四格式对拍）。

已知：backend/tests/test_resume_hidden_sections.py 现在有 3 条失败，
Phase 3 结束时它们必须转绿 —— 那是本阶段要修的行为，不是新引入。
不要改它们的断言。

禁止：重构导出管线（它已经是对的）。禁止：改渲染器。
完成后停下，贴出：闸门原始输出（含"旧隐藏板块测试全绿"这一行）。
```

#### 卡片 4（Phase 4）

```text
仓库：D:\飞牛文件同步\工作\简历通
任务：只执行 docs/fork-v2-compatibility-plan.md 的 Phase 4。

创建 scripts/check_v2_boundary.py，按文档列的四类检查实现：
1. v1 形状消费（AST）
2. record.content 的使用形态白名单（当实参 / 哈希比较白名单）
3. hidden_sections / section_order 的写入
4. 迁移文件名前缀唯一 + heads 单头 + down_revision 存在

禁止按"record.content 出现次数"做 allowlist —— 实测 40 处里危险写法是 0 处。

反向验证必须做：往 backend/app/api/ 临时加一行 record.content.get("projects")，
守卫要报错；删掉后全绿。把这个过程写进第 9 章。
然后把它接进 scripts/Check-All.ps1。

完成后停下，贴出：闸门原始输出 + 反向验证的前后两次输出。
```

#### 卡片 5（Phase 5）

```text
仓库：D:\飞牛文件同步\工作\简历通
任务：只执行 docs/fork-v2-compatibility-plan.md 的 Phase 5。

先写同形不变量测试（backend/tests/test_document_shape_invariants.py），
它比业务矩阵更重要：对同一份记录，详情/导出/preflight/招呼语上下文取出的文档
规范化后必须完全相同。用测试夹具造数据，不要依赖真实库。

再写业务回归矩阵，矩阵用文档 §5.2 那张（注意"记录原本是 v1"那一列）。
F01 招呼语只测"以「您好，」开头"这一条确定性不变量（其余是提示词约束）。

完成后停下，贴出：闸门原始输出 + 覆盖到的矩阵格子清单。
```

### 11.2 给 GLM-5.3-flash 的性能调优要点

如果你的客户端能调参数，按这张表设置；不能调就靠提示词达成同样的效果。

| 目标 | 做法 | 为什么对便宜模型有效 |
|---|---|---|
| 减少“自由发挥” | 每轮只给一张任务卡（11.1），全文粘贴，不改写 | 任务边界由人写死，模型不做范围判断 |
| 减少幻觉文件路径 | 文档里所有路径都是完整相对路径 + 行号 | 模型只需要复制，不需要推断 |
| 减少“以为跑过了” | 要求贴**闸门原始输出**，不接受“已通过”四个字 | 输出是外部证据，不能编 |
| 减少长上下文串味 | E8：每阶段只读 ≤4 个文件 | 便宜模型的长上下文召回质量下降更快 |
| 减少返工 | 每次改一个文件就重跑闸门 | 失败定位从“整个阶段”缩到“一个文件” |
| 提高首次正确率 | 文档直接给函数签名、文件头写法、备份脚本 | 让模型抄，而不是设计 |
| 降低不可回滚风险 | 每阶段单独提交 + 备份 | 出错退一步，不用重来 |
| 抑制“优化冲动” | E3 明令禁止重构，只能写进执行记录 | 便宜模型喜欢“顺手改进”，这是主要 bug 来源 |
| 兜住判断失误 | E6：冲突就停下问，并记录冲突点 | 比让它二选一后再返工便宜得多 |

**温度/采样建议**：如果客户端暴露这些参数，用较低温度（0–0.3）跑 Phase 1–4 这类确定性改造；Phase 5 写测试可以略高（0.3–0.5）。不要用高温跑数据迁移。

**分轮策略**（重要）：不要把 Phase 0–6 塞进一次会话。建议：

```
第 1 轮：卡片 0        → 停，人工看一眼基线文档
第 2 轮：卡片 1        → 停，人工看一眼 dry-run 的 visibility_changes
第 3 轮：卡片 2        → 停，人工做四步冒烟
第 4 轮：卡片 3 + 4    → 停
第 5 轮：卡片 5 + 6    → 停，全量闸门 --all
```

每轮开始前 `git status` 必须是干净的（上一轮已提交）。如果脏了，先让模型只提交、不改代码。

---

## 12. 本版相对第一版的修订清单

| 编号 | 第一版写法 | 本版处理 | 依据 |
|---|---|---|---|
| R1 | Phase 0 用 `cp` 备份 | 改 `sqlite3.backup`，回滚加删 `-wal`/`-shm` | 实测 WAL 下朴素 cp 会丢数据，极端情况连表都没有 |
| R2 | “SSE 最终仍走 save_record 收口” | 删 `document=` 旁路，SSE 与落库共用同一份返回值 | 实测 6 个项目绕过去重全部落库 |
| R3 | “校验 → 去重 → 清理 → 不再校验” | 改为“归一 → 变换 → 校验 → 序列化” | 实测合并后 1000 > 500，`parse_document` 失败 |
| R4 | 修订复用生成的全部后处理 | 拆 `dedupe_resume` / `limit_resume`，修订只去重不截断 | 记录 40：7 个项目会被裁到 6 |
| R5 | 经历按公司去重 | 改成 `(company, role, period)` | 实测两段同公司不同职位被合并成一条 |
| R6 | `hidden_sections` “接受但丢弃即可” | 明确 `persistable_format_config` 必须一起删；前端 `{...base}` 也要处理 | 实测键会从生成路径写回 |
| R7 | Phase 3 “确认四个出口”算待办 | 改为“导出已统一，只加对拍测试，不改渲染器” | 六个出口实测都过 `paper_document` |
| R8 | Phase 4 按 `record.content` 出现次数做 allowlist | 改为按“形状消费”AST 判定 | 40 处中危险写法 0 处，按次数做守卫必然失效 |
| R9 | Phase 4 检查 revision id 唯一 | 改为检查文件名前缀唯一 | revision 字符串本来就唯一，查它永远绿 |
| R10 | 数字 10/4 份、110 处、44 处 | 改为 9/3 份（live）、40 处、293/85 | 实测 |
| R11 | 用 `npx` | 改 `npm run typecheck` / `npm run lint` | 仓库规则 “No npx” |
| R12 | Phase 5 矩阵含不可达格子 | 改为“请求体版本 / 记录原本版本”两列 | Phase 1 后记录层不再有 v1 |
| R13 | F01 六条不变量当作已有保证 | 标注“仅开头有确定性实现”，给出 A/B 两条路线 | 代码里只有 `normalize_greeting_opening` |
| R14 | 无机器验收 | 新增 `scripts/v2_gate.py` + 每阶段闸门命令 | 让便宜模型有可复现的目标 |
| R15 | 未标注“已修但未提交”的条目 | §1.3 标出 P5 已修、P2 位置已变 | 避免重复实现 |
