======================================================================
AI 求职 sidecar · 早晨续接提示词（v2 整改之后）
======================================================================
使用方式：早上看完 D:\飞牛文件同步\工作\简历通-morning-report.md 之后，
把下面两条横线之间的全部内容，整段粘给新的会话（或同一个会话）。

前提：v2 整改的 Phase 0–3 已经跑完。如果闸门没全绿，**先不要用这份提示词**，
先用 fork-v2-phase-prompts.txt 里对应的卡片把闸门修绿。
======================================================================


你在 Windows 仓库 D:\飞牛文件同步\工作\简历通 工作。
这是一个 FastAPI + React 的本地二开项目（ResumeForge），我们在往上面加一个「AI 求职」功能（sidecar 集成 BossHunter）。

昨晚跑完了一轮 v2 文档模型整改。今天要做的是：**确认 v2 整改没把 sidecar 弄坏，然后收掉 sidecar 的剩余尾巴。**

======================================================================
【第一件事：读三份文件，不要读别的】
======================================================================
1. D:\飞牛文件同步\工作\AI求职集成-交接文档.md  —— 第 0.0 节 + 第 17 节任务板
2. D:\飞牛文件同步\工作\简历通-morning-report.md  —— 昨晚 v2 整改做了什么
3. D:\飞牛文件同步\工作\简历通\docs\fork-v2-compatibility-plan.md —— 只读 Phase 2 和 Phase 3 两节

**不要重读整个仓库。** 你要用的信息都在上面三份里。

======================================================================
【第二件事：先确认 v2 整改是好的（10 分钟）】
======================================================================
cd /d D:\飞牛文件同步\工作\简历通

1. 闸门全绿吗？
   backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --all

2. 库里的 v1 记录清零了吗？（v1 记录的 version 是 `None`，不是 1，所以按 version 键计数）
   backend\.venv\Scripts\python.exe -I -c "import json,sqlite3;from collections import Counter;c=sqlite3.connect('backend/data/resume_forge.db');print(Counter(json.loads(r or '{}').get('version') for (r,) in c.execute('select content from resume_record where deleted_at is null')))"
   期望输出：`Counter({2: 12})` —— 全是 2，没有 `None` 这个键。
   如果还有 `None`，说明 Phase 1 没做完，回头跑 normalize 脚本。

3. sidecar 专项测试还绿吗？（关键：v2 收口可能碰到 resume_sync / job_match_context）
   cd backend
   .venv\Scripts\python.exe -m pytest tests/test_ai_jobs_resume_sync.py tests/test_ai_jobs_greeting.py tests/test_ai_jobs_e2e.py tests/test_ai_jobs_delivery.py tests/test_ai_jobs_redteam_fixes.py -q

**三条都过 → 继续往下做。任何一条不过 → 停下来先修，不要往下做。**
如果第 3 条挂了，大概率是 v2 的 write-path 收口改了 `save_record`，
而 `services/ai_jobs/resume_sync.py` 或 `services/job/job_match_context.py`
还在按旧方式读 `record.content`。修法：改成走 `document_io.document_for_record(db, record)`。

======================================================================
【第三件事：sidecar 剩余任务（按这个顺序做）】
======================================================================

■ 任务 A：v2 之后 sidecar 的读取口收口（如果有需要）
   检查这两个文件还在不在直接消费 record.content：
     backend/app/services/ai_jobs/resume_sync.py
     backend/app/services/job/job_match_context.py
     backend/app/api/apply.py
   如果它们在用裸 content（比如 json.dumps({"content": resume.content})），
   改成先经 document_io.document_for_record / ensure_document_version 转成 v2。
   理由：v2 收口之后库里虽然都是 v2，但"直接读什么形状"这件事还是要单源，
   否则下一个合并上游的人又会踩同一个坑。
   验证：上面那 4 个测试文件仍全绿。

■ 任务 B：前端 6 处写死站点 token（交接文档待办 #4）
   先找出这 6 处：
     grep -rn "boss直聘\|BOSS直聘\|直聘" frontend/src --include=*.tsx --include=*.ts
   改用后端已有的派生方案（services/job/platform.py 的 _PLATFORM_LABELS）。
   原则：前端不写死平台名，一律从 API 拿。
   验证：npm run typecheck && npm run lint

■ 任务 C：补 parity 核对（交接文档待办 #6）
   按 docs/ai-jobs-parity.md 第 10.3 节逐项标注「已实现 / 部分 / 未做 + 验收边界」。
   这是纯文档工作，只改 docs/ai-jobs-parity.md。

■ 任务 D：补「第四步：对抗项必要性复盘」附章（交接文档待办 #5）
   追加到 D:\飞牛文件同步\工作\AI求职集成-夜间报告.md 末尾。
   内容：F1–F8 八条修正里，哪几条是"真实威胁"、哪几条是"预防性"、
   哪几条其实可以不做。要给出判断依据，不要罗列。

======================================================================
【第四件事：做不了的两件，不要尝试】
======================================================================
■ 真实 BOSS 端到端联调 —— **必须我本人在场**（要扫码登录、要确认发送）
   不要尝试启动真实引擎、不要访问招聘网站。
   你只需要：把晨间验收步骤写成一份 checklist，放到
   D:\飞牛文件同步\工作\AI求职集成-晨间验收清单.md
   内容按交接文档第 17 节 + 安全模式倒推，每步写：操作 → 预期 → 失败时看哪。

■ OCR 二道审查 —— 本机没有 Key，跳过。不要假装跑过。

======================================================================
【硬性规则】
======================================================================
1. 每个任务做完就跑对应测试，绿了才提交。提交信息带任务 ID（feat(ai-jobs): B ...）。
2. 禁止 git reset --hard / checkout . / clean -fd / stash drop
3. 禁止 push、禁止 merge 到 main、禁止 rebase
4. 禁止修改已存在的测试断言
5. 禁止删任何文件（除了明确要求改的那几行）
6. 禁止碰 backend/data/resume_forge.db（这是真实用户数据）
7. 遇到需要我决策的（比如"计划外文件归属"这种），**不要自己决定**，
   写进报告的"待决策"一节，跳过，继续下一个任务。

======================================================================
【汇报格式】
======================================================================
1. v2 确认三项的结果（闸门 / v1 清零 / sidecar 测试）
2. 每个任务的状态：完成（提交哈希）/ 跳过（原因）/ 未开始（原因）
3. 改了哪些文件（绝对路径）
4. "待你决策"清单
5. "遗留风险"

做完就停，不要自作主张扩大范围。
