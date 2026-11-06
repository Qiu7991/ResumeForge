# N8 简历侧移植 · 晨间报告

> 日期：2026-11-06 夜 → 11-07 晨
> 分支：`feat/resume-side`（从 `feat/fork-port` 88ae5ac 切出，共 14 个提交）
> 计划书：`简历通-2.0-N8简历侧移植计划.md`

---

## 一、一句话结论

**N8 完成度：全部（8/8 卡完成，按计划 §7 属「超额」档）。**
去重、技术栈开关、覆盖清单、画像导入四块全部落地且有测试；仅在**闸门 phase_1 的环境断言**
上留一条红——原因是老板自己开着的 1.x 应用在夜间跑了一轮自动投递，把 1.x 库 checkpoint 大了
5.29 MB，与本次改动无关（详见第三节）。

**N8 的 11 条实质检查全部 PASS**（phase_9 内 11 PASS / 1 FAIL，FAIL 是复跑 phase_1 带出来的）。

---

## 二、完成清单（任务号 + commit + 闸门原始输出）

| 卡 | 做了什么 | commit |
|---|---|---|
| **R0** | 建分支 + 三件套 + 闸门 phase_9（只新增） | `26a878c` / `12a2c44` |
| **R1** | 落点复核 → `docs/fork-2.0-resume-baseline.md` | `0b80f73` |
| **R2** | 生成结果去重（6 用例） | `c9e87fa` / `e585a9a` |
| **R3** | 显示技术栈开关（默认关，3 条写路径 + 设置卡，9+4+2 用例） | `9076765` / `e17aa70` |
| **R4** | 覆盖清单复核（判定 EXISTS，差异登记 DEFERRED-3） | `086381f` / `6b8ce20` |
| **R5** | 画像导入（3 文件 + 9 用例，dry-run 已跑） | `c7a9f1f` / `ef47c77` |
| **R6** | 测试补齐（1.x 9 用例零改动 + 补 3 条） | `5dfd0b3` |
| **R7** | 对抗审查（A 3/3 · B 4/4 · C 3/3 · D 2/2） | `b68cc88` / `ca57698` |
| **R8** | 全量闸门 + 三方指纹 + 本报告 | 本提交 |

### 2.1 闸门 phase_9 原始输出（N8 的 12 项检查）

```
===== Phase 9 =====
PASS resume_dedupe.py 可导入 — returncode=0
PASS 去重已接进生成链路 — 调用点=['services/resume/resume_record.py']
PASS 去重与截断分离 — resume_dedupe.py 命中违禁词=无
PASS 技术栈开关设置项 show_tech_stack 存在 — backend\app\schemas\generation_preferences.py
PASS 技术栈开关默认关 — show_tech_stack: bool = False
PASS 技术栈两条路径都生效 — 生成路径=['services/resume/resume_record.py'] 手工保存=['services/resume/document_save.py']
PASS 覆盖清单补入能力存在或已记 GONE — resume_profile_append.py=True resume_coverage.py=True GONE登记=False
PASS scripts/import_portrait.py 存在 — scripts/import_portrait.py
PASS 画像导入无 profile_facts 引用 — 命中 0 处 []
PASS portrait_extract.md 存在 — backend\app\prompts\portrait_extract.md
PASS N8 定向测试绿 — returncode=0；24 passed, 1 warning
FAIL 前 8 阶段复跑无 FAIL — 复跑 FAIL=1 [('FAIL', '1.x 库未被修改', '当前 166531072 字节 / 记录 160989184 字节')]

汇总：PASS=11 FAIL=1 SKIP=0
```

第 12 项唯一 FAIL 来自 **phase_1 的环境断言**（见第三节 `BLOCKED-ENV-1`）。

### 2.2 全量闸门 `--all` 原始输出（摘要）

