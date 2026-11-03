# 对《v2 单模型兼容性整改开发文档》的对抗性审查

> 审查对象：`docs/fork-v2-compatibility-plan.md`（2026-11-03 版）
> 审查方式：第一性原理重推 + 对每条结论做可执行验证（读代码 / 跑脚本 / 造数据复现）
> 审查日期：2026-11-03
> 结论：**方向正确，但有 4 个会让整改直接失效或造成数据事故的问题，必须先改文档再动手。**

---

## 0. 一句话结论

文档把问题定义成"同一功能有两条数据路径"，这个判断是对的；但它给出的**收口点并不唯一**（`document=` 旁路）、**校验顺序是反的**（先校验后破坏）、**备份方式在 WAL 下会丢数据**、**要清理的旧键仍能从正常业务路径写回来**。这四条不修，Phase 1–4 做完后第 5 天就会复发。

---

## 1. 第一性原理：这份方案在解决什么

把文档的目标拆到最底层，其实只有三个命题：

1. **存储层只有一个形状**（库里的 `content` 永远是 v2）；
2. **写入只有一个入口**（任何 AI/手工/工具写入都经过同一段后处理）；
3. **不变量在入口处被强制执行**（不是提示词，不是 reviewer checklist）。

当前代码的真实状态是：

| 命题 | 文档假设 | 实测 |
|---|---|---|
| 存储单形状 | 10 份 v1 待转 | 9 份 v1（live）+ 14 份软删 v1；v2 3 live + 14 软删 |
| 写入口唯一 | `save_record` + `save_content` | `save_record(document=...)` 直接跳过全部后处理 |
| 不变量强制 | `finalize_ai_document` 一个函数 | 校验发生在后处理**之前**，后处理可产出非法文档 |

所以真正要补的不是"再加一层兼容"，而是**把"校验"移到"所有变换之后"**，并把 `save_record` 的旁路堵死。文档现在的写法会让接手者以为这两件事已经成立。

---

## 2. P0：不修则整改失效

### P0-1 备份与回滚在 WAL 模式下不成立

**文档写法**（§4 Phase 0）：

```bash
cp backend/data/resume_forge.db backend/data/resume_forge.db.pre-v2-normalize-$(date +%Y%m%d-%H%M%S).bak
```

**问题**：当前库是 `journal_mode=wal`，且存在活跃的 `resume_forge.db-wal`（实测 10 MB）。只复制主库文件会丢掉 WAL 里已提交但未 checkpoint 的事务。实测复现（新建 WAL 库、关闭 autocheckpoint、提交两行后只 `cp` 主文件）：

```
src sees: (2,)  wal size: 16512
naive cp sees:  sqlite3.OperationalError: no such table: t
```

也就是说，极端情况下备份出来的文件**连表都没有**；正常情况下也会丢最近的简历/招呼语改动。

**回滚同样有问题**：文档写"用备份覆盖 `backend/data/resume_forge.db`"，但没有要求删除 `-wal` / `-shm`。残留的 WAL 会在下次打开时被重放，把恢复后的库再次改回"坏状态"。

**改法**（仓库里已有现成实现，直接复用）：

- 备份走 SQLite 在线备份 API：`sqlite3.connect(src).backup(sqlite3.connect(dst))`，`scripts/import_portrait.py:257-270` 的 `_backup_database()` 就是这一套；
- 或在**停应用**后执行 `PRAGMA wal_checkpoint(TRUNCATE)` 再复制（并把 `-wal/-shm` 一起复制或确认已清空）；
- 回滚步骤增加：先删 `resume_forge.db-wal`、`resume_forge.db-shm`，再覆盖主库；
- Phase 1 的 `--apply` 必须要求应用已停止（SQLite 写锁 + 进程内 identity map 都不可控）。

---

### P0-2 `save_record(document=...)` 旁路：不变量根本没在"唯一写入口"执行

**文档写法**（§4 Phase 2 表格）："`generate_routes.py` 的流式解析……保留可，但确保最终仍走 `save_record` 的收口"。

**事实**：`save_record` 确实会做去重/限量/技术栈清理，但那段代码只作用于入参 `content`；一旦调用方传入 `document=`，落库用的是**传入的那份 document**，而它是在后处理之前构造的（`backend/app/services/resume/resume_record.py:143-173`）。`generate_routes.py:291` 先 `ensure_document_version(parsed)` 得到 `document`，`resume_record.py:325` 再把它原样传进去——`parsed` 被去重了，`document` 没有。

