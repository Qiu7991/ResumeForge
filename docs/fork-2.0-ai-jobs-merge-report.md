# AI 求职 · 线2 前端合并报告

> 2026-11-06 午间。分支 `feat/ai-jobs-sidecar`（线2，永久不合并回主线）。
> 本报告由线2 会话执行「合并前端分支 + 整页验通」后产出。
> 后端成果见 `docs/fork-2.0-ai-jobs-morning-report.md`（会话 A，A0–A8 全绿）。

## 一、结论

**线2 整页可用（在「引擎未配置」这一前置条件下的完整可用）。**

| 维度 | 结论 | 证据 |
|---|---|---|
| 后端闸门 | ✅ 全绿 | `fork_gate.py --all` = **PASS 37 / FAIL 0 / SKIP 6**（EXIT=0，构建后终态） |
| 后端测试 | ✅ 全绿 | `-k "ai_jobs or apply"` = **567 passed / 1 skipped** |
| 前端类型 | ✅ 通过 | `npm run typecheck` EXIT=0 |
| 前端 lint | ✅ 通过 | EXIT=0（**35 warnings / 0 errors**，其中 9 条落在 ai-jobs 文件，见 §四 B-2） |
| 前端单测 | ✅ 全绿 | `vitest run src/components/ai-jobs` = **5 files / 18 tests passed** |
| 前端构建 | ✅ 成功 | `npm run build` EXIT=0；`AiJobsPage-9V_voe6s.js`(40.4 kB) 已进产物 |
| 同源页面 | ✅ 可用 | `GET /ai-jobs`（`Accept: text/html`）= **200 text/html**，SPA 回退命中 |
| 状态接口 | ✅ 明确非 500 | `GET /api/ai-jobs/status` = **200**，返回「尚未配置引擎位置」+「sidecar 未启动」 |
| 发送闸门 | ✅ 默认关 | `POST /api/ai-jobs/deliver` = **403**（未设 `AI_JOBS_ALLOW_SEND`） |

**一句话**：合并零冲突，两线文件集不相交；后端 567 测试与合并前逐字一致（合并只加前端）；
页面、路由、产物、状态接口、发送闸门全部实测通过。**唯一没做的是真实联调**（需真引擎 + 真账号 + 人在场），
见 §五。

**⚠️ 一处必须纠正闸门自身结论（不改代码，只记事实）**：`--all` 里 `aiJobs 中英 i18n key 数相等`
报 **`zh=0 en=0` 却判 PASS**——这是**假信号**（正则要求 4 空格缩进，B 的文件用 2 空格，
两边都数出 0，`0==0` 恒真）。独立口径复测：**zh=148 / en=148，key 集合完全相同**（详见 §四 B-1）。
闸门的**结论**对，**证据**是空的；因红线 9 禁止改 `fork_gate.py`，此处只登记不改。

## 二、合并结果

### 2.1 现场确认（合并前，原样）

```
$ git branch --show-current
feat/ai-jobs-sidecar
$ git status --porcelain
（空）
$ git log --oneline -3
e5fb384 docs(ai-jobs): 夜间执行报告（A0-A8 全绿收工）
d20e977 test(ai-jobs): 修 A8 联合选择器下的测试间租约泄漏（NOTE-3），567P/1S 全绿
dc996c5 docs(ai-jobs): 任务板 A7 完成
```

### 2.2 分支文件集不相交（合并前实测）

| 检查 | 结果 |
|---|---|
| `fe/feat/ai-jobs-frontend` 相对基线 `88ae5ac` 改的 backend 文件数 | **0** |
| `feat/ai-jobs-sidecar` 相对基线改的 frontend 文件数 | **0** |
| 前端分支提交数（`88ae5ac..3b12203`） | 18 |
| 后端分支提交数（`88ae5ac..e5fb384`） | 11（A0–A8 共 10 + 1 测试修复） |

### 2.3 合并动作与结果

```
$ git remote add fe /d/飞牛文件同步/工作/简历通-2.0-fe
$ git fetch fe
 * [new branch]      feat/ai-jobs-frontend -> fe/feat/ai-jobs-frontend
$ git merge --no-ff fe/feat/ai-jobs-frontend
44 files changed, 3305 insertions(+), 4 deletions(-)
```

- **冲突：0 个**（与 §15.2 的「注册表改动全部归 B 独占」设计一致）。
- 合并提交：`000600f chore(ai-jobs): 合并前端分支 feat/ai-jobs-frontend 到线2`
- 双亲验证：`000600f → (e5fb384, 3b12203)`，确实 `--no-ff`，未产生快进。
- 合并后 `feat/ai-jobs-sidecar` 领先基线 **30 个提交**（11 + 18 + 1 合并提交）。