```
PASS 2.0 基线单提交且未被改写 — upstream-v2.0.0 提交数=1，是 HEAD 祖先=True
PASS 版本是 2.0.0 — frontend/package.json version=2.0.0
PASS 迁移文件数 < 10 — 数量=2
PASS 8010 健康检查 — 响应={'status': 'ok', 'name': 'ResumeForge', 'version': '2.0.0'}
PASS baseline 文档存在
FAIL 1.x 库未被修改 — 当前 166531072 字节 / 记录 160989184 字节      ← 环境因素，见第三节
PASS 2.0 库无 profile_facts 表 — 命中 0 条
SKIP 导入对账无未解释跳过 — B-1 属会话 B
PASS apply_queue_item.greeting_confirmed 列存在
PASS apply_task_item.greeting_confirmed 列存在
PASS apply_task_item 失败三列存在 — 缺失=无
PASS backend/app 无 'page_limit or 1' 字面量 — 命中 0 处
PASS pytest -k apply 全绿 — 444 passed, 6727 deselected
PASS BOSS 修复：点击前等 document.readyState == complete
PASS BOSS 修复：trusted_click 前焦点仿真（Ego 多窗口 hidden 修复）
PASS BOSS 修复：job_closed 软跳过分类
SKIP pytest -k 'boss or apply_boss' 全绿 — 上游基线已含在 -k apply 内
PASS ai_job_link 表存在
PASS 迁移链单头 — heads=0002_fork_apply_greeting_plan_aijob
SKIP 前端 /ai-jobs 路由 — N7 未移植（本轮范围外）
SKIP aiJobs 中英 key 数相等 — N7 未移植（本轮范围外）
PASS resume_generation_plan 表存在
PASS resume_dedupe.py 存在
PASS backend/app profile_facts 引用 == 0 — 命中 0 处
SKIP npm run typecheck 绿 — N7 未移植（本轮范围外）
PASS dist 比 src 新
SKIP i18n 中英差集为空 — N7 未移植（本轮范围外）
FAIL 前 7 阶段复跑无 FAIL — 复跑 FAIL=2（都由上面那条 1.x 库断言传染）
PASS 两份报告存在
（以下为 phase 9 的 12 项，同 2.1）

汇总：PASS=32 FAIL=3 SKIP=6
```

**三条 FAIL 是同一个环境事实的三种体现**（phase_1 直接报 + phase_7/phase_9 复跑传染），
没有任何一条指向 N8 的代码。

### 2.3 定向测试

```
$ cd backend && pytest tests -q -k "resume_dedupe or coverage or portrait or tech_stack or ai_jobs or apply"
536 passed, 6635 deselected, 1 warning in 74.05s
```

### 2.4 前端

```
$ npx tsc --noEmit -p tsconfig.json     → 无输出（通过）
$ npm run build                          → ✓ built in 1.23s
$ npx vitest run src/components/settings src/pages/SettingsPage
  32 files / 205 tests passed
$ npx vitest run src/i18n                → 334 passed, 1 skipped
$ npx vitest run src/components/resume/CoverageActions.test.tsx coverageGroups.test.ts
  31 passed
```

### 2.5 三块功能的验收要点

| 功能 | 落地位置 | 怎么验 |
|---|---|---|
| **生成结果去重** | `services/resume/resume_dedupe.py` + 挂在 `resume_record.save_record` | `pytest tests/test_resume_dedupe.py`（6 用例）；E13 对照 6→5 / 2→1 |
| **显示技术栈开关（默认关）** | 设置页「外观与交互」→「生成偏好 · 简历内容」 | 开关默认关；关掉后生成/手工保存/修订/手写创建四条路径都无技术栈；数据仍在（`placement=hidden`） |
| **覆盖清单「从资料补上这段」** | 2.0 本来就完整（自建分区确定性补入） | 45 项测试全绿；内置分区差异登记 DEFERRED-3 |
| **画像导入** | `scripts/import_portrait.py` + `portrait_import.py` + `portrait_extract.md` | dry-run 对账（10 项目 / 1 经历 / 54 技能 → 65 条目 + 11 事实）；**未 --apply** |

---

## 三、BLOCKED 清单

### BLOCKED-ENV-1：phase_1「1.x 库未被修改」红 —— **不是本轮改动造成的**