**实测复现**（构造 6 个项目、含同名重复、`page_limit=1`）：

```
document= (SSE/落库共用) projects: [('同名项目',…), ('同名项目',…), ('P2',…), ('P3',…), ('P4',…), ('P5',…)]
document unchanged after dedupe/strip: True
has tech_stack item in document: True
```

预期落库 3 条（1 页上限）、同名合并；实际落库 6 条、重复保留。

**影响**：UI 走的是后台任务（`/generate/tasks` → runner，不传 `document=`），所以主链路是对的；但 SSE `/generate` 端点、以及任何"复用同一份转换结果"的调用方都绕开了不变量。**文档里"最终仍走 save_record 的收口"这句话是错的**，下一个人会据此认为洞已经堵上。

**改法**：二选一，写进文档并加测试：

1. 删掉 `document=` 参数，SSE 的 `done.resume` 与落库各自从 `finalize_ai_document` 的结果取（同一份返回值，不会出现两份形状）；
2. 保留参数，但在 `save_record` 里对传入的 `document` 也跑一遍 `finalize_ai_document`，并断言"落库 document 与 done.resume 逐字节相同"。

---

### P0-3 `finalize_ai_document` 的顺序是反的，且能产出非法文档

**文档写法**（§4 Phase 2）：

```
1. prepare_document_for_save(...)   # 转换 + id 校验 + normalize
2. dedupe_and_limit_resume(...)
3. strip_resume_tech_stack(...)
4. 返回同一个 dict，调用方不得再二次转换
```

问题在于第 1 步已经把文档 `parse_document` 校验过了，第 2 步却在**校验之后**改动结构，而且第 4 步明确禁止再次校验。这等于"先过安检再装箱"。

**实测反例**：两条同名项目各自带 500 个 `tech_stack` 值（正好等于 `MAX_LIST_VALUES`），合并后变成 1000 个：

```
valid before dedupe: True
merged list length: 1000  limit: 500
re-parse: FAILED -> sections.0.entries.0.items.1.list.values: List should have at most 500 items …
```

后果分两种，都很难看：落库成功但库里有非法文档（下次读取/导出 422）；或在别的路径被 422 挡住，用户看到"生成内容无法落库"却查不出原因。

**改法**：把 finalize 定义成一次**纯函数流水线**，校验永远在最后：

```python
doc = ensure_document_version(content, …)       # 只做版本归一
doc = dedupe_and_limit_resume(doc, page_limit=…)  # 无损合并 + 截断
doc = strip_resume_tech_stack(doc) if not include else doc
normalized = parse_document(doc)                # 唯一校验点（归一化后再校验）
validate_document_ids_v2(normalized)
return document_to_json(normalized)
```

并在 `resume_dedupe` 里给合并后的 `values` 加 `[:MAX_LIST_VALUES]`（合并是加法，必须自己守住上限）。

---

### P0-4 `hidden_sections` 仍然能从正常业务路径写回库

文档 §2.4 说"不允许新增 `format_config.hidden_sections` 的写入"，§4 Phase 3 说"`prepare_document_for_save` 不再写回这两个键；现有 `validated_format_config` 保留'接受但丢弃/迁移'的行为即可"。

**事实是它现在既不丢弃、也不迁移，而且会被前端带回来**：

1. `resume_sections.py:118-130` 的 `persistable_format_config` 只删 `section_order`，`hidden_sections` 原样保留；
2. `resume_template_format.py:176-181` 的 `validated_format_config` 又把 `hidden_sections` 收进结果；
   实测：`validated(persistable({"hidden_sections":["awards","skills"],…}))` → `{'hidden_sections': ['awards','skills'], …}`；
3. 前端 `utils/resumeSectionOrder.ts:87` 的 `buildSectionOrderConfig` 是 `{...base}`，`GenerationConfigStage.tsx:293` 把底稿的整份 `format_config` 透传给生成请求；
4. `save_record` 落库前走 `validated(persistable(merged_config))`，`hidden_sections` 因此被持久化。

于是：Phase 1 把 12 条记录的这个键清干净后，用户只要"以某份旧简历为底稿生成一次"，键就回来了。Phase 4 的守卫如果按文档写的 allowlist（放行 `resume_template_format.py`），恰好会**放过唯一的写入口**。

