# N8 简历侧移植 · 执行日志（追加式）

> 分支 `feat/resume-side`，从 `feat/fork-port`（88ae5ac）切出。
> 每张卡：闸门输出 → 本节 → 单独提交 → taskboard。

## R0 分支校验与三件套

### 现场探测（开工）

```
$ git branch -vv
* feat/ai-jobs-sidecar e5fb384 docs(ai-jobs): 夜间执行报告（A0-A8 全绿收工）
  feat/fork-port       88ae5ac feat(2.0): BOSS 适配器移植（三处修复/Ego 浏览器/页内收录扩展挂载/单测）
  main                 d893243 chore: 上游 v2.0.0 基线 (53b813a7)

$ git status --porcelain
（空）
```

### 分支处置：**只 switch，不 merge**

计划 §1.3 要求把 A/B 两条分支合回主线；但本轮指令明确「线1 与线2 保持物理隔离，
不合并 AI 求职那两条分支」。所以 R0 收窄为：

```
$ git switch feat/fork-port
Switched to branch 'feat/fork-port'
$ git switch -c feat/resume-side
Switched to a new branch 'feat/resume-side'
```

N8 只动简历生成链路，不需要 ai_jobs 的任何代码；跳过合并不影响 R1–R8 的落点。

### 补齐缺失测试（计划 §1.4）

```
$ cp "/d/飞牛文件同步/工作/简历通/frontend/src/components/apply/queue/QueueItemEditor.test.tsx" \
     frontend/src/components/apply/queue/
$ git status --porcelain
?? frontend/src/components/apply/queue/QueueItemEditor.test.tsx
```

### 闸门基线（phase 0，R0 时刻）

```
===== Phase 0 =====
PASS 2.0 基线单提交且未被改写 — upstream-v2.0.0 提交数=1，是 HEAD 祖先=True
PASS 版本是 2.0.0 — frontend/package.json version=2.0.0
PASS 迁移文件数 < 10 — 数量=2 ['0001_baseline_v2.py', '0002_fork_apply_greeting_plan_aijob.py']
PASS 8010 健康检查 — 响应={'status': 'ok', 'name': 'ResumeForge', 'version': '2.0.0'}
PASS baseline 文档存在 — D:\飞牛文件同步\工作\简历通-2.0\docs\fork-2.0-baseline.md

汇总：PASS=5 FAIL=0 SKIP=0
```

### phase_9 设计口径（E10：建好之后不再改）

`phase_9` 沿用 phase_5 的既有约定：**未开工的能力输出 SKIP 并注明「R2 未移植」**，
已存在的能力必须满足。这样 R0 时刻闸门不会因为「N8 还没做」而变红，R8 时刻全项转 PASS。

重入保护：`phase_7` 的内部实现是 `for p in sorted(PHASES): PHASES[p]()`，
新增 9 之后会形成 7↔9 递归。`phase_9` 内置 `_IN_PHASE_9` 重入标志，
被 phase_7 回调时立即返回（不改 phase_7 一个字符）。

### phase_9 首次运行（R0 收口，L3）

```
===== Phase 9 =====
SKIP resume_dedupe.py 可导入 — R2 未移植（resume_dedupe.py 不存在）
SKIP 去重已接进生成链路 — R2 未移植
SKIP 去重与截断分离 — R2 未移植
SKIP 技术栈开关设置项 show_tech_stack 存在 — R3 未移植（schemas/generation_preferences.py 不存在）
SKIP 技术栈开关默认关 — R3 未移植
SKIP 技术栈两条路径都生效 — R3 未移植（resume_tech_stack.py 不存在）
PASS 覆盖清单补入能力存在或已记 GONE — resume_profile_append.py=True resume_coverage.py=True GONE登记=False
SKIP scripts/import_portrait.py 存在 — R5 未移植
SKIP 画像导入无 profile_facts 引用 — R5 未移植
SKIP portrait_extract.md 存在 — R5 未移植
SKIP N8 定向测试绿 — R2/R3/R5 测试均未移植
PASS 前 8 阶段复跑无 FAIL — 复跑 FAIL=0

汇总：PASS=2 FAIL=0 SKIP=10
```

前端 typecheck / build（计划 R0 步骤 3）：

```
$ npx tsc --noEmit -p tsconfig.json   → exit 0
$ npm run build                        → ✓ built in 989ms
```

### 偏差与处置：QueueItemEditor.test.tsx 未落地（BLOCKED-Q1）

计划 §1.4 要求 `cp` 1.x 的 `QueueItemEditor.test.tsx` 进 2.0。实测该测试三项全红，
原因**不是 2.0 有 bug**，而是它断言的两个功能属于 1.x 投递台的后续迭代，2.0 的
`QueueItemEditor.tsx`（127 行）没有它们：