### 2.4 闸门输出（分两次跑，取终态）

**合并后、构建前**（`34P/0F/9S` → 本次）：
```
汇总：PASS=35 FAIL=0 SKIP=8
EXIT=0
```

**构建后（终态，报告采用此数字）**：
```
PASS dist 比 src 新 — dist mtime=1793938716.4830103 src mtime=1793938019.4370866
汇总：PASS=37 FAIL=0 SKIP=6
EXIT=0
```

相对合并前基线 `34P/0F/9S`：**PASS +3、SKIP −3、FAIL 恒 0**。
转 PASS 的三项正是会话 B 的产出：前端 `/ai-jobs` 路由、`dist 比 src 新`、
phase_8 版 i18n key 数（该项为假 PASS，见 §四 B-1）。
剩余 6 个 SKIP 均属**其他线/N7/N8 范围**或**需人工/环境**项，不是线2 缺陷：

| SKIP 项 | 原因 |
|---|---|
| 导入对账无未解释跳过 | B-1 数据桥属会话 B，本轮未执行 |
| `pytest -k "boss or apply_boss"` | N5 未移植（线1 范围） |
| `aiJobs 中英 key 数相等`（phase_4 版） | N7 未移植（phase_8 版已 PASS，见 §四 B-1） |
| `resume_dedupe.py` / `npm run typecheck` / `i18n 中英差集` | N7/N8 未移植（线1 范围） |

### 2.5 定向测试

```
$ cd backend && .venv/Scripts/python.exe -m pytest tests -q -k "ai_jobs or apply"
567 passed, 1 skipped, 6701 deselected, 1 warning in 115.30s
```

与合并前**逐字一致**（合并未动一个 backend 文件，符合预期）。

## 三、与线1 的隔离证明

### 3.1 线2 相对 `feat/fork-port`（88ae5ac）修改的 5 个既有文件

> 任务口径要求列「5 个既有文件」= 后端 4 个 + `fork_gate.py`。（另有一批前端既有文件由会话 B 独占修改，见 §3.3。）

| # | 文件 | 改了什么 | 主线是否受影响 |
|---|---|---|---|
| 1 | `backend/app/application_routers.py` | 加 `ai_jobs` 导入 + 注册（2 处） | ❌ 未受影响 |
| 2 | `backend/app/models/tracker.py` | 加 `SOURCE_AI_JOBS` 常量 / `record_applied(source=)` | ❌ 未受影响 |
| 3 | `backend/app/services/apply/task_runner.py` | 加 AI 求职互斥块（照 1.x 逐字） | ❌ 未受影响 |
| 4 | `backend/app/services/tracker.py` | `record_applied` 增加 `source` 参数 | ❌ 未受影响 |
| 5 | `scripts/fork_gate.py` | 新增 `phase_8()` 并注册（**phase_0..7 一行未改**） | ❌ 未受影响 |

### 3.2 主线未被染污的硬证据

```
$ git grep -l "ai_jobs" feat/fork-port -- backend/app
（空 —— 主线无任何 ai_jobs 引用）
$ git show feat/fork-port:scripts/fork_gate.py | grep -c "phase_8"
0
$ grep -c "phase_8" scripts/fork_gate.py        # 线2
2
$ git rev-parse feat/fork-port
88ae5ac5a14f0c0697cfe6f76b10c06367bf4911      # 仍在基线，未被本线推进
```

上述 5 个文件在 `feat/fork-port` 与 `feat/ai-jobs-sidecar` 之间**全部 DIFF**，
即**改动只存在于线2 分支**，主线内容不包含它们。

### 3.3 线1 独占的前端既有文件（由会话 B 修改，线2 后端一行未碰）

`frontend/src/api/jobs.ts`、`appRoutes.tsx`、`components/navigation/navigationConfig.ts`、
`i18n/i18nBaseline.json`、`en-US.jobsPage.ts`、`en-US.navigation.ts`、`en-US.ts`、
`zh-CN.jobsPage.ts`、`zh-CN.namespaces.ts`、`zh-CN.navigation.ts`、`pages/JobsPage.tsx`、
`pages/registry.ts` —— 共 12 个，全在 `frontend/**`，与后端零交集。

### 3.4 红线 3 禁改清单命中检查

```
$ git diff --diff-filter=M --name-only 88ae5ac..HEAD | grep -E "services/resume/|job_match|resume_dedupe|import_portrait|coverage"
（无命中 —— 未碰线1 禁区）
```