**改法**：

- 把 `hidden_sections` 并入 `persistable_format_config` 的丢弃清单（和 `section_order` 同处），`validated_format_config` 只保留读取/迁移用途；
- 在 `_ordered_sections` / 转换器里保留"读旧键"的兼容，但任何写路径都不再产出该键；
- Phase 4 守卫不要放行 `resume_template_format.py` 的**写**分支——正确做法是让那里物理上不存在写分支。

---

## 3. P1：会误伤用户数据或让接手者做错事

### P1-1 "AI 修订也做页数收敛"= 静默删条目

文档 Phase 2 要求 `/revise` 走同一个 `finalize_ai_document`（含 `dedupe_and_limit_resume(page_limit=record.page_limit)`），并在测试里断言"2 页上限 → 项目数量符合规则"。

但 `dedupe_and_limit_resume` 不只是"合并"（无损），它还会 `entries[:limit]` **截断**（`resume_dedupe.py:158-185`）。实测现有记录 id=40：`page_limit=3` → `(6, 4)`，而它当前有 **7 个**项目。也就是说，用户只要对这份简历点一次"AI 修订"，就会**凭空少一个项目**，而且没有任何提示。

这直接违反文档自己写下的第 4 条硬性约束"不删除任何用户简历/资料/投递记录"。

**改法**（把"合并"和"截断"拆开）：

- `dedupe`（按身份合并要点）：生成、修订都可用，无损；
- `limit`（按页数截断）：只在**生成本身**用，且只能裁"本次模型新增的条目"，不能裁用户已有条目；
- 修订路径只用 dedupe，并在测试里加一条"7 项目简历修订后仍是 7 项目"。

附带风险：事实锁按 `object_id` 定位，找不到时**回退同栏目同下标**（`content_locks.py:80-93`）。截断让后面的条目整体前移，回退逻辑就会锁到**别的条目**上——这是"看起来没报错但锁错了"的那类 bug。

### P1-2 F07 写的"打开时能恢复"没有实现

文档 §5.2 F07：`关闭时 placement=hidden；打开时能恢复（数据未被删除）`。

实测：`hidden_from` 这个字段**只在** `resume_tech_stack.py:82` 被写入，全仓库没有任何读取点（`grep -rn hidden_from backend/app` 只有这一处）。也就是说，把开关重新打开，之前被隐藏的技术栈**不会回到纸面**，用户只能逐条手工改 `placement`。

二选一：

- 实现恢复：读取偏好从 off→on 时，把 `hidden_from` 非空的项 `placement = hidden_from` 并清空 `hidden_from`（放在设置保存的服务里，不进渲染）；
- 或把不变量改成如实描述："数据保留在文档里，但自动恢复不保证，需要手工拖回"，Phase 5 不要写一条会失败的测试。

### P1-3 Phase 1 会让"隐藏板块"第一次真正生效，这是可见变化

文档 P3 的症状写成"预览藏了导出还在，或反过来"，容易让人以为只是显示不一致。实测现状更彻底：**旧键完全不生效**。

- `document_converter.py` 全文没有读 `hidden_sections`（只有 `section_order`）；
- 实测记录 id=9（v1，`hidden_sections=['awards','campus_experience','skills']`）：转换后 `section.hidden` 全是 `False`，`paper_document` 输出仍是 `['summary','education','experience','projects','skills']`；
- 四个导出都走 `paper_document`（已统一），所以现在"藏"这件事对纸面**完全没作用**。

因此 Phase 1 的迁移会让 12 条记录里的 skills/awards/campus **第一次真的从纸面上消失**。这是修对了，但它是一次用户可见的内容变化，必须当成迁移风险来管理：

- `--dry-run` 报告要逐条列出"这条记录转换后哪些板块会从纸面消失"；
- 验收标准从"v1 数量 = 0"扩成"v1 数量 = 0 且每条记录的可见板块变化都在报告里被人工确认过"；
- 风险表补一行"隐藏设置首次生效导致简历变短"。

### P1-4 Phase 4 的守卫指标选错了

文档要"禁止 `record.content` / `resume.content` 出现在 allowlist 之外"，allowlist 只给 `document_io.py`、`document_converter.py`、迁移脚本、测试。