| 测试断言 | 2.0 现状 |
|---|---|
| 「查看岗位 JD」展开拉 `/jobs/{id}` 并渲染 `.apply-queue-jd-body` | 组件里没有任何 JD 相关代码 |
| 「收起岗位 JD」缓存不重复请求 | 同上 |
| 项目下拉 + `focus_project` 传给 `previewGreeting` | 组件里没有项目下拉；`api/apply.ts:185` 只有类型字段 |

**处置**：删掉拷入的文件（保持 2.0 目录干净），登记 BLOCKED 后继续。
红线 §2.2#4 禁止改测试断言，而补这两个功能属于投递台（N3/N4 已验收范围，
§13 明确「不碰」）。见 `fork-2.0-resume-blocked.md`。

## R1 落点复核（只读）

产出 `docs/fork-2.0-resume-baseline.md`。四条结论：

| 块 | 判定 | 关键证据 |
|---|---|---|
| ① 去重 | **GONE**，需移植+找挂点 | 2.0 无 `resume_dedupe.py` / `document_invariants.py`；`grep dedupe_resume` = 0 |
| ② 技术栈开关 | **GONE**，三处落点全缺 | `grep show_tech_stack` / `include_tech_stack` = 0；但 `AppSetting` 与 1.x 同构 |
| ③ 覆盖清单 | **EXISTS**，2.0 已完整实现 | `resume_profile_append.py` + `POST /append-profile-entries` + 前端 `CoverageActions.tsx` |
| ④ 画像导入 | **GONE**，但**目标无需改写** | 1.x 画像导入本来就写 `ClaimRecord`，不是 `profile_facts` |

### 两处与计划书不符（以代码为准，E5）

**偏差 1（③）**：计划 §1.4 写覆盖清单「需核对」，§R4 准备移植。实测 2.0 已有完整实现
（后端 `resume_coverage.py` 457 行 + `resume_profile_append.py` + 专用 API + 前端组件 +
三条测试）。R4 改为「只补差异 + 对抗验证」，不新增代码。

**偏差 2（④，关键）**：计划 §1.4/§9.1/§R5 的前提是「1.x 画像导入写 `profile_facts`，
2.0 已删表所以要改目标」。实测**1.x 的画像导入写的就是 `ClaimRecord`**：

```
$ grep -n "profile_facts\|ClaimRecord" backend/app/services/profile/portrait_import.py
33:    ClaimRecord,
472:        for row in db.query(ClaimRecord).filter(ClaimRecord.deleted_at.is_(None)).all()
527:        db.add(ClaimRecord(**claim))
```

`profile_facts` 在 1.x 属于**另一套功能**（扩展栏目资料表 `api/profile_facts.py` /
`models/profile_fact.py` / `fact_store.py`），与画像导入无关。所以 R5 的「改目标」
落地为：**照 1.x 原本的 claims+资料条目目标移植，并且绝不引入 `fact_store`/`profile_facts`**
（这正是 E14 的本意）。phase_9 第 9 项「画像导入无 profile_facts 引用 == 0」照样成立。

### 挂点决策（R2/R3 直接用）

- 去重挂 `resume_record.save_record`（**不是** `document_io.prepare_document_for_save`：
  后者被 9 处调用，含手工保存，塞进去会删用户手动条目）
- 技术栈：生成路径挂 `save_record`；手工保存挂 `document_save.save_content`
  （与 1.x `document_save.py:255` 逐字对齐）；修订路径挂 `ai_edits_routes` 的 finalize
- 画像导入：独立离线脚本，不进运行时路由

## R2 生成结果去重

### 改动

| 文件 | 动作 |
|---|---|
| `backend/app/services/resume/resume_dedupe.py` | **新增**（移植 1.x，**只保留 `dedupe_resume`**） |
| `backend/app/services/resume/resume_record.py` | 加 import + 在 `save_record` 转换前后各调一次 |
| `backend/tests/test_resume_dedupe.py` | **新增**（6 个用例） |

**为什么砍掉 `limit_resume` / `dedupe_and_limit_resume`**：E15 与 phase_9 第 3 项要求
「去重与截断分离」。1.x 把两者塞进同一个模块甚至同一个包装函数，才出了
「点一次 AI 修订少一个项目」的事故。2.0 的篇幅控制已有两条独立链路
（`resume_space_gate.finalize_page_budget` 行预算、导出层按页收敛），不需要也不允许
`resume_dedupe` 再持有一份截断逻辑。

**为什么挂 `save_record` 而不是 `document_io.prepare_document_for_save`**：
后者被 9 处调用（含手工保存 `_shared.py:149`、版本回滚、来源认领、助手工具）。塞进去
等于让「用户手工保存」也被去重，直接违反 §10「去重删掉用户手动加的条目」。

**为什么转换前后各调一次**：SSE 链路（`generate_routes.py:283`）会把转换好的
`document` 传进 `save_record` 复用给 `done` 事件。v1 `content` 与 v2 `document` 是两个
对象，只处理一侧会让「落库内容」和「前端拿到的 done.resume」条目数不一致。

### L1 / L2 / L3

