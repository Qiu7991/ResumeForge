======================================================================
AI 求职 sidecar · 第二轮（等 v2 稳定期间：清理 + 预备）
======================================================================
使用方式：把 alignment-ai-jobs.md 那份跑完之后，再整份复制下面 === 之间的内容
粘给同一个侧边会话（「请读取 D:\...\AI求职集成-交接文档.md…」那个）。

前提：你已经完成 alignment 那份的 A/B/C/D 四项，并且**没有改任何业务代码**。
======================================================================


你在 Windows 仓库 D:\飞牛文件同步\工作\简历通 工作，分支 fix/v2-single-model。

第一轮你只做了只读分析。这一轮你有 4 件事可做，全部是**安全区内的活**：
不碰 v2 正在改的文件，不碰用户未提交的 50 个改动。

======================================================================
【文件所有权（必须严格遵守）】
======================================================================

**另一个会话（v2 整改）正在并行工作。** 它拥有这些文件，你**绝对不能碰**：
  backend/app/services/resume/**
  backend/app/api/resumes/**
  backend/app/schemas/resume*.py
  backend/tests/test_resume_*.py, test_document_*.py, test_ai_write_*.py
  backend/tests/test_section_visibility_*.py, test_normalize_*.py
  backend/tests/test_fork_regression.py, test_document_shape_invariants.py
  frontend/src/components/resume/**
  frontend/src/features/resume-*/**, profile-library/**
  scripts/check_v2_boundary.py, scripts/v2_status.py, scripts/normalize_*.py
  docs/fork-*.md, docs/quality/**

**你拥有**（可以改）：
  backend/app/services/ai_jobs/**
  backend/app/api/ai_jobs.py
  backend/tests/test_ai_jobs_*.py
  frontend/src/components/ai-jobs/**
  frontend/src/pages/AiJobsPage.tsx
  frontend/src/api/aiJobs.ts, frontend/src/types/aiJobs.ts
  docs/ai-jobs*.md
  **本次新增**：frontend/src/types/job.ts, frontend/src/components/jobs/JobTable.tsx,
             frontend/src/pages/jobs/JobFilterBar.tsx, backend/app/services/job/platform.py

======================================================================
【任务 E：修掉前端 6 处写死的站点名（1–1.5 小时，收益明确）】
======================================================================

这是一条**已经在红的预存量测试**，根因明确：

    backend/tests/test_qa_browser_sites_adversarial.py::test_frontend_production_code_has_no_hardcoded_site_names

实测当前有 3 个文件、6 处命中禁用词（zhipin / boss直聘 / 直聘 / lagou / 51job / liepin）：
    frontend/src/types/job.ts
    frontend/src/components/jobs/JobTable.tsx
    frontend/src/pages/jobs/JobFilterBar.tsx

它断言的是「新增站点只需改后端」，所以正确修法不是把字符串挪个地方，
而是**前端不再出现站点名，一律从后端派生值拿**。

后端已有能力（读一遍再动手）：
    backend/app/services/job/platform.py
    backend/app/api/jobs.py 里派生字段的返回处
（上一轮 sidecar 的红队修正已经确立了这个约定：平台展示名/只读标记由后端
 `_PLATFORM_LABELS` / `_PLATFORM_READ_ONLY` 派生，前端不写死 token。）

步骤：
  1. 先跑测试确认当前红：
       cd backend
       .venv\Scripts\python.exe -m pytest tests/test_qa_browser_sites_adversarial.py -q
     期望：1 failed, 16 passed。

  2. 读那 3 个文件，找出每一处站点名是**干什么用的**：
     - 如果是「筛选项的显示名」→ 改成从接口拿
     - 如果是「类型定义里的字面量联合」→ 改成 `string` 或后端枚举派生
     - 如果是「默认值/兜底」→ 改成空串或从配置拿
     **不要为了过测试而改成拼音首字母或拆字符串**（那是作弊，会留下更难查的坑）。

  3. 如果后端缺一个"平台列表"接口或字段，**允许改 services/job/platform.py 和 api/jobs.py**
     （这两个文件在你的所有权范围内）。但只做最小增量，不要重构。

  4. 改完跑：
       .venv\Scripts\python.exe -m pytest tests/test_qa_browser_sites_adversarial.py -q
     期望：17 passed。
     再跑相邻的：
       .venv\Scripts\python.exe -m pytest tests/test_jobs_platform_filter.py -q
     期望全绿（不能因为你的改动变红）。

  5. 前端类型检查与相关测试：
       cd frontend
       npm run typecheck
       npm run test -- src/components/jobs  （如果这个路径没有测试就跳过）

  6. 提交：
       git add frontend/src/types/job.ts frontend/src/components/jobs/JobTable.tsx frontend/src/pages/jobs/JobFilterBar.tsx
       git add -u backend/app/services/job/platform.py backend/app/api/jobs.py
       git commit -m "fix(jobs): 平台名一律从后端派生，清掉前端写死 token"

  ⚠️ 如果发现这个改动会牵连超过 15 个文件，**停下来**，只写报告说明牵连面，不要硬做。

======================================================================
【任务 F：审计那 50 个未提交改动，产出归属清单（45 分钟，纯只读）】
======================================================================

这是用户最需要的一份东西：**哪些改动是谁的、能不能安全提交**。

做法（只用 git 只读命令，不 add、不 commit、不 stash）：
    cd /d D:\飞牛文件同步\工作\简历通
    git status --porcelain
    git diff --stat
    git diff <每个文件>

分类规则：
  A类 = 与招呼语/投递台相关（apply.py, job_match.py, QueueItemEditor.tsx,
        ApplySettingsModal.tsx, i18n/*.applyQueue*, i18n/*.applySettings*,
        schemas/apply/*, prompts/apply_greeting.md, test_apply_greeting_*）
  B类 = 与覆盖补全/投影相关（projectionContent.*, ResumeCoverageNotes.tsx,
        resume_coverage.py, fillCoverageNote.test.ts）
  C类 = 与显隐/技术栈/去重相关（可能是 v2 会话已经部分提交后剩下的）
  D类 = 文档/配置（CHANGELOG.md, .npmrc, runtime/）
  E类 = 无法归类

对每一类给出：
  - 文件清单（含行数变化）
  - 一句话说明"这看起来是什么改动"
  - 判断：**应该提交 / 应该丢弃 / 需要用户决定**
  - 判断依据（引用具体的 diff 片段，不要猜）

产出：`D:\飞牛文件同步\工作\简历通\docs\quality\uncommitted-audit.md`

**绝对不要执行 `git add`、`git commit`、`git stash`、`git checkout -- <file>`。**
只写文档。

这份文档的价值：用户早上可以照着它，3 分钟内把那 50 个改动切开提交，
而不是花一小时一个个看 diff。

======================================================================
【任务 G：给 sidecar 写一份"v2 合并后适配清单"（1 小时，纯文档）】
======================================================================

基于你第一轮任务 B 产出的 `docs/ai-jobs-v2-read-paths.md`，写第二份：
`docs/ai-jobs-v2-adaptation-plan.md`

内容要求（**每条都要给具体文件和行号，不要写"检查一下"**）：

1. **必须改的**（v2 合并后会坏的）
   表格：文件 | 行号 | 现在怎么读 | 改成什么 | 风险 | 验证命令
   预期至少覆盖：`services/ai_jobs/resume_sync.py`、`services/job/job_match_context.py`、
   `api/apply.py` 里读 `record.content` 的地方。

2. **可以不改的**（读了但只做哈希/比较，形状无关）
   逐条说明为什么安全。

3. **需要验证但不确定的**
   列出你的不确定点，每条给一个"怎么验证"的具体命令或探针思路。

4. **改动顺序建议**
   哪一条先改（风险最低的），哪一条最后改（要跑全量）。

5. **每一条的回滚方式**
   （单文件 `git checkout -- <file>` 就够，还是需要连带改测试）

**不要写代码实现，只写计划。** 等 v2 定稿后照这份计划动手。

======================================================================
【任务 H：把两份 sidecar 文档的待办收口（30 分钟）】
======================================================================

读 `docs/ai-jobs-parity.md` 和 `D:\飞牛文件同步\工作\AI求职集成-夜间报告.md`，
把里面所有"待办 / 未做 / TODO / 部分实现"的条目抽出来，合成一张总表：

产出 `docs/ai-jobs-todo-inventory.md`：

| # | 来源 | 事项 | 类型（代码/文档/需人工） | 阻塞原因 | 预估耗时 | 建议顺序 |

排序原则：能自动化且无风险的排前面；需要用户本人在场的（真实 BOSS、扫码、发送）排最后
并单独标注「必须用户在场」。

======================================================================
【绝对禁止（这一节比上面重要）】
======================================================================
1. 禁止碰第一节列出的 v2 会话所有权文件
2. 禁止 `git add` / `git commit` / `git stash` / `git checkout` / `git switch` / `git rebase`
   （任务 F 只读；任务 E 的提交是唯一例外，且只能 add 你在任务 E 里明确列出的文件）
3. 禁止改任何测试断言
4. 禁止启动真实 BOSS / 访问招聘网站 / 真实发送
5. 禁止跑后端全量 pytest（44 分钟）
6. 禁止改 `backend/app/services/resume/**`（那是 v2 会话的核心区）
7. 禁止"顺手"重构 services/job/ 的既有逻辑——只做任务 E 需要的最小增量

======================================================================
【时间管理】
======================================================================
现在看时间。如果距离 09:00 不到 1.5 小时：
  只做 F（审计 50 个改动）→ 写报告。F 是纯只读，永远不会坏。
如果还有 2–3 小时：
  F → E → H → G。
如果超过 3 小时：
  F → E → G → H，做完还有时间就补 G 的验证探针。

**F 永远排第一**，因为它纯只读、零风险，而且用户最需要。

======================================================================
【汇报格式】
======================================================================
1. 现场：当前分支 / HEAD / 未提交改动数
2. 任务 F：A/B/C/D/E 五类的文件数与各自结论（提交/丢弃/待定）
3. 任务 E：修前修后测试结果（1 failed → ? passed）
4. 任务 G/H：产出文档的绝对路径
5. 提交哈希清单
6. "我判断不了、需要你决定的事"
7. "我碰了哪些文件"（精确清单，方便用户核对没有越界）

做完停下。