| 项 | 证据 |
|---|---|
| 现象 | `FAIL 1.x 库未被修改 — 当前 166531072 字节 / 记录 160989184 字节`（+5,541,888 ≈ 5.29 MB） |
| 时间线 | R0（12:2x）时该断言是 **PASS**（phase_9 报「复跑 FAIL=0」）→ 14:27 变化 |
| 谁写的 | **老板自己开着的 1.x 应用**：PID 24444 / 端口 8005 / 启动于 11-05 16:28；今日 01:05 起 11,325 次请求；`apply_config.interval_seconds=25` 自动投递 |
| 那一刻发生了什么 | 14:27 完成 `apply_task`：total=11 / processed=11 / **succeeded=11 / failed=0**；随后 SQLite 把 4,663,872 字节 WAL checkpoint 进主库 |
| 不是我改的 | 1.x `git status --porcelain` = 0 行、`HEAD` 仍 `a09b63e4`；副本 `PRAGMA integrity_check = ok`；数据完好（52 简历 / 126 资料 / 29 事实 / 219 岗位） |
| 静置验证 | 不碰它 60 秒，尺寸与 mtime 均不变（`变化: 0 字节`）→ 是那一次任务的，不是持续增长 |
| 为什么不修 | 红线 §2.2#6 禁止改 `fork_gate.py` 的 phase_0..phase_8；`STATIC_1X_DB_SIZE` 就在 phase_1 里 |

**要让闸门回绿，二选一（都需要老板决定）**：
① 关掉 1.x 应用后从备份恢复基线（涉及用户数据）；
② 授权后更新 `STATIC_1X_DB_SIZE` 常量（改闸门）。

### BLOCKED-Q1：1.x 的 `QueueItemEditor.test.tsx` 未落地

计划 §1.4 让拷这个测试。实测 3 项全红，根因是它断言的两个功能（「查看岗位 JD」展开拉
`/jobs/{id}`、项目下拉 + `focus_project`）**2.0 的 104 行 编辑器里根本没有**，属于投递台
（N3/N4 已验收、§13 明确「不碰」）。已撤回文件，登记后继续。**不影响 N8 任何一张卡。**

### DEFERRED-1：画像导入 `--apply`（真数据迁移留人工）

### DEFERRED-2：去重的相似度阈值（沿用 1.x 确定性规则）

### DEFERRED-3：覆盖清单——内置分区（项目/经历）缺条目时只能走 AI 修订

2.0 的 `resolveCoverageAction` 只对 `custom:` 分区返回 `append`。补齐需搬 1.x 的
`projectionContent.ts`（615 行）+ 改动作判定 + 对齐 `PaperProjectionOut` 前端类型，
超出「只补差异」边界，单开一张卡更合适。

---

## 四、三方完好证明

```
$ cd /d/飞牛文件同步/工作/简历通
a09b63e43cac1edd957f84daf7794b18cdf0023e
branch: fix/v2-single-model
dirty: 0

$ cd /d/飞牛文件同步/工作/简历通-2.0-fe
3b122036a8fa68d4035cccd9b934d3fecf81a2a1
branch: feat/ai-jobs-frontend
dirty: 0

$ cd /d/飞牛文件同步/工作/简历通-2.0
ca576986002c64b96c03e437bb4601d21f025afc
branch: feat/resume-side
dirty: 0

$ cd /d/飞牛文件同步/工作/BossHunter
77f3572fa98aa1a2e0c73a79f0dace1c0619da70
branch: main
dirty: 2      ← 只有 start.cmd / stop.cmd 两个**未跟踪**文件，时间戳 11-02 17:44/17:54
                （老板 11-02 自建的启停脚本，与本轮无关，本轮从未进入本目录做写操作）
```

1.x HEAD 与开工前一致、dirty=0；2.0-fe 未进入；2.0 在本分支上干净。

### 本轮未触碰线2（BossHunter）任何文件 —— 验证命令与输出

```
$ cd /d/飞牛文件同步/工作/简历通-2.0
$ git diff --name-only feat/fork-port..HEAD | grep -i "ai_jobs"
（无输出 —— 0 命中）

$ git diff feat/fork-port..HEAD -- backend/app/application_routers.py
（无输出 —— 未给 routers 加 ai_jobs 路由）

$ git diff --name-only feat/fork-port..HEAD | grep "task_runner"
（无输出 —— 未给 task_runner.py 加 AI 互斥块）

$ git diff --name-only feat/fork-port..HEAD
（29 个文件，全部属于：简历生成链路 / 设置 / 画像导入 / 前端设置卡 / N8 文档 / fork_gate phase_9）
```