```
$ python -c "ast.parse(...)"                       → AST OK
$ python -c "import app.services.resume.resume_dedupe" → import OK ['dedupe_resume']
$ python -c "import app.services.resume.resume_record" → record import OK

$ pytest tests/test_resume_dedupe.py -q -p no:cacheprovider
6 passed, 1 warning in 0.61s

$ pytest tests/test_resume_section_order_materialize.py tests/test_resume_fact_annotations.py \
         tests/test_generation_normalization.py -q
16 passed, 1 warning in 2.54s
```

### L3（phase 9）

```
PASS resume_dedupe.py 可导入 — returncode=0
PASS 去重已接进生成链路 — 调用点=['services/resume/resume_record.py']
PASS 去重与截断分离 — resume_dedupe.py 命中违禁词=无
SKIP 技术栈开关设置项 show_tech_stack 存在 — R3 未移植（schemas/generation_preferences.py 不存在）
SKIP 技术栈开关默认关 — R3 未移植
SKIP 技术栈两条路径都生效 — R3 未移植（resume_tech_stack.py 不存在）
PASS 覆盖清单补入能力存在或已记 GONE — resume_profile_append.py=True resume_coverage.py=True GONE登记=False
SKIP scripts/import_portrait.py 存在 — R5 未移植
SKIP 画像导入无 profile_facts 引用 — R5 未移植
SKIP portrait_extract.md 存在 — R5 未移植
PASS N8 定向测试绿 — returncode=0；6 passed, 1 warning
PASS 前 8 阶段复跑无 FAIL — 复跑 FAIL=0

汇总：PASS=6 FAIL=0 SKIP=6
```

### E13 改前/改后对照（同一份内容，绕过 vs 经过 `dedupe_resume`）

输入：6 个项目（含 1 组同名对、1 组「CreatorDistill」相似对、1 条无身份半成品）
+ 2 条完全相同经历。

| 项 | 改前 | 改后 | 判定 |
|---|---|---|---|
| 项目数 | 6 | **5** | 只合并完全同名的那一对 |
| 经历数 | 2 | **1** | 复合身份 (company, role, start, end) 全同才合并 |
| 合并后第一条要点 | desc=[闭环] / hl=[] | desc=[闭环] / **hl=[20 个 API]** | 并集，内容没丢 ✅ |
| 相似条目（CreatorDistill ×2） | 2 | **2** | 都保留 ✅ |
| 无身份半成品 | 1 | **1** | 保留 ✅ |
| 经历合并后 description | — | `['补充要点']` | 并集 ✅ |

原样输出见本节末尾「E13 原始输出」。

### 一次 FAIL 与处置（未改闸门）

phase_9 首跑报 `FAIL 去重与截断分离 — 命中违禁词=['truncate']`。根因是我的**模块
docstring 里写了 `document_truncate` 这个模块名**（字符串包含 `truncate`），代码本身
没有任何截断逻辑。处置：改写那句话，不提该模块名——闸门一个字未改（E10）。

### E13 原始输出

```
=== 改前（无去重） ===
projects: [["AI 简历工作台",1,0],["民生账号",1,0],["AI 简历工作台",0,1],
           ["CreatorDistill 创作者内容分析系统",0,0],["CreatorDistill 爆款拆解语料库",0,0],["半成品",1,0]]
experience: [["蓝粤","测试工程师",false],["蓝粤","测试工程师",true]]
=== 改后（经 dedupe_resume） ===
projects: [["AI 简历工作台",1,1],["民生账号",1,0],["CreatorDistill 创作者内容分析系统",0,0],
           ["CreatorDistill 爆款拆解语料库",0,0],["半成品",1,0]]
experience: [["蓝粤","测试工程师",true]]
条目数 改前: 6 2 → 改后: 5 1
内容保全检查：合并后第一条是否同时有 description 与 highlights: True
相似条目是否都保留: ['CreatorDistill 创作者内容分析系统', 'CreatorDistill 爆款拆解语料库']
半成品是否保留: True
```

## R3 显示技术栈开关（默认关）

### 改动

| 文件 | 动作 |
|---|---|
| `backend/app/schemas/generation_preferences.py` | **新增** `GenerationPreferences{show_tech_stack: bool = False}` |
| `backend/app/services/profile/generation_preferences.py` | **新增**（`AppSetting` KV，key 沿用 1.x 字面量 `profile_generation_preferences`） |
| `backend/app/services/resume/resume_tech_stack.py` | **新增** `strip_resume_tech_stack` + `visible_tech_stack_count` |
| `backend/app/api/settings.py` | **加** `GET/PUT /api/settings/generation-preferences` |
| `backend/app/services/resume/resume_record.py` | 生成路径挂点（转换后，作用在 v2 上） |
| `backend/app/services/resume/document_save.py` | 手工保存 `save_content` + AI 修订 `save_ai_revision` 两处挂点 |
| `frontend/src/types/settings.ts` / `api/settings.ts` | 新增 `GenerationPreferences` 类型与两个客户端函数 |
| `frontend/src/features/settings/useShowTechStack.ts` | **新增**（照 `useWebFormRelaxedMode` 写法） |
| `frontend/src/components/settings/GenerationPreferencesCard.tsx` | **新增** 设置卡 |
| `frontend/src/components/settings/SettingsPanels.tsx` | 挂进「外观与交互」页 |
| `frontend/src/i18n/messages/{zh-CN,en-US}.settingsUi.ts` | 各加 7 个 key（中英相等） |
| `backend/tests/test_tech_stack_preference.py` | **新增**（6 用例） |
| `backend/tests/test_generation_preferences.py` | **新增**（3 用例） |
| `frontend/src/components/settings/GenerationPreferencesCard.test.tsx` | **新增**（2 用例） |

