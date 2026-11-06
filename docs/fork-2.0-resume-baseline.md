# N8 简历侧移植 · 落点复核（R1，只读）

> 分支 `feat/resume-side`（从 `feat/fork-port` 88ae5ac 切出）
> 口径：四块逐项定位，**每行必须有证据**。不凭印象写 EXISTS。
> 结论先行：2.0 缺 `resume_dedupe` / `resume_tech_stack` / `generation_preferences` /
> `document_invariants` / `portrait_import`；**覆盖清单已存在**（R4 只补差异）。

## 总表

| 块 | 1.x 落点 | 2.0 落点 | 状态 | 改造要点 |
|---|---|---|---|---|
| ① 生成结果去重 | `services/resume/resume_dedupe.py` + `document_invariants.finalize_ai_document` | **无**。挂点候选：`services/resume/resume_record.py:save_record` / `document_io.prepare_document_for_save` | **GONE**（需移植 + 找挂点） | 2.0 没有 `document_invariants` 收口函数，`prepare_document_for_save` 是**所有**写路径的公共收口，不能往里塞（会波及手工保存）。挂点选生成专属的 `save_record` |
| ② 显示技术栈开关 | `services/profile/generation_preferences.py` + `schemas/generation_preferences.py` + `services/resume/resume_tech_stack.py` + `document_invariants` + `document_save._hide_tech_stack_when_disabled` | **无**（`grep show_tech_stack` 与 `include_tech_stack` 在 `backend/app/` 均 0 命中） | **GONE**（三条独立落点都要建） | 设置项照 1.x 用 `AppSetting` KV（2.0 `models/setting.py:12` 同款，表 `app_setting`）；两条路径：生成 `save_record`、手工 `document_save.save_content` |
| ③ 覆盖清单「从资料补上这段」 | `services/resume/resume_coverage.py` + 前端清单组件 + 补入 API | `services/resume/resume_coverage.py`（457 行）+ `services/resume/resume_profile_append.py` + `api/resumes/ai_edits_routes.py:append_entries_to_resume`（`POST /{resume_id}/append-profile-entries`）+ 前端 `api/resumeAppend.ts` / `components/resume/CoverageActions.tsx` | **EXISTS**（2.0 已有完整实现） | **不重写**。R4 只补差异 + 记 progress |
| ④ 画像导入 | `scripts/import_portrait.py` + `prompts/portrait_extract.md` + `services/profile/portrait_import.py` | **全缺**（三个文件 2.0 都没有）。目标表：`ClaimRecord`（`models/claim.py:125`）+ `ProfileEntry`（`models/profile_entry.py`，经 `services/profile/entry_store.py`） | **GONE**（目标改写：不写 `profile_facts`） | **1.x 本来就不写 profile_facts**，写的是 `ClaimRecord` + 资料条目。详见下方「重要更正」 |

---

## ① 生成结果去重

### 1.x

- `backend/app/services/resume/resume_dedupe.py`（222 行）：
  `dedupe_resume`（无损，按身份键合并要点取并集）/ `limit_resume`（有损，按页数截断）/
  `dedupe_and_limit_resume`（兼容包装）。
- 唯一收口：`backend/app/services/resume/document_invariants.py:52 finalize_ai_document`，
  序列为 `ensure_document_version → dedupe_resume → limit_resume(page_limit) →
  strip_resume_tech_stack → parse_document → validate_document_ids_v2 → document_to_json`。
- 调用方两处：`resume_record.py:163`（生成落库）、`ai_edits_routes.py:178`（AI 修订，`page_limit=None`）。

证据：

```
$ grep -rn "dedupe_resume\|dedupe_and_limit\|limit_resume" backend/app --include=*.py | grep -v resume_dedupe.py
backend/app/services/resume/document_invariants.py:35:from .resume_dedupe import dedupe_resume, limit_resume
backend/app/services/resume/document_invariants.py:69:    document = dedupe_resume(document)
backend/app/services/resume/document_invariants.py:71:        document = limit_resume(document, page_limit=page_limit)
```

### 2.0

```
$ ls backend/app/services/resume/resume_dedupe.py    → No such file
$ ls backend/app/services/resume/document_invariants.py → No such file
$ grep -rn "dedupe_resume" backend/app --include=*.py   → 0 命中
```

已有的相近能力（**不是同一件事**，不能顶替）：

| 已有 | 位置 | 作用范围 |
|---|---|---|
| `dedupe_skills` | `generation_normalize.py:98` | 只去重 `skills` 数组，按名称归一 |
| `_dedupe_lines` | `generation_normalize.py:66` | 同一条目内 `description`/`highlights` 的**行级**去重 |
| `profile_entry_merge` 文档字符串 | `services/profile_entry_merge.py:16` | 资料侧，不是简历侧 |