实测：`(record|resume|row|current).content` 共 **40 处 / 28 个文件**，其中大多数是**合法**的——喂给 `document_for_record`、喂给 `ensure_document_version`、参与 sha256、冻结交付快照、`document_save` 里比较原文。而"真正危险的写法"（拿 `record.content` 当 v1 或 v2 直接取键，如 `.content.get("projects")`）实测是 **0 处**。

按文档实现，结果只有两种：要么 allowlist 膨胀到 35+ 条（守卫形同虚设），要么正常代码全红（守卫被关掉）。这正好是文档自己列的"allowlist 太宽 → 守卫失效"风险。

**改法**：守卫检查"形状消费"，不检查属性出现：

1. 禁止 `record.content` 的**下标/取键**直接访问 v1 字段（`projects` / `experience` / `educations` / `tech_stack` / `hidden_points` …）；
2. 要求 `record.content` 的出现必须满足三种形态之一：直接作为 `document_for_record(...)` / `ensure_document_version(...)` / `coerce_document(...)` / `paper_document(...)` 的实参；或出现在 `document_save.py` / `resume_delivery.py` / `ai_jobs/resume_sync.py`（哈希/比较）的白名单里；
3. 用 AST 而不是正则（正则会把 `response.content`、`message.content`、`part.content` 全算进来，现在 `backend/app` 里 `.content` 共 201 处）。

### P1-5 Phase 3 的导出部分基本已经做完了，不要重写

文档 Phase 3 要求"确认 HTML/PDF/Word/Markdown 四个出口都只从 `paper_document` 取可见板块"，并把它当成一项待办。

实测：**已经统一**。

- `exporter.py:92`（JSON）、`exporter.py:142`（HTML）、`pdf_exporter/fit.py:88/339`、`docx_exporter.py:242`、`markdown_export.py:134`、`txt_exporter.py`（复用 markdown）全部先过 `paper_document`；
- `document_html.py:191-220` 是唯一的可见性过滤点；
- `export_pipeline.py:122/191` 还在传 `resolved_visible_sections(context.format_config)`，但 `export_markdown` 的 docstring 明确说这个参数"仅为兼容旧调用方保留"，v2 顺序由 `document.sections` 决定。

所以 Phase 3 的真实工作量只有两件：**把旧键迁进 `section.hidden`**（Phase 1）+ **删死控件**。文档不写清楚这一点，接手模型很可能去"重构导出管线"，白干一轮还引入回归。建议把 Phase 3 改成："导出已单源，只加对拍测试锁住现状；不要改渲染器。"

### P1-6 招呼语的不变量没有确定性校验

§5.2 F01 列了 6 条硬不变量，Phase 5 要求测试"开头必须是「您好，」且不含学校/学历/届别"。

实测代码里只有一条被真正执行：`normalize_greeting_opening`（`job_match.py:473-491`）补「您好，」。**没有**任何服务端校验检查"是否含学校/学历/届别/毕业时间"，也没有"正好五句""140–220 字"的校验（`parse_greeting` 只做长度上限 500 截断）。这些全靠提示词。

也就是说 Phase 5 那条测试只能覆盖"用假 provider 返回固定串"的回归，不能保证线上不出现学历。两种写法都行，但要写明：

- 要么加确定性守卫（禁用词表 + 句数 + 字数 + 「」引用存在性，违规重试一次再落库）；
- 要么把不变量降级成"提示词约束 + 抽样人工检查"，Phase 5 不要写一条伪装成保证的测试。

另外文档与提示词有两处口径不一致，先统一再写测试：

| 项 | 文档 §5.2 F01 | `prompts/apply_greeting.md` |
|---|---|---|
| 数字 | "不超过 1–2 个" | "数字是否不超过 1 个" |
| 能力/工具 | "1 个项目 + 1–2 个能力" | 第 4 句固定"1 个工具 + 1 个能力" |

### P1-7 Phase 5 的矩阵有不可达的格子

矩阵里"AI 修订 / v1 输入 / 有"和"手工保存 / v1 输入 / 有"：Phase 1 之后库里不存在 v1 记录，`/revise` 只会拿到 `document_for_record` 转好的 v2（`revise_resume` 对 dict 走的是 `revise_document` v2 路径）。v1 只可能以**请求体**形式出现在保存类接口，不会出现在"记录 → 修订"这条链上。