### 三条写路径都覆盖（1.x 只做了两条）

| 路径 | 落点 | 为什么 |
|---|---|---|
| AI 生成 | `resume_record.save_record` | SSE 与后台 runner 两条生成链路都走它 |
| 手工保存 | `document_save.save_content` | 1.x 踩过的坑：只在生成路径清，手工保存漏了 |
| **AI 修订** | `document_save.save_ai_revision` | 1.x 靠 `finalize_ai_document` 覆盖；2.0 没有那个函数，不在这里补就会「修订一次又露出来」 |
| 覆盖清单补入 | 走 `save_content` | 自动被第二行覆盖（补进来的条目 tech_stack 是 `placement=trail`） |

### 为什么作用在 v2 而不是 v1

`v1.projects[].tech_stack` 在 `document_converter_specs.py:55` 被转成
`placement=trail` 的 v2 列表项。只清 v1 的话转换器会按资料原值重新写回纸面。
所以 `save_record` 里必须先 `prepare_document_for_save` 再 strip。

### 关闭 = 不上纸面，不是删数据

v2 项置 `placement="hidden"` + `hidden_from="trail"`，`values` 原样保留（编辑器可拖回）。
打开开关**不自动恢复**已隐藏的项——与 1.x 同样的单向语义（只隐藏、不恢复）。

### L1 / L2 / L3

```
$ python -c "import app.api.settings; import app.services.resume.resume_record"
imports OK; default = show_tech_stack=False

$ pytest tests/test_tech_stack_preference.py -q      → 6 passed
$ pytest tests/test_generation_preferences.py -q     → 3 passed
$ pytest tests -q -k "resume_dedupe or tech_stack or save or content"
273 passed, 9 skipped, 6873 deselected in 90.39s

$ npx tsc --noEmit -p tsconfig.json                  → 无输出（通过）
$ npx vitest run src/components/settings src/pages/SettingsPage
32 files / 205 tests passed
$ npx vitest run src/i18n                            → 334 passed, 1 skipped
$ npx vitest run src/components/settings/GenerationPreferencesCard.test.tsx → 2 passed
$ npm run build                                      → ✓ built in 1.12s
```

L3：

```
PASS resume_dedupe.py 可导入 — returncode=0
PASS 去重已接进生成链路 — 调用点=['services/resume/resume_record.py']
PASS 去重与截断分离 — resume_dedupe.py 命中违禁词=无
PASS 技术栈开关设置项 show_tech_stack 存在 — backend\app\schemas\generation_preferences.py
PASS 技术栈开关默认关 — show_tech_stack: bool = False
PASS 技术栈两条路径都生效 — 生成路径=['services/resume/resume_record.py'] 手工保存=['services/resume/document_save.py']
PASS 覆盖清单补入能力存在或已记 GONE — resume_profile_append.py=True resume_coverage.py=True GONE登记=False
SKIP scripts/import_portrait.py 存在 — R5 未移植
SKIP 画像导入无 profile_facts 引用 — R5 未移植
SKIP portrait_extract.md 存在 — R5 未移植
PASS N8 定向测试绿 — returncode=0；12 passed, 1 warning
PASS 前 8 阶段复跑无 FAIL — 复跑 FAIL=0

汇总：PASS=9 FAIL=0 SKIP=3
```

### E13 改前/改后对照

```
v1（生成链路 content）: 可见技术栈 改前=1 → 改后=0
v2（落库 document）:    可见技术栈 改前=1 → 改后=0
数据保全（v2 项仍在，values 未丢）: ['React', 'FastAPI'] placement= hidden
正文清理（v1 description）: ['闭环交付。']
资料事实不受影响（资料侧 tech_stack 是另一张表，本模块不碰）: ok
```

### 接口实测

```
registered: []                      ← 运行中的 8010 是改动前启动的进程，故 404
GET 200 {'show_tech_stack': False}  ← 用 TestClient 走真实 app，默认关已确认
```

（未重启用户正在跑的服务；新路由在后端下次启动时生效。）

### 两次测试红与处置（都按"以代码为准"，未改断言精神）