**结论：线2 对 `services/resume/**`、`job_match*`、`resume_dedupe`、`import_portrait`、覆盖清单相关文件零改动。**

### 3.5 执行方式上的额外隔离（本次采用的强化手段）

**开工时发现主目录 `简历通-2.0` 已被线1 会话占用并正在活跃写入**：

```
$ git branch --show-current      # 几分钟前还是 feat/ai-jobs-sidecar
feat/fork-port                   # 12:03:46 被切走（git reflog 可查）
$ git status --porcelain
?? frontend/src/components/apply/queue/QueueItemEditor.test.tsx   # 12:04:17 写入中
```

若在本目录 `git switch feat/ai-jobs-sidecar` 后合并，会**打断线1 的工作树**，且必然与其
未提交改动冲突。**处置：改用独立 git worktree**，物理隔离：

```bash
git worktree add "D:/飞牛文件同步/工作/简历通-2.0-line2" feat/ai-jobs-sidecar
```

线2 全程只在该 worktree 内操作；`backend/.venv` 与 `frontend/node_modules` 各复制一份
（不共用，避免并发构建抢 Vite 缓存）。数据库用 `sqlite3.Connection.backup()` 从运行库做
一致性快照到 worktree（**只读源库**，不写）。

**该决策已被事实验证必要**：收尾时线1 已切到 `feat/resume-side`，并在主目录留下
`scripts/fork_gate.py` 的 **188 行未提交改动**（新增 Phase 9 / N8 简历侧）。
这些改动从未进入线2 的 worktree，线2 的 `--all` 结果不受污染。

**副作用（须知晓）**：worktree `简历通-2.0-line2` 是本次新增目录，约 **810 MB**
（venv 341M + node_modules 470M）。确认线2 验收后可整体删除：

```bash
cd /d/飞牛文件同步/工作/简历通-2.0
git worktree remove --force ../简历通-2.0-line2   # 或手工删目录后 git worktree prune
```

## 四、BLOCKED 清单

> 均**不阻塞**线2 交付；无 `[BLOCKED]` 状态的任务卡。按「发现问题即登记、不擅自改」处理。

| 编号 | 问题 | 证据 | 影响 | 处置 |
|---|---|---|---|---|
| **B-1** | `fork_gate.py` phase_8 第 12 项 `aiJobs 中英 i18n key 数相等` 是**假 PASS**：检查用正则 `^\s{4}?[\w-]+:` 要求 4 空格缩进，B 的 i18n 文件是 **2 空格**缩进 → 两边都数出 0，`0==0` 恒真 | 闸门输出 `zh=0 en=0`；独立复测 `zh=148 / en=148`，`set(zh)==set(en)` 为 True | 闸门**结论**正确，**证据**是空的；未来若中英真不等，此检查仍会 PASS | 红线 9 禁改闸门 → 只登记。建议线1/维护者后续把正则改为 `^\s+` 并复跑 |
| **B-2** | ai-jobs 前端文件有 9 条 lint warning（`react-hooks/set-state-in-effect` 等），与上游存量 26 条同类 | `npm run lint` = 35 warnings / **0 errors**，EXIT=0；命中文件：`ConfirmationTable.tsx:106`、`GreetingEditor.tsx:31`、`JobDetailDrawer.tsx:34`、`ReplyInbox.tsx:42`、`RunHistoryTable.tsx:50`、`SettingsForm.tsx`、`AiJobsPage.tsx:62/113` | 不影响构建与运行（lint 不 fail） | 红线 2 禁改 B 的成果 → 只登记。属**上游既有 lint 口径**问题，非本轮引入 |
| **B-3** | `GET /api/ai-jobs/{workbench,confirmation,engine-jobs,replies,history,stats}` 在引擎未配置时返回 **422**（非 200 空数据） | 实测：`{"detail":"sidecar 未运行：请先启动引擎"}` / HTTP=422 | 需前端正确兜底；B 的 `useAiJobsPolling` 有 `catch` 并暴露 `error` 字符串，设计上可接受 | **验收确认项**（§五 第 3 条）：页面应显示「引擎未运行」而非报错弹窗/白屏 |
| **B-4** | 主线 8010 上的后端是 **04:39 启动的旧代码**，不加载 ai_jobs 路由 | `runtime/backend.json` process_id=28248 起于 11-05T20:39Z；`netstat` 8010 → PID 18892（PPID 28248） | 若直接在 8010 上验 ai-jobs 会误判「接口不存在」 | 本次用**独立端口 8011** 验证线2 代码（见 §4.5）；8010 属线1 环境，**未杀** |
| **B-5** | 分支状态与任务书描述有偏差：任务书称两条线都从 `feat/fork-port @ 88ae5ac` 切出且「文件集不相交」，实测成立；但**主目录被两条线共用**，主目录当前在 `feat/resume-side` | `git reflog`：12:03:46 从 `feat/ai-jobs-sidecar` 切到 `feat/fork-port`，后又切到 `feat/resume-side` | 高：任何在共用目录切分支的操作都会互相踩 | 本次已用 worktree 规避；**建议长期固定**：线2 只在此 worktree 工作 |