**改法**：把矩阵的行定义从"输入版本"改成"请求体版本 / 记录版本"两列，并明确：

- 保存类接口：v1 请求体必须仍被接受（旧客户端）；
- 修订/导出/招呼语：输入永远是 v2，测试应断言"喂 v1 记录也能得到 v2 行为"，而不是"给修订接口喂 v1"。

---

## 4. P2：事实与可执行性

### P2-1 三处关键数字与实测不符（会影响工作量与 allowlist 设计）

| 文档 | 实测（2026-11-03） |
|---|---|
| v1 记录 10 份 / v2 4 份 | **live：v1 9 / v2 3**；含软删共 v1 23 / v2 17 |
| 直接读 `record.content` 约 110 处 | `(record\|resume\|row\|current).content` **40 处 / 28 文件**；`backend/app` 全部 `.content` 201 处 |
| 前端约 44 处引用 `ResumeContent` | **293 处 / 85 个文件**（非测试 182 处 / 54 个文件） |

第三条尤其要改：Phase 4/5 的工作量估计建立在"44 处"上，实际是 6 倍多。不过其中大部分是**测试夹具**和 `ContentLike = ResumeContent | ResumeDocument` 这类兼容签名，真正需要迁移的生产代码远少于 293——建议改成"54 个非测试文件，其中 X 个是双形状兼容层（可逐步收窄），Y 个是纯 v1 消费（必须迁）"，并给出分类清单。

### P2-2 命令不符合仓库自身规则

- §6.2 用了 `npx tsc` / `npx eslint`，但 `scripts/Check-All.ps1` 开头明确写着 "No npx (repo rule)"，应改为 `npm run typecheck` / `npm run lint`；
- `npm run test -- --run src/...`：`npm run test` 已经是 `vitest run`，再传 `--run` 是冗余参数，建议 `npm run test -- src/...`。

### P2-3 "迁移编号重复"的真实口径

文档说 `0069_apply_greeting_confirm` 与 `0069_profile_field_placement`、`0070` 两对重复，并让 Phase 4 检查"revision id 唯一"。

实测：`revision` 字段是完整字符串（`"0069_apply_greeting_confirm"` 等），**本来就唯一**，`alembic heads` 也确实是单头 `['0075_ai_job_link']`。重复的只是**文件名数字前缀**。所以 Phase 4 那条检查会永远绿，抓不到真实风险。

**改法**：守卫检查 `versions/` 下文件名前缀（`^\d{4}_`）唯一；`alembic heads` 单头单独一条；再加"`down_revision` 引用的 id 必须存在"。

### P2-4 新脚本的导入引导

Phase 1 的运行方式是 `cd backend && ./.venv/Scripts/python.exe ../scripts/normalize_resume_documents.py`。此时 `sys.path[0]` 是 `scripts/`，`import app.…` 会失败。仓库已有正确写法，文档应直接引用：`scripts/import_portrait.py:30-31`

```python
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
```

### P2-5 §1.3 的"现状"已落后于工作树，会导致重复实现

- P2 说"技术栈只在生成链路、去重只在 `save_record`"——实测 `resume_record.py:143-145` **已经**同时做 dedupe 和 strip；真实缺陷是 `document=` 旁路（P0-2）。
- P5 说"覆盖补全旧实现：项目亮点缺失时追加整个项目；技能按源下标合并"——`projectionContent.ts:448-502` 现在按身份匹配（`candidateMatchesName` + `fillProjectionCandidate`），工作树里已经修过（未提交）。
- Phase 2 表格里"`revise_existing_resume` 直接 `prepare_document_for_save` 后 `save_ai_revision`"是对的，但同文件的注释"修订算法产出的 v1 内容"已过时（`revise_resume` 对 dict 走 `revise_document`，是 v2 路径）。

接手模型按文档找"要新增的东西"，会重复实现已有功能，并在已有修复上再叠一层。建议 §1.3 每条标注"已修（未提交）/ 未修"，Phase 2 明确"dedupe/strip 已存在，本阶段只做收口与消旁路"。

### P2-6 Phase 1 的验收口径与目标不一致

目标写"消灭同一张表里两种格式"，脚本也处理软删记录，但验收命令只查 `where deleted_at is null`。要么把目标改成"未删除记录单形状"，要么检查语句去掉过滤。