1. `test_switch_off_strips_inline_tech_stack_lines` 首跑红：我写的预期是
   「……。技术栈：Docker、Caddy。」清完留「……」。实测 1.x 与 2.0 输出**逐字相同**
   （`["闭环交付一份可投的简历。", "做过端到端交付"]`——行内正则把句号一起吃了）。
   处置：断言改成 1.x 的实测输出，实现不动。
2. `en-US.settingsUi.ts` TS1005：我在双引号字符串里直接写了 `"Tech stack: ..."`。
   处置：转义成 `\"`。

## R4 覆盖清单「从资料补上这段」

### R1 结论复核：EXISTS，但**只覆盖自建分区**（一处真实差异）

2.0 已有的部分（R1 已列证据，不重写）：

| 能力 | 2.0 文件 | 现状 |
|---|---|---|
| 缺什么（集合比对） | `services/resume/resume_coverage.py`（457 行） | ✅ 在用 |
| 确定性补入 | `services/resume/resume_profile_append.py` | ✅ 在用 |
| API | `POST /api/resumes/{id}/append-profile-entries` | ✅ 在用 |
| 前端 | `api/resumeAppend.ts` + `CoverageGroupCard.tsx` + `coverageGroups.ts` | ✅ 在用 |

实测两条测试链全绿：

```
$ pytest tests/test_resume_coverage.py -q          → 14 passed
$ pytest tests/test_append_profile_entries.py -q   → 14 passed
$ npx vitest run src/components/resume/CoverageActions.test.tsx \
                 src/components/resume/coverageGroups.test.ts → 31 passed
```

### 差异（以代码为准）

| 项 | 1.x | 2.0 |
|---|---|---|
| 内置分区（项目/经历/教育）缺条目时 | 「从资料补上这段」→ `fillCoverageNote` 按身份确定性补进**已有条目**/追加 | `resolveCoverageAction` 只对 `custom:` 分区返回 `append`；内置分区一律 `revise`（AI 修订） |
| 自建分区缺条目 | 同上 | ✅ `append`（走 `/append-profile-entries`） |

证据：

```
$ grep -n "function resolveCoverageAction" -A10 frontend/src/components/resume/coverageGroups.ts
208:  if (canAppend && group.entryIds.length > 0 && isCustomSection(group.rawSection)) {
209:    return "append";

$ grep -n "_projected_custom_entries" -A12 backend/app/services/resume/resume_profile_append.py
145:    """``entry_id -> v1 自建条目``（与生成链同一份投影，含截断与空条目跳过）。"""
146:    projected = project_paper_content(consumed)
147:    for section in getattr(projected, "custom_sections", None) or []:
```

1.x 侧的对应实现是 `frontend/src/features/profile-library/projectionContent.ts`（615 行，
`fillCoverageNote` / `fillProjectionCandidate` / `mergeProjectionCandidate`），**前端**
按投影接口返回的候选做合并，不新增后端能力。

### 处置：登记 DEFERRED，不移植

理由（逐条对计划卡 R4 的约束）：

1. **卡 R4 步骤 1 写明「若 R1 判定 2.0 已有对应物 → 只补差异，不重写」。** 对应物确实存在，
   差异是"内置分区只能走 AI 修订"。
2. 补齐这条差异需要移植 `projectionContent.ts`（615 行）+ 改 `coverageGroups.ts` 的
   动作判定 + 在 `ResumeDetailPreview` 里接投影请求。这已经**超出「补差异」**，且
   `projectionContent.ts` 依赖 1.x 的 `ProfileProjection` 类型形状，2.0 的
   `PaperProjectionOut` 是另一套（`profile_workspace.py:150` 返回 v1 投影，但前端类型没接）。
3. 更关键：**2.0 的自建分区路径已经是"确定性补入、不走 AI"**，这正是卡 R4 步骤 3
   强调的那条正确做法（1.x 曾因「按钮走 AI 修订导致预览无变化」修过一次）。内置分区的
   AI 修订兜底是 2.0 上游的既定交互，不是 bug。

写进 `blocked.md` 的 DEFERRED-3，并在 R7 的 D 类对抗里**实测自建分区那条路**
（能补 A、不误加 B、补完预览更新），而不是假装覆盖了内置分区。

### 逆向风险的补强（本轮做了，代价小）

覆盖清单补入走 `document_save.save_content`，而 R3 在 `save_content` 里加了技术栈隐藏。
这条组合正是 1.x 注释里点名的复发路径："生成时藏好了 → 补一段 → 又露出来"。R3 的
挂点已经覆盖它（补进来的 `tech_stack` 是 `placement=trail`，落库前被置 hidden），
R7 的 D 类对抗会实测这一点。

## R5 画像导入（目标：claims + 资料字段，**不是** profile_facts）

### 关键事实（R1 已核实，这里再钉一次）

计划书 §1.4 / §9.1 / §R5 的前提是「1.x 画像导入写 `profile_facts`，2.0 已删该表所以要改目标」。
**实测 1.x 的画像导入写的就是 `ClaimRecord` + `ProfileEntry`**，从来不是 `profile_facts`：