### 4.5 服务自检的端口隔离说明（B-4 的处置细节）

任务书第 4 步要求「`stop-2.0.cmd` 后用 `start-2.0.cmd` 重启」。**未照做**，原因如下：

- 8010 上的服务是**线1 的环境**（PID 18892 / PPID 28248，与主目录 `runtime/backend.json` 对应）。
- 执行 `stop-2.0.cmd` 会杀掉它 → **直接打断线1 正在进行的 N8 工作**，违反「两线永久隔离」。
- 替代方案（等效且更严格）：在**线2 的 worktree 内**用同一套启动脚本、`-FrontendMode production`、
  独立端口 **8011/5175** 起服务，验证的是**合并后的线2 代码**。

实测输出（原样）：

```
$ curl -s http://127.0.0.1:8011/api/health
{"status":"ok","name":"ResumeForge","version":"2.0.0"}

$ curl -s -w "\nHTTP=%{http_code}" http://127.0.0.1:8011/api/ai-jobs/status
{"dataset_id":"main","config":{...,"engine_port":8687,...,"engine_version":""},
 "engine_configured":false,
 "engine_error":"尚未配置引擎位置：请在设置里填写 BossHunter 的安装目录与 Python 路径",
 "sidecar":{"reachable":false,"status":"","version":"","version_ok":false,"reason":"sidecar 未启动"},
 "owned_running":false,"port":0}
HTTP=200
```

**第二条满足任务要求：返回「引擎未安装/未运行」的明确状态，HTTP 200，不是 500。**

补充实测（同实例）：

| 探测 | 结果 |
|---|---|
| `GET /ai-jobs` + `Accept: text/html` | **200** `text/html`，3106 B（SPA 回退命中） |
| `GET /assets/AiJobsPage-9V_voe6s.js` | **200** `text/javascript`，40 421 B（MIME 正确，非 text/plain） |
| `index.html` 引用的入口 | `/assets/index-Bck74naF.js` 等，与本次 build 产物一致 |
| `GET /api/ai-jobs/config` | **200**，返回完整配置对象 |
| `POST /api/ai-jobs/deliver`（闸门关） | **403** `发送闸门未打开：设置环境变量 AI_JOBS_ALLOW_SEND=1 并重启后端后才允许投递（默认关）` |
| 进程环境 `AI_JOBS_ALLOW_SEND` | `[]`（空，**未开启**，红线 6 遵守） |
| 线1 的 8010（对照） | **200** `{"status":"ok",...,"version":"2.0.0"}` —— 未受影响 |

自检完成后已停掉 8011 临时服务（PID 7960，只剩 TIME_WAIT），未留下常驻进程。

## 五、醒来先做这 3 件事

### 1. 决定 worktree 的去留，并把线2 钉在固定目录（5 分钟）

两线**共用主目录**是本次最大的操作风险（`git reflog` 显示主目录 12:03 被线1 切走、
12:04 还在写文件、收尾时又有 188 行未提交的 `fork_gate.py` 改动）。

```bash
cd /d/飞牛文件同步/工作/简历通-2.0
git worktree list
# 若决定保留：以后线2 一律在 ../简历通-2.0-line2 里操作，主线目录不许再 switch 到 ai-jobs 分支
# 若决定删除（确认线2 不再需要独立环境）：
git worktree remove --force ../简历通-2.0-line2    # 释放约 810 MB
```

### 2. 真实联调（人工在场，全程不要点发送）

夜间**未做**（红线 5：禁止启动引擎、禁止开浏览器、禁止调 `/api/workbench/deliver`；
红线 6：禁止打开 `AI_JOBS_ALLOW_SEND`）。步骤：