### 2.0 的写路径拓扑（决定挂点）

`document_io.prepare_document_for_save` 被 **9 处**调用，横跨生成、手工保存、AI 修订、
版本回滚、来源认领、素材替换、助手工具：

```
$ grep -rn "prepare_document_for_save" backend/app --include=*.py | grep -v "document_io.py"
api/resumes/ai_edits_routes.py:225
api/resumes/_shared.py:149            ← 手工保存（crud_routes 走这里）
schemas/resume.py:171                 （文档字符串）
services/assistant_tools/document_support.py:298
services/resume/manual_creation.py:136
services/resume/document_versions.py:333
services/resume/document_provenance_adopt.py:169
services/resume/resume_assets.py:263
services/resume/resume_record.py:165   ← 生成落库
```

**结论**：`prepare_document_for_save` 是公共收口，把去重塞进去等于让「手工保存也去重」
——违反 §10「去重删掉用户手动加的条目」红线。挂点必须是**生成专属**的
`resume_record.save_record`（SSE 与后台 runner 两条生成链路都走它，
`resume_generate_runner.py:363-367` 已证实）。

---

## ② 显示技术栈开关

### 1.x 三处落点

| 落点 | 文件:行 | 作用 |
|---|---|---|
| 默认值与读写 | `services/profile/generation_preferences.py:22,36,39` | `AppSetting` KV，key=`profile_generation_preferences`，`{"include_tech_stack": False}` |
| API | `api/profile.py:276,282` | `GET/PUT /profile/generation-preferences` |
| schema | `schemas/generation_preferences.py:8` | `include_tech_stack: bool = False` |
| 生成路径 | `document_invariants.py:72-73` → `strip_resume_tech_stack` | `not include_tech_stack` 时清空 |
| 手工保存路径 | `document_save.py:163 _hide_tech_stack_when_disabled` → `:255` 调用 | 唯一例外：手工保存也清（说明写在 `:166-180`） |
| 请求级覆盖 | `schemas/resume_generation.py:114` `include_tech_stack: bool \| None` | 单次生成可覆盖 |
| 清空实现 | `resume_tech_stack.py:strip_resume_tech_stack` | v1：清 `projects[].tech_stack` + 删「技术栈：」整行/行内；v2：`placement=hidden`（**保留数据**） |

### 2.0

```
$ grep -rn "show_tech_stack" backend/ --include=*.py    → 0
$ grep -rn "include_tech_stack" backend/app --include=*.py → 0
$ ls backend/app/services/resume/resume_tech_stack.py   → No such file
$ ls backend/app/services/profile/generation_preferences.py → No such file
$ grep -rn "AppSetting" backend/app/services/profile/*.py → 0
```

设置存法：2.0 `models/setting.py:12 class AppSetting`（表 `app_setting`，`key` PK +
`value` Text/JSON）**与 1.x 同构**，照它现有方式加即可。

`tech_stack` 在 2.0 的落点（说明数据侧不用改）：

```
$ grep -rn "tech_stack" backend/app --include=*.py | head
models/profile.py:174          tech_stack: Mapped[str]      （资料侧，逗号分隔）
schemas/resume_entries.py:117  tech_stack: list[ResumeLine] （简历条目侧）
services/resume/document_converter_specs.py:55  "lists": (("tech_stack","tech_stack","trail"),)
services/resume/bilingual_variants.py:56        "projects": ("tech_stack", ...)
```

`document_converter_specs.py:55` 里 `trail` 就是「会渲染到纸面」的 placement，
与 1.x 的 strip 实现（置 `hidden` + `hidden_from="trail"`）**完全对齐**，可逐字移植。

---

## ③ 覆盖清单「从资料补上这段」

### 判定：**EXISTS**（2.0 已有完整实现，不重写）

| 能力 | 2.0 文件 | 证据 |
|---|---|---|
| 缺什么 | `services/resume/resume_coverage.py`（457 行） | 模块 docstring：只读本次冻结的消费快照做集合比对 |
| 确定性补入 | `services/resume/resume_profile_append.py` | 模块 docstring：「不调模型，直接按生成时同一份投影写进文档」 |
| API | `api/resumes/ai_edits_routes.py:263 append_entries_to_resume` | `POST /{resume_id}/append-profile-entries` |
| 前端 API | `frontend/src/api/resumeAppend.ts:38` | `appendProfileEntries()` |
| 前端 UI | `frontend/src/components/resume/CoverageActions.tsx` + `CoverageGroupCard.tsx` | 有测试 `CoverageActions.test.tsx:143` 断言打到该 URL |
| 分支决策 | `frontend/src/components/resume/coverageGroups.test.ts:11` | 「补进简历 / AI 补上这段 / 去制作台添加」三态 |