```
$ grep -n "profile_facts/ClaimRecord" backend/app/services/profile/portrait_import.py
33:    ClaimRecord,
472:        for row in db.query(ClaimRecord)...
527:        db.add(ClaimRecord(**claim))
```

所以本卡的「目标改写」实际落成：**照 1.x 原本的 claims + 资料条目移植，并且
一个字符都不碰 `profile_facts` / `fact_store`**（这才是 E14 的本意）。
phase_9 第 9 项 `画像导入无 profile_facts 引用 == 0` 实测通过。

### 改动

| 文件 | 动作 |
|---|---|
| `backend/app/services/profile/portrait_import.py` | **新增**（从 1.x 逐字复制，549 行，**零改动**） |
| `backend/app/prompts/portrait_extract.md` | **新增**（从 1.x 逐字复制，85 行，**零改动**） |
| `scripts/import_portrait.py` | **新增**（从 1.x 复制 + 加显式 `--dry-run` 别名） |
| `backend/tests/test_portrait_import.py` | **新增**（从 1.x 逐字复制，9 用例，**零改动即绿**） |

### 为什么只加了一个参数

1.x 的 dry-run 是「不加 `--apply` 的隐含默认」。计划卡 R5 步骤 6 写的是
`python scripts/import_portrait.py --dry-run`。加一个显式别名（行为完全不变，
与 `--apply` 同时给出时以 `--apply` 为准并打印一句提示），让"我这次只看看"在命令行里
可读、可 grep。**没有新增任何写库路径。**

### 依赖核对（R1 预判的 import 路径问题不存在）

R1 担心 `app.services.llm_settings` 在 2.0 改名。实测 2.0 **同路径同签名**：
```
backend/app/services/llm_settings.py:169:def get_llm_config(db: Session) -> LLMConfig
backend/app/services/llm/__init__.py:10:def create_provider(config: LLMConfig, ...)
backend/app/database.py:106:SessionLocal = ...
```
字段 ID 也对齐（`catalog_experience.py:45-60` 的 `projects.name/role/start_date/
end_date/tech_stack/description/highlights/public_url/outcome_type` 与 1.x 写入的键
完全一致，`outcome_type` 五个枚举值也相同）。所以**服务层零改动**。

### L1 / L2 / L3

```
$ python -c "ast.parse(scripts/import_portrait.py)"            → AST OK
$ python -c "import app.services.profile.portrait_import"      → service import OK
$ python -c "exec scripts/import_portrait.py"                  → script import OK

$ pytest tests/test_portrait_import.py -q                      → 9 passed
```

L3：
```
PASS scripts/import_portrait.py 存在 — scripts/import_portrait.py
PASS 画像导入无 profile_facts 引用 — 命中 0 处 []
PASS portrait_extract.md 存在 — backend\app\prompts\portrait_extract.md
PASS N8 定向测试绿 — returncode=0；21 passed, 1 warning
PASS 前 8 阶段复跑无 FAIL — 复跑 FAIL=0

汇总：PASS=12 FAIL=0 SKIP=0     ← phase_9 首次全项满分
```

### dry-run 对账输出（★ 只跑 dry-run，未执行 --apply）

```
复用已有抽取结果：...\简历通\runtime\portrait-bundle.json（加 --extract 可重新抽取）
抽取摘要：{"projects": 10, "experiences": 1, "skills": 54}

预览（尚未写库）：
  识别到教育经历（不写入资料库，避免和已有教育经历重复）：
    - 哈尔滨信息工程学院
  新增资料库条目（65）：
    + AI 简历工作台
    + CreatorDistill 创作者内容分析系统
    + 基于 ESP32-S3 的居家康养异常行为检测系统
    + ESP-SparkBot AI 桌面机器人复刻
    + STM32F070 + SHT31 + RS485 温湿度传感节点
    + PixelBeads 拼豆网站复刻
    + 家庭网络与自托管
    + CreatorDistill 爆款拆解语料库
    + 微信公众号民生消费类
    + AIGC 短视频生产体系
    + 成都纳界盛科技有限公司 · 工程师…
    + （技能 54 条：C / TypeScript / JavaScript / Python / SQL / Shell / C++ /
       LLM 结构化输出 / OpenAI 兼容协议 / 提示词工程 / JD 抽取 / 匹配度分析 /
       Codex·ZCode / WorkBuddy / Next.js / Vue3 / Fastify / Drizzle / SQLite /
       Playwright / Vitest / Docker / Git / LVGL / ESP-IDF / MCU / 驱动协议 /
       立创EDA / Modbus / ROS2 / BLE / 逻辑分析仪 …）
  更新已有条目（0）：
  新增事实台账（11）：
    + AI 简历工作台 · 项目事实｜已确认｜承担：项目负责人
    + CreatorDistill 创作者内容分析系统 · 项目事实｜已确认｜承担：负责模块
    + 基于 ESP32-S3 的居家康养异常行为检测系统 · 项目事实｜已确认｜承担：项目负责人
    + ESP-SparkBot AI 桌面机器人复刻 · 项目事实｜已确认｜承担：负责模块
    + STM32F070 + SHT31 + RS485 温湿度传感节点 · 项目事实｜已确认｜承担：负责模块
    + PixelBeads 拼豆网站复刻 · 项目事实｜已确认｜承担：参与
    + 家庭网络与自托管 · 项目事实｜已确认｜承担：负责模块
    + CreatorDistill 爆款拆解语料库 · 项目事实｜待确认｜承担：负责模块
    + 微信公众号民生消费类 · 项目事实｜已确认｜承担：主导方案或交付
    + AIGC 短视频生产体系 · 项目事实｜待确认｜承担：主导方案或交付
    + 成都纳界盛科技有限公司 · 经历事实｜待确认｜承担：参与

未写入数据库。确认以上明细后加 --apply 执行；写入前会自动备份数据库。
```