本轮**没有合并** `feat/ai-jobs-sidecar` 与 `feat/ai-jobs-frontend`：开工时分支停在
`feat/ai-jobs-sidecar`，按本轮隔离要求**只执行了 `git switch feat/fork-port`**（未 merge），
再从它切出 `feat/resume-side`。

### 闸门 phase_9 是纯新增（E10）

```
$ for p in phase_0..phase_7; do 比对函数体 md5; done
phase_0 逐字一致
phase_1 逐字一致
phase_2 逐字一致
phase_3 逐字一致
phase_4 逐字一致
phase_5 逐字一致
phase_6 逐字一致
phase_7 逐字一致
```

`git diff` 里唯一被删的一行是 `PHASES = {0: …, 7: phase_7}` 这一行（为了注册 9），
phase_0..phase_8 的函数体一字未动。

---

## 五、醒来先做这 3 件事

### 1. 决定 phase_1 那条红怎么处理（5 分钟）

它是**唯一**的 FAIL，且是本轮之外的原因（1.x 应用夜间自动投递把库 checkpoint 大了 5.29MB）。
- 想让它自然回绿：确认 1.x 应用是否该继续整夜自动投递 → 关掉后从 `backend/data/backups/`
  恢复一份基线库（会回退投递记录，需你确认）；
- 或者授权我把 `STATIC_1X_DB_SIZE` 更新为当前值（这是改闸门，本轮禁止，需你点头）。

### 2. 重启 2.0 后端，然后人工冒烟（15 分钟）

新路由 `GET/PUT /api/settings/generation-preferences` 只在**下次启动**后才存在
（运行中的 8010 是改动前启动的进程，我没去动它）。

```bash
cd /d/飞牛文件同步/工作/简历通-2.0
powershell -Command "Start-Process -FilePath 'stop.cmd'"
powershell -Command "Start-Process -FilePath 'start.cmd'"
# 然后
curl http://127.0.0.1:8010/api/settings/generation-preferences
# 期望：{"show_tech_stack": false}
```

冒烟三件事：
- 设置 → 外观与交互 → 看到「生成偏好 · 简历内容」卡，开关默认**关**；
- 生成一份新简历 → 项目里**不出现**「技术栈：…」行；
- 覆盖清单里点一次「补进简历」（自建分区）→ 补完预览立刻更新、技术栈不冒出来。

### 3. 决定两件 DEFERRED 要不要现在做（各 1–2 小时）

- **DEFERRED-3**（内置分区也能「从资料补上这段」）：需搬 615 行前端 + 对齐投影类型；
- **画像导入 `--apply`**：dry-run 对账已经跑通（10 项目 / 1 经历 / 54 技能 → 65 条目 + 11 事实，
  教育 1 条自动跳过），确认后我可以执行（会先自动备份库）。

---

## 附：本轮新发现的两个与计划书不符的地方（以代码为准）

| # | 计划书写的 | 实测 |
|---|---|---|
| 1 | 画像导入 1.x 写 `profile_facts`，2.0 已删表，**必须改目标** | 1.x **本来就写 `ClaimRecord` + 资料条目**，从来不是 `profile_facts`（`grep` 证据见 baseline §④）。所以「改目标」实际是「确认目标已是 claims 且不引入 `fact_store`」——phase_9 的 `profile_facts 引用 == 0` 照样成立 |
| 2 | 覆盖清单需核对/移植（§1.4 标「需核对」） | 2.0 **已完整具备**（后端 `resume_profile_append.py` + 专用 API + 前端 `CoverageGroupCard` + 45 项测试）。R4 改为只补差异 |
| 3 | R7 的第三条路径是「底稿模式」 | 2.0 **没有底稿模式**（`base_resume_id` 0 命中，1.x 独有）。改用 2.0 现状的「手写/底稿创建」路径 |