**计划 §1.4 把这块写成「需核对」，R1 核对结果：全部已就位。**
→ R4 改成「只补差异 + 对抗验证」，不新增代码（详见 R4 记录）。

---

## ④ 画像导入（★ 重要更正）

### 计划书的前提有一处与代码不符

计划 §1.4 / §9.1 / §R5 都写「1.x 的事实写入 `profile_facts`，2.0 已删该表，要改目标」。
**实测 1.x 的画像导入本来就写 `ClaimRecord`，不写 `profile_facts`**：

```
$ grep -n "profile_facts\|ClaimRecord" backend/app/services/profile/portrait_import.py
33:    ClaimRecord,
472:        for row in db.query(ClaimRecord).filter(ClaimRecord.deleted_at.is_(None)).all()
527:        db.add(ClaimRecord(**claim))
```

模块 docstring 原文（`portrait_import.py:1-6`）：

> 「画像里的「做了什么 / 关键技术决策 / 结果 / 证据等级 / 边界 / 可迁移能力」不是资料库
> 13 个字段能完整容纳的：资料库只保留简历纸面可见的规范字段，**深度事实进 `ClaimRecord`**。」

`profile_facts` 在 1.x 只出现在**另一套功能**（`api/profile_facts.py`、`models/profile_fact.py`、
`services/profile/fact_store.py`）——那是扩展栏目的资料表，与画像导入无关。

### 因此 R5 的「目标改写」实际是：**确认目标已经是 claims，不要引入 fact_store**

| 项 | 1.x | 2.0 | 处置 |
|---|---|---|---|
| `scripts/import_portrait.py` | 有（14 KB） | 无 | 移植 |
| `prompts/portrait_extract.md` | 有 | 无 | 移植 |
| `services/profile/portrait_import.py` | 有（549 行） | 无 | 移植 |
| 写入目标 | `ClaimRecord` + `ProfileEntry`（经 `entry_store`） | `ClaimRecord`（`models/claim.py:125`）+ `ProfileEntry`（`services/profile/entry_store.py`） | **语义一致，不改目标** |
| `profile_facts` / `fact_store` | 存在 | 2.0 已删 | **不移植**（E14） |

### 依赖核对（移植可行性）

| 1.x 依赖 | 2.0 是否等价 |
|---|---|
| `app.models.claim` 常量（`CLAIM_CATEGORY_EXPERIENCE` / `CLAIM_CATEGORY_PROJECT` / `RESPONSIBILITY_LEVELS` / `VERIFICATION_CONFIRMED` / `PENDING` / `REJECTED` / `ClaimRecord`） | ✅ 全在 `models/claim.py:32-56,125` |
| `entry_store.list_entries(db, section_keys={...})` | ✅ `entry_store.py:244`（同签名） |
| `entry_store.bulk_save_entries(db, items)` | ✅ `entry_store.py:313`（同签名） |
| `workspace_bootstrap.ensure_workspace(db)` | ✅ `workspace_bootstrap.py` 存在 |
| `app.services.llm.create_provider` | ✅ `services/llm/__init__.py` |
| `get_llm_config(db)` | ⚠️ 1.x 从 `app.services.llm_settings` 取；2.0 是 `app.services.settings_service.get_llm_config`（`resume_generate_runner.py:57`） → **import 路径要改** |
| `app.database.SessionLocal` | ✅ `database.py` |
| `entry_store` 的字段校验 | ⚠️ 2.0 拆出了 `entry_store_fields._validated_values`，签名可能不同 → 移植后用 dry-run 实测 |

结论：**移植可行**，改动面 = 1 个 import 路径 + 可能 1 处字段校验调用。

---

## 附：本轮的挂点决策表（R2/R3 直接用）

| 改动 | 唯一挂点 | 为什么不是别处 |
|---|---|---|
| 去重 | `services/resume/resume_record.py:save_record`（`prepare_document_for_save` 之前） | 公共收口会让手工保存也被去重 |
| 技术栈 · 生成路径 | 同上（与去重相邻） | 与 1.x 的 `finalize_ai_document` 同级 |
| 技术栈 · 手工保存路径 | `services/resume/document_save.py:save_content`（`_check_content_budget` 之前） | 与 1.x `document_save.py:255` 逐字对齐 |
| 技术栈 · AI 修订路径 | `api/resumes/ai_edits_routes.py` 的 `finalize` 调用点 | 1.x 同样覆盖，避免「修订一次又露出来」 |
| 画像导入 | `scripts/import_portrait.py`（新文件） | 一次性离线脚本，不进运行时路由 |