对账四项都成立：
1. **源行数**：10 项目 / 1 经历 / 54 技能（与 bundle 逐项相符）；
2. **预计写入**：65 条资料条目 + 11 条事实；
3. **跳过原因**：教育 1 条（`哈尔滨信息工程学院`，不写资料库避免与已有教育重复）；
4. **不覆盖**：「更新已有条目（0）」——2.0 库的 `profile_entry` 是空的（新库），
   所以没有可覆盖对象；一旦有，`plan_portrait` 的"只补空字段"逻辑由
   `test_portrait_import.py` 的 9 个用例守住（含现有用例里对只补空的断言）。

### 未写入证明（dry-run 前后库指纹一致）

```
$ ls -la backend/data/resume_forge.db
-rw-r--r-- 1 Administrator 197121 1085440 Nov  6 13:38 backend/data/resume_forge.db
（dry-run 之后 mtime 仍是 13:38，即请求前的值）

$ sqlite3 profile_entry count → 0     （导入前就是 0，未新增）
$ sqlite3 claim_record          → 表存在，未新增行
```

**`--apply` 未执行**（计划 §9.4 DEFERRED-1：真数据迁移留人工）。

## R6 测试移植

### 清点（1.x `ls backend/tests/ | grep -E "dedupe|coverage|portrait|tech_stack|preference"`）

| 1.x 测试 | 2.0 对应 | 处置 |
|---|---|---|
| `test_resume_dedupe.py` | ✅ `tests/test_resume_dedupe.py`（R2 建，6 用例） | **未原样移植**：1.x 那 2 个用例断言的是 `dedupe_and_limit_resume`（含按页截断），2.0 已按 E15 砍掉截断，原样搬会测一个不存在的函数。R2 按同一语义重写为 6 个去重-only 用例（含"相似不同都保留""无身份不丢""不截断数量"三条 1.x 没覆盖的）。 |
| `test_generation_preferences.py` | ✅ `tests/test_generation_preferences.py`（R3 建 3 + R6 补 1 = 4 用例） | 1.x 的 4 个用例里，**2 个**（`tolerates_missing_projects` / `handles_v2_document_items`）补进 `test_tech_stack_preference.py`；**1 个**（API 往返）补进本文件——1.x 路径是 `/api/profile/generation-preferences` + 字段 `include_tech_stack`，2.0 是 `/api/settings/generation-preferences` + `show_tech_stack`，语义一致、位置按 2.0 现状。 |
| `test_portrait_import.py` | ✅ `tests/test_portrait_import.py`（R5 移植，9 用例） | **逐字复制，零改动即绿**。 |
| `test_resume_coverage.py` | ✅ 已在 2.0（14 用例） | 不重复搬。 |
| `test_assistant_coverage.py` / `test_backup_coverage.py` / `test_profile_field_preferences.py` | ✅ 已在 2.0 | 与 N8 无关，不搬。 |
| `test_tech_stack_preference.py`（1.x **不存在**同名文件） | ✅ `tests/test_tech_stack_preference.py`（R3 建 6 + R6 补 2 = 8） | 1.x 的技术栈用例放在 `test_generation_preferences.py` 里；2.0 单开一个文件（去重/技术栈各自一份，FAIL 定位更快）。 |

### 卡 R6 要求的命令

```
$ cd backend && pytest tests -q -k "resume_dedupe or coverage or portrait or tech_stack"
97 passed, 7073 deselected, 1 warning in 12.78s
```

（`-k` 额外带上 `generation_preferences`，因为技术栈开关的设置项测试在该文件里；
97 项 = 去重 6 + 覆盖 14+14+31 前端不在此 + 画像 9 + 技术栈 8 + 偏好 4 + 既有 coverage 系列。）

### 各文件单跑

```
$ pytest tests/test_resume_dedupe.py -q            → 6 passed
$ pytest tests/test_tech_stack_preference.py -q    → 8 passed
$ pytest tests/test_generation_preferences.py -q   → 4 passed
$ pytest tests/test_portrait_import.py -q          → 9 passed
$ pytest tests/test_resume_coverage.py -q          → 14 passed
$ pytest tests/test_append_profile_entries.py -q   → 14 passed
$ npx vitest run src/components/settings/GenerationPreferencesCard.test.tsx → 2 passed
$ npx vitest run src/components/resume/CoverageActions.test.tsx coverageGroups.test.ts → 31 passed
```