```bash
# ① 用线2 worktree 的代码起服务（注意：不要杀 8010，那是线1 的）
cd /d/飞牛文件同步/工作/简历通-2.0-line2
powershell -NoProfile -Command "Start-Process powershell -ArgumentList '-NoExit','-File','.\scripts\start-2.0.cmd'"

# ② 独立启动 BossHunter 2.4.0（8686；引擎自身端口，别和 2.0 的 8010 混）
#    引擎目录：D:\飞牛文件同步\工作\BossHunter（只读引用，未拷入仓库）

# ③ 浏览器打开 http://127.0.0.1:8010/ai-jobs（或 8011），在「设置」里填：
#    引擎安装目录 = D:\飞牛文件同步\工作\BossHunter
#    Python 路径   = <该目录 venv 的 python.exe>
#    → 回到「引擎连接」卡点「连接」→ 应显示「已连接 BossHunter」+ 版本 2.4.x

# ④ 只验只读链路：工作台 / 岗位列表 / 评分轨迹 / 回复收件箱 能出数据
#    ★ 全程不要点「发送」；AI_JOBS_ALLOW_SEND 保持未设置
```

**验收判据**：`/api/ai-jobs/status` 的 `sidecar.reachable` 转 `true`、
`version_ok` 转 `true`；页面无白屏、无未捕获错误；**`POST /deliver` 仍返回 403**。

### 3. 确认 B-3 的 422 兜底观感，并修 B-1 的闸门假信号（10 分钟）

- **B-3**：引擎未配置时，工作台/确认表/历史/回复等 6 个接口返回 **422**。
  打开页面确认这些区域显示「引擎未运行」类提示，**不是红色报错弹窗或白屏**。
  若观感不对，属会话 B 的 UI 兜底问题（需在 `简历通-2.0-fe` 修正，不在本线改）。
- **B-1**：`fork_gate.py` phase_8 第 12 项正则是 4 空格硬编码，对 2 空格缩进的文件恒判 `0==0`。
  建议由**线1 或闸门维护者**把 `re.findall(r"^\s{4}?...` 改为 `r"^\s+?"`，改后复跑
  `--all` 应仍为 `PASS=37/FAIL=0`（真实 key 数 148/148 已独立验证相等）。

---

## 附：合并前后 git log 对比

### 合并前（`feat/ai-jobs-sidecar` @ e5fb384，领先基线 11 提交）

```
e5fb384 docs(ai-jobs): 夜间执行报告（A0-A8 全绿收工）
d20e977 test(ai-jobs): 修 A8 联合选择器下的测试间租约泄漏（NOTE-3），567P/1S 全绿
dc996c5 docs(ai-jobs): 任务板 A7 完成
e692431 docs(ai-jobs): 对抗审查报告（F1-F4 全 PASS + 通用五类）
6038983 docs(ai-jobs): 任务板 A3/A4 完成
eb2f29c feat(ai-jobs): 路由注册 + 投递台互斥 + 互斥/发送闸门测试 + 合规改名 fake_sidecar（L3 全绿 12P/0F/2S）
bdb0985 test(ai-jobs): 测试移植批次 1-5（SOURCE_AI_JOBS/record_applied source 补齐，SK-1 语义冲突 skip）
3e1d942 docs(ai-jobs): 任务板 A2 完成
82f240a feat(ai-jobs): 后端适配层移植（14 服务 + schema + API + 发送闸门默认关 + 两处契约改造）
4cd19df docs(ai-jobs): 三方契约核对表
5cb7dc7 chore(ai-jobs): 建分支与闸门 phase 8
88ae5ac feat(2.0): BOSS 适配器移植（三处修复/Ego 浏览器/页内收录扩展挂载/单测）   ← 基线
```

### 合并后（`feat/ai-jobs-sidecar` @ 000600f，领先基线 30 提交）

```
000600f chore(ai-jobs): 合并前端分支 feat/ai-jobs-frontend 到线2          ← 本次合并（--no-ff）
├─ e5fb384 …（上列 11 个后端提交，原样保留）
└─ 3b12203 docs(ai-jobs-fe): B7 晨间报告与任务板收尾                      ← fe/feat/ai-jobs-frontend
   2edb0de  chore(i18n): ai-jobs 移植文件的存量中文计数登记
   decf9eb  docs(ai-jobs-fe): B6 进度与任务板更新
   53e09a6  feat(ai-jobs-fe): 发送闸门前端体现（空列表探测 403/400，fail-closed + 二次确认保持）
   bf81fb4  docs(ai-jobs-fe): B5 进度与任务板更新
    …（共 18 个前端提交）
```

**合并提交双亲**：`000600f → (e5fb384, 3b12203)`，`--no-ff` 生效，历史可完整回退。
**回退方式**：`git reset --hard e5fb384`（线2 单支丢弃，主线不受影响）。
