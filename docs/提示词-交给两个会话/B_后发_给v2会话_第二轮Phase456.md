======================================================================
简历通 v2 整改 · 第二轮（审查之后：Phase 4/5/6 + 预存量清理）
======================================================================
使用方式：等你把 adversarial-review-v2.md 那份提示词跑完、P0 修完、报告拿到之后，
再整份复制下面 === 之间的内容粘给同一个会话。

⚠️ 前提：对抗性审查已完成、P0 已修、`v2_gate.py --phase 1/2/3` 全绿。
   不满足就不要粘这份。
======================================================================


你在 Windows 仓库 D:\飞牛文件同步\工作\简历通 工作，分支 fix/v2-single-model。

第一轮（Phase 0–3 + 对抗性审查）已经做完。这一轮要做三件事，按优先级：

  A. Phase 4：静态守卫（必须做完）
  B. Phase 5：同形不变量测试 + 二开回归包（必须做完）
  C. Phase 6：合并 runbook（必须做完）
  D. 预存量失败清理（有余力再做，价值极高但不是必须）

======================================================================
【文件所有权（关键：另一个会话在并行工作）】
======================================================================

**有一个 AI 求职 sidecar 的会话正在同一个仓库里并行工作。**
它会动这些文件，你**绝对不能碰**：
  backend/app/services/ai_jobs/**
  backend/app/api/ai_jobs.py
  backend/app/services/job/**
  backend/app/services/apply/**
  backend/app/api/apply.py
  frontend/src/components/ai-jobs/**
  frontend/src/pages/AiJobsPage.tsx
  frontend/src/api/aiJobs.ts
  frontend/src/types/aiJobs.ts
  docs/ai-jobs*.md

如果闸门或测试卡在这些文件上，**跳过并记录**，不要修。

你**拥有**这些目录（可以自由改）：
  backend/app/services/resume/**
  backend/app/api/resumes/**
  backend/app/schemas/resume*.py
  backend/tests/test_*.py（除 test_ai_jobs_*）
  scripts/**
  frontend/src/features/resume-*/**, frontend/src/components/resume/**
  frontend/src/pages/ProfilePage*.tsx, frontend/src/pages/ResumesPage*.tsx
  docs/quality/**, docs/fork-*.md

======================================================================
【A. Phase 4：静态守卫（1–1.5 小时）】
======================================================================

新建 `scripts/check_v2_boundary.py`，实现四类检查。**必须用 AST，不要用正则**
（正则会把 `response.content`、`message.content` 全算进来；backend/app 里 `.content` 共 201 处，
而真正危险的只有 0 处）。

■ 检查 1：v1 形状消费（AST）
禁止对 `record.content` / `resume.content` / `row.content` / `current.content`
做下标或 `.get()` 取 v1 字段名。v1 字段清单：
    projects, experience, educations, internships, awards, campus_experience,
    custom_sections, job_intent, tech_stack, hidden_points
命中就报 `<文件>:<行号> — 直接按 v1 形状消费 record.content`。

■ 检查 2：`record.content` 的使用形态
每一处出现必须满足下列之一，否则报错：
   (a) 直接作为这些函数的实参：document_for_record / ensure_document_version /
       coerce_document / paper_document / prepare_document_for_save
   (b) 在哈希/比较白名单文件里：document_save.py / resume_delivery.py /
       ai_jobs/resume_sync.py
   (c) 赋值给变量后立刻传给上面的函数（允许一层间接：`raw = record.content` 后
       `ensure_document_version(raw)`）

■ 检查 3：旧版式键的写入
禁止出现"给 result/values 写 hidden_sections 或 section_order"的**任何**形式：
    下标赋值  x["hidden_sections"] = ...
    .update({...})   .setdefault(...)   {**x, "hidden_sections": ...}
⚠️ 这条要小心：`validated_format_config` 里有一个 `result.update({str(key): hidden})`
   是**解析外部输入**用的，不是落库写入。用下面两条区分：
   - 函数名在 `{validated_format_config}` 白名单 → 允许（它只解析外部输入）
   - 其他任何地方 → 报错
   白名单必须写在脚本里并注释理由。

■ 检查 4：迁移完整性
   a) `migrations/versions/*.py` 的**文件名 4 位数字前缀**唯一（不是 revision 字符串——
      revision 本来就唯一，查它永远绿）
   b) 每个 `down_revision` 引用的 id 在目录里存在
   c) heads 只有一个（自己解依赖图，不要依赖 alembic 包）

■ 输出格式
每条错误一行：`FAIL <检查名> — <文件>:<行号> — <说明>`
全绿时：`PASS <检查名> — N 个文件`，末尾 `汇总：X 通过 / Y 失败`，有失败 exit 1。

■ 反向验证（**必须做，并把输出贴出来**）
在 backend/app/api/ 临时加一行：
    def _probe(record): return record.content.get("projects")
跑守卫 → 必须报错且指到那一行。
再改成：
    def _probe(record): return ensure_document_version(record.content)
跑守卫 → 必须放行。
验完把这两行删掉。

■ 接入
在 `scripts/Check-All.ps1` 的第 1 步（ruff）之后加一步，调用这个脚本。

■ 验收
    backend\.venv\Scripts\python.exe -I scripts\check_v2_boundary.py
必须 exit 0 且输出 `汇总：4 通过 / 0 失败`。

提交：
    git add scripts/check_v2_boundary.py scripts/Check-All.ps1
    git commit -m "test(v2): 加 v2 边界静态守卫（Phase 4）"

======================================================================
【B. Phase 5：同形不变量 + 回归包（2–3 小时）】
======================================================================

■ B1（先做这个，价值最高）：`backend/tests/test_document_shape_invariants.py`

这是整轮整改最重要的一个测试。目标：**同一份记录，从任何入口取出来的文档必须完全一样。**

实现思路：
  1. 用 fixture 造 4 份记录（直接写库，用测试库）：
     - 一份纯 v2、结构干净
     - 一份从 v1 转换来的（含 education/experience/projects/skills）
     - 一份带 `section.hidden=True` 的
     - 一份带技术栈项 `placement="hidden"` 的
  2. 对每份记录，用下列入口各取一次文档：
     - `document_io.document_for_record(db, record)`（详情路径）
     - `document_io.ensure_document_version(record.content, ...)`（裸读路径）
     - `export_markdown(...)` 之前的 `coerce_document(record.content, ...)`
     - `paper_document(coerce_document(...))`（纸面路径）
     - `document_versions.document_content(record.content, render_context)`（历史路径）
  3. 每个结果做：`json.dumps(..., sort_keys=True, ensure_ascii=False)` → sha256
  4. 断言：**前三个（详情/裸读/coerce）的 sha256 必须完全相同**。
     `paper_document` 那一个允许不同（它会剔除隐藏项），但要断言"它等于前者的隐藏项被剔除后的版本"。
  5. 断言 `paper_document` 的结果在 v1 来源和 v2 来源上行为一致。

这个测试锁住的是 P1（同一功能时好时坏）和 P3（两套真相）这两类问题，
以后任何人改读路径，它都会红。

■ B2：`backend/tests/test_fork_regression.py`

矩阵（注意"记录原本是 v1"那一列，不是"请求体 v1"）：

| 写路径 | 请求体 v1 | 请求体 v2 | 记录原本是 v1 | 断言 |
|---|---|---|---|---|
| 生成落库 | 有 | 有 | — | 无重复、技术栈隐藏、页数上限 |
| AI 修订 | — | 有 | 有 | 无重复、技术栈隐藏、**条目不减少** |
| 手工保存 | 有 | 有 | — | 不自动删内容，但结构合法 |
| 覆盖补全 | — | 有 | — | 按身份合并、幂等 |
| 导出四格式 | — | 有 | 有 | 隐藏板块不出现、顺序一致 |

每条断言写清"失败时说明哪个功能/哪条不变量坏了"，不要只写 `assert x == y`。

■ B3：`frontend/src/features/profile-library/forkRegression.test.ts`
只测纯函数层（`fillCoverageNote` 的幂等与身份匹配、`buildSectionOrderConfig` 不透传旧键）。
不要起 React 渲染。

■ 验收
    backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --phase 5
必须：`PASS 同形不变量测试全绿`、`PASS 二开回归包全绿`。

提交（可以分两次）：
    git add backend/tests/test_document_shape_invariants.py
    git commit -m "test(v2): 加同形不变量测试，锁住读写路径单源（Phase 5）"
    git add backend/tests/test_fork_regression.py frontend/src/features/profile-library/forkRegression.test.ts
    git commit -m "test(v2): 二开功能回归矩阵（Phase 5）"

======================================================================
【C. Phase 6：合并 runbook（1 小时）】
======================================================================

新建 `docs/fork-sync-runbook.md`。必须包含这些具体内容（不要写空话）：

1. **同步节奏**：每月一次，单次变更文件数上限 300（超过就拆分）
2. **合并前 checklist**（可直接勾选）：
   - [ ] `stop.cmd` 停应用
   - [ ] `v2_gate.py --backup` 生成备份
   - [ ] `git status` 干净（或已 WIP 提交）
   - [ ] `v2_gate.py --all` 全绿
   - [ ] 记录当前 `alembic heads`
3. **合并中冲突处理优先级表**：
   | 文件类型 | 优先谁 | 理由 |
   | 上游基础设施（database.py / pyproject / CI） | 上游 | 跟随基础设施演进 |
   | 二开功能文件（services/ai_jobs, resume_dedupe…） | 二开 | 上游没有这些能力 |
   | 模板 .j2 | 上游引擎 + 二开模板改语法 | 模板引擎会变 |
   | 迁移文件 | 上游编号 + 二开补新迁移 | 不能改已发布的 revision |
4. **合并后验证**（按顺序，每步的命令都写出来）：
   - `v2_gate.py --all`
   - 后端定向：resume 相关 + fork 回归
   - 前端：typecheck / lint / 定向 vitest
   - 真实库冒烟 9 步（从方案文档 §6.4 抄过来）
5. **回滚**：给具体命令，包含删 `-wal`/`-shm`（库是 WAL 模式，不删会重放）
6. **已知的重复/冲突源**（写清楚，避免下次踩）：
   - 迁移文件名前缀 0069 / 0070 各有两份
   - `scripts/convert_resume_documents.py` 与 `scripts/normalize_resume_documents.py` 功能重叠
     （前者不能消费旧版式键，后者可以；本轮保留后者，**下次同步时二选一合并**）

提交：
    git add docs/fork-sync-runbook.md
    git commit -m "docs(v2): 合并同步 runbook（Phase 6）"

======================================================================
【C2. 调试入口脚本（强烈建议做，30 分钟，直接给用户省时间）】
======================================================================

新建 `scripts/v2_status.py`：**一条命令看清当前状态**。用户调试时不用记五条命令。

行为（全部只读，不写库）：
    backend\.venv\Scripts\python.exe -I scripts\v2_status.py

输出形如：

    === 简历通 v2 状态 ===
    分支      fix/v2-single-model @ f7df4afd
    工作树    50 个未提交改动
    数据库    backend/data/resume_forge.db (wal, integrity=ok)
    版本分布  live v1=0 / v2=12   含软删 v1=0 / v2=40
    隐藏板块  22 条记录有 section.hidden（明细见 --verbose）
    旧版式键  format_config 里 hidden_sections/section_order 残留 0 条
    备份      最近一份 pre-v2-normalize-*.bak = xxx.bak (integrity=ok)

    === 闸门 ===
    Phase 0 3/3 PASS
    Phase 1 4/4 PASS
    Phase 2 5/5 PASS
    Phase 3 5/5 PASS
    Phase 4 0/3 FAIL（未建 check_v2_boundary.py）
    Phase 5 1/3 FAIL（未建同形不变量 / 回归包）
    合计 18 通过 / 3 失败

    === 回归（定向，约 40 秒）===
    resume 核心        28 passed
    write invariants   9 passed
    section visibility 10 passed
    sidecar            36 passed

    === 结论 ===
    可以继续 Phase 4/5；不要动数据库。

要点：
1. 闸门部分**直接 import 或 subprocess 调用** `scripts/v2_gate.py` 的各 phase 函数，
   不要复制它的检查逻辑（否则两套真相）。
2. 回归部分跑固定 4 组定向测试，**不要跑全量**（44 分钟）。
3. 加 `--verbose` 打印 22 条 hidden 记录的 id 明细与 section key。
4. 加 `--json` 输出机器可读版本（供将来 CI 用）。
5. 输出必须用中文，用户直接看。

这个脚本的价值：用户早上起来只需跑这一条，就知道"能不能用、能不能继续、哪里坏了"。

提交：
    git add scripts/v2_status.py
    git commit -m "chore(v2): 加一条命令的状态查看脚本"

======================================================================
【D. 预存量失败清理（有余力再做，按下面的顺序挑）】
======================================================================

前提：A/B/C 全绿、`v2_gate.py --all` 全绿。如果没全绿，直接跳过 D，去写报告。

⚠️ 这一节**只允许改测试文件和 mock，不允许改业务逻辑**。任何要改业务代码的，
记进报告的"待决策"一节，不要动手。

按投入产出比从高到低：

■ D1（最高价值，改动最小）：前端 20 条失败 = 1 个 mock 缺导出
现象：`src/pages/ProfilePage.test.tsx`、`ProfilePage.webform.test.tsx`、
      `ProfilePage.webform.customFields.test.tsx` 共 27 条失败（其中 20 条是同一根因）。
根因：这三个文件的 `vi.mock("../api/profile", () => ({...}))` 里没有
      `getGenerationPreferences`，而 `src/api/profile.ts:20` 导出了它，组件调用时崩。
修法：给这三个 mock 工厂补上 `getGenerationPreferences: vi.fn(async () => ({ include_tech_stack: false }))`
     （或复用文件里已有的 apiMocks 表）。
验证：
    cd frontend
    npm run test -- src/pages/ProfilePage.test.tsx src/pages/ProfilePage.webform.test.tsx src/pages/ProfilePage.webform.customFields.test.tsx
期望：从 27 failed 变成 0 failed。
如果补完还有失败，说明根因不止一个，**停下来记录**，不要把断言改松。

■ D2：后端 48 条"顺序依赖失败"的隔离（价值高、风险中）
现象：`test_collection_archive`(15)、`test_dataset_scope`(11)、`test_dataset_scope_stream`(5)、
      `test_dataset_activation_compensation`(3)、`test_dataset_request_identity`(3)、
      `test_api_sample_dataset`(3)、`test_assistant_proposals_endpoint`(2)、
      `test_qa_adversarial_20261019`(2) 等——单独跑都过，全量跑就挂。
根因假设：数据集激活状态（`active.json` 指针 + 内存里的租约）在用例间泄漏。
`backend/tests/conftest.py` 已有 `_reset_to_test_database` 和 `_clear_datasets` 两个 autouse fixture，
但可能覆盖不全（比如模块级缓存、engine 已冻结的引用、后台线程持的 lease）。

做法（保守版，不要大改）：
  1. 先用最小复现锁定：跑 `pytest tests/test_dataset_scope.py tests/test_collection_archive.py -q`
     看是否复现；再单独跑每个文件看是否通过。
  2. 找出 conftest 里没被重置的状态。重点查：
     - `app.database` 里冻结的 engine / SessionLocal 绑定
     - `dataset_registry` 的模块级缓存
     - 有没有后台线程（runner）持着 lease
  3. 只允许改 `backend/tests/conftest.py`：补一个更强的 autouse fixture 来清这些状态。
     **不要改 app/ 下的任何代码。**
  4. 每补一项就重跑那两个文件，确认失败数下降。
  5. 时间盒：**最多 1.5 小时**。到点没解决就停，把已定位的写进报告。

■ D3：后端 8 条确定性失败（每条独立，按需挑）
从基线文档里挑**不改业务逻辑**的：
   - `test_preflight.py` 2 条：`generation_plan.md` / `portrait_extract.md` 没进提示词完整性清单
     → 改清单文件（属于配置，不是业务逻辑），先确认清单文件在哪、加进去不破坏别的断言
   - `test_assistant_prompt_budget.py` 1 条：系统提示固定成本 23836 > 23800
     → 这是**真问题**（提示词膨胀），但改提示词会影响所有对话质量，**不要自己改**，只记录
   - `test_file_size_budget.py` 1 条：12 个文件超 500 行
     → 不要拆文件（风险大），只记录
   - `test_candidate_import.py` 1 条：'社招' vs '校招'
     → 先判断哪个是正确业务口径，判断不了就只记录
   - `test_resume_sample_content.py` 1 条：split/small 模板填充率 63.8% < 0.65
     → 调模板 CSS 风险高，只记录
   - `test_resume_templates.py` 1 条：预览渲染 `'resume' is undefined`
     → 可能是真 bug，值得查（30 分钟时间盒）

**判断原则**：改一行能修好、且不改变用户可见行为的 → 修；
需要判断业务口径、或会改变渲染结果的 → 只记录。

======================================================================
【收尾：写第二轮报告（必做，20 分钟）】
======================================================================

新建 `D:\飞牛文件同步\工作\简历通-round2-report.md`：

    # v2 整改第二轮报告（2026-11-04）

    ## 一句话结论
    （Phase 4/5/6 做完了吗，预存量清了几条，工作树干净吗）

    ## 1. v2_gate.py --all 的完整输出
    （原样粘贴，不要只写汇总）

    ## 2. 各阶段状态
    | 阶段 | 状态 | 提交哈希 | 关键证据 |

    ## 3. 预存量清理结果
    | 项 | 修前失败数 | 修后失败数 | 改动文件 |
    （D1/D2/D3 各自一行；没做的写"未做 + 原因"）

    ## 4. 改了哪些文件（绝对路径 + 一句话）

    ## 5. 没敢做的事 / 待你决策
    （每条：现象 + 为什么不敢 + 建议怎么做）

    ## 6. 早上调试入口
    （给出 3 条最有用的命令：怎么跑全量闸门、怎么跑定向回归、怎么看某个功能）

    ## 7. 提交清单
    （本轮所有提交的哈希 + 一行说明，按时间顺序）

======================================================================
【绝对禁止】
======================================================================
1. 禁止碰第一节列出的 sidecar 文件（另一个会话在用）
2. 禁止修改 `scripts/v2_gate.py`
3. 禁止修改已有测试的断言来让它变绿（补 mock 可以，改断言不行）
4. 禁止改 app/ 下的业务逻辑来让预存量测试变绿
5. 禁止 git reset / checkout . / clean -fd / stash drop / rebase / push
6. 禁止跑后端全量 pytest（44 分钟，基线已建档；只跑定向）
7. 禁止重命名/移动文件
8. 每完成一个阶段必须提交，不要把多个阶段混在一个提交里

======================================================================
【时间管理】
======================================================================
现在时间你自己看。如果距离 09:00 不到 2 小时，只做 A + B1 + C，跳过 D 和 B2/B3。
如果不到 1 小时，只做 A，然后写报告。

**宁可少做也不要留下半成品。** 每个提交必须是"测试绿 + 闸门绿"的状态。