**没有修改任何测试断言使它们通过**：1.x 搬来的 9 个用例逐字未改；
新增/补写的用例都是按实测行为写期望（两次红都是我先写错了预期，见 R3 记录）。

## R7 对抗审查（A/B 全 PASS）

产出 `docs/fork-2.0-resume-adversarial.md`。四类结果：

| 类 | 结果 |
|---|---|
| **A 去重误删** | 3/3 PASS（重复→1 条 / 相似→都留 / 无身份→不删） |
| **B 技术栈泄漏** | **4/4 PASS**，其中 **B③ 首轮 FAIL → 已修 → PASS** |
| C 画像导入污染 | 3/3 PASS（对账准确 / 不重复 / 不覆盖，全程只 dry-run） |
| D 覆盖清单补全 | 2/2 PASS（补 A 不误加 B / 补入后技术栈不复发） |

### B③ 打出真实缺口并修掉（本轮最重要的一次发现）

攻击：开关关闭时，用 `POST /api/resumes/manual` 新建一份带 `tech_stack` 的手写简历。

**首轮 FAIL**：`manual_creation._validated_content` 直接走
`prepare_document_for_save_with_report`，**不经过** `document_save.save_content`，
所以技术栈仍以 `placement=trail` 上纸面（`可见技术栈项: 1`）。1.x 同样有此洞
（`grep include_tech_stack backend/app/services/resume/manual_creation.py` = 0 命中）。

**修复**：`manual_creation.py::_validated_content` 转换后读偏好，关闭则
`strip_resume_tech_stack(content)`。方向与其它路径一致（只隐藏、不删数据）。

**回归测试**：`tests/test_tech_stack_preference.py::test_manual_creation_strips_tech_stack_when_off`
（走真实 HTTP，断言可见 0 + 数据仍在 `placement=hidden`）。

修复后 B 类三条路径全部 0：

```
偏好: {'show_tech_stack': False}
① AI 生成 (save_record): 0
② 手工保存 PUT status: 200 → 可见技术栈: 0
③ 手写创建 status: 201 → 可见技术栈: 0
对照组（开关打开）: 1（说明不是无条件删）
```

### 计划书偏差（以代码为准，E5）

- 卡 R7 要求的「底稿模式」在 2.0 **不存在**（`base_resume_id` 在 2.0 schema 0 命中，
  是 1.x 独有）。第三条路径改用 2.0 现状的「手写/底稿创建」（`source=manual`+`draft`），
  并把 1.x 的"v2 文本项里的技术栈行"用例一并纳入。

### L3 与一处环境红

```
PASS resume_dedupe.py 可导入
PASS 去重已接进生成链路 — 调用点=['services/resume/resume_record.py']
PASS 去重与截断分离 — 命中违禁词=无
PASS 技术栈开关设置项 show_tech_stack 存在
PASS 技术栈开关默认关 — show_tech_stack: bool = False
PASS 技术栈两条路径都生效 — 生成路径=[resume_record.py] 手工保存=[document_save.py]
PASS 覆盖清单补入能力存在或已记 GONE
PASS scripts/import_portrait.py 存在
PASS 画像导入无 profile_facts 引用 — 命中 0 处 []
PASS portrait_extract.md 存在
PASS N8 定向测试绿 — 24 passed
FAIL 前 8 阶段复跑无 FAIL — 复跑 FAIL=1 [('FAIL','1.x 库未被修改','当前 166531072 / 记录 160989184')]

汇总：PASS=11 FAIL=1 SKIP=0
```

**这条 FAIL 来自 `phase_1`，不是 N8 的检查**，根因是用户自己开着的 1.x 应用在 14:27
跑完一次 11/11 全成功的自动投递并把 WAL checkpoint 进主库（+5.29MB）。详见
`fork-2.0-resume-blocked.md` → `BLOCKED-ENV-1`。红线禁止改 phase_0..phase_8，
所以本轮不修、只取证。

### 探测数据的清理（自审）

R7 的对抗探测直接调用了真实 HTTP 端点，往 **2.0 开发库**写了 13 条测试简历 +
1 条资料条目 + 1 个偏好 key。这些是我自己造的，已全部清掉：

```
软删 13 条 → POST /api/trash/purge（purged: 13, ok: True ×13）
剩余 resume_record: 0
探测 profile_entry 15ea38592db94ce79f689fdc 已删除；剩余 profile_entry: 0
claim_record: 0
app_setting: apply_config / ui.locale / profile_generation_preferences（值 false = 默认）
```

（2.0 开发库在开工前本来就没有简历与资料条目，所以清空等于回到原状。
偏好 key 保留默认值 `{"show_tech_stack": false}`——它同时是 R3 的默认态证据。）