另外 `revision = revision + 1` 对软删记录没有意义（不会有人拿它做条件写），可以只对 live 记录推进，报告里分开统计。

### P2-7 建议补一个"同形不变量"测试（这是最有价值的一条）

文档的 Phase 5 是按"功能 × 写路径"列矩阵，覆盖成本高且容易漏。更根本的写法是按**读入口**做不变量：

> 对库里每一条记录，分别经 详情 API / 导出 JSON / Markdown / preflight / 招呼语上下文 / 事实锁 取出文档，规范化后取 sha256，断言全部相同。

一个测试就能永久锁住 P1（同一功能时好时坏）和 P3（两套真相）这两类问题，而且不依赖具体业务规则。建议把它作为 Phase 5 的主测试，业务矩阵作为补充。

---

## 5. 建议对原文档做的具体修改（可直接照改）

1. **§4 Phase 0**：备份命令换成 sqlite3 backup API；明确"停应用"是备份与 apply 的前置条件；回滚步骤加删 `-wal/-shm`。
2. **§4 Phase 1**：
   - 增加硬约束"转换必须先用 `format_config` 排完序，再消费 `hidden_sections`、再删两个键"；
   - 增加 `--dry-run` 输出"每条记录纸面可见板块的变化"；
   - 验收命令去掉 `deleted_at is null`（或改目标口径）；
   - 补 `sys.path` 引导。
3. **§4 Phase 2**：
   - 把"1 校验 → 2 去重 → 3 清理 → 4 不许再转"改成"1 归一 → 2 去重 → 3 清理 → 4 校验并序列化"；
   - 删掉或修好 `document=` 旁路，并在验收里加"SSE 落库内容 = done.resume 内容"；
   - `/revise` 只用无损 dedupe，不做页数截断；补"7 项目修订后仍 7 项目"的测试；
   - `Document_tech_stack` 的"恢复"要么实现、要么改口径。
4. **§4 Phase 3**：明确"导出已单源，只加对拍测试，不改渲染器"；把 `hidden_sections` 从 `persistable_format_config` 的保留项移到丢弃项。
5. **§4 Phase 4**：
   - 守卫从"属性出现次数"改成"v1 形状消费 + 实参白名单"；
   - 迁移检查改成"文件名数字前缀唯一 + heads 单头 + down_revision 引用存在"。
6. **§5.2 F01/F07**：与提示词对齐数字口径；F07 如实描述恢复能力。
7. **§6.2**：`npx` 换成 `npm run typecheck` / `npm run lint`。
8. **§1.2/§1.3**：用实测数字替换 110/44/10/4；每条问题标注"已修（未提交）/ 未修"。

---

## 6. 本次审查的验证清单（可复核）

| 结论 | 复核方式 | 结果 |
|---|---|---|
| 库为 WAL 且有活跃 WAL | `PRAGMA journal_mode`；`ls data/*.db-wal` | `wal`，10 MB |
| 朴素 cp 会丢 WAL 提交 | 新建 WAL 库、关 autocheckpoint、提交后只 cp 主文件 | 拷贝里连表都没有 |
| `document=` 跳过不变量 | 构造 6 项目调 `save_record` 的等价流程 | 6 条、重复保留、document 未变 |
| 去重可产出非法文档 | 两条各 500 值同名项目去重后再 `parse_document` | 1000 > 500，校验失败 |
| 转换器不认 `hidden_sections` | 用真实记录 9 走 `document_for_record` + `paper_document` | `section.hidden` 全 false，5 个板块全在纸面 |
| `hidden_sections` 能写回 | `validated(persistable({...}))` | 键被保留 |
| `hidden_from` 只写不读 | `grep -rn hidden_from backend/app` | 仅 1 处写入 |
| 现有 v1 记录可无损转换 | 23 条 v1 全量 `prepare_document_for_save` | 23/23 通过 |
| v2 记录归一化幂等 | 17 条 v2 连续转换两次比较 | 无变化、0 条需重写 |
| 迁移单头 | `alembic heads` | `['0075_ai_job_link']` |
| 记录 40 的截断风险 | `page_limit=3` → 限 6 项目，实际 7 项目 | 修订即删 1 条 |
| 死控件确实无引用 | `grep -rn ResumeHiddenSectionsControl frontend/src` | 仅自身 |
