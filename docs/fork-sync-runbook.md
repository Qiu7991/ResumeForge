# Fork 同步 Runbook（上游合并流程 · Phase 6）

> 适用：`Qiu7991/ResumeForge`（Fork）↔ 上游 `magicapple123/ResumeForge` 的同步，以及任何
> 把上游改动并进本仓库的操作。核心教训：**2026-11-01 的"一次性大爆炸合并"（1154 文件、
> +79163/−64432）是 v1/v2 双真相积病的根源**——以后禁止再那样合并。
> 每次同步的验收口径 = `scripts/v2_gate.py --all` 全绿 + 本文的合并后验证。

## 1. 同步节奏

- **每月一次小批量**；单次合并引入的变更文件数上限 **300**，超过就拆成多批
  （按模块拆：模板一批、基础设施一批、业务一批），每批单独走完本文流程。
- 上游镜像 remote 只读（`upstream`），本地二开提交按功能成串，方便回溯。
- 禁止 `merge --no-ff` 大对象之外的操作：不 rebase 已推送历史、不改已发布 revision。

## 2. 合并前 checklist（逐项勾选，全过才动手）

```text
[ ] stop.cmd                                   # 停应用（写库进程清零）
[ ] backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --backup
[ ] git status 干净（有未提交改动先 WIP 提交，绝不 reset/checkout .）
[ ] backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --all   # 全绿才继续
[ ] 记录当前 alembic heads（backend 目录）：
    .venv\Scripts\python.exe -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"
[ ] 记录起点提交哈希：git rev-parse --short HEAD
[ ] 数据库备份文件名已抄进执行记录（回滚要用）
```

## 3. 合并中：冲突处理优先级

| 文件类型 | 优先谁 | 理由 |
|---|---|---|
| 上游基础设施（`app/database.py`、`pyproject.toml`、CI、`Check-All.ps1` 骨架） | **上游** | 跟随基础设施演进，本地不背维护分叉 |
| 二开功能文件（`services/ai_jobs/**`、`resume_dedupe.py`、`resume_coverage.py`、招呼语、画像导入、投递浏览器） | **二开** | 上游没有这些能力；二开侧已按 v2 收口 |
| 模板 `.j2` | **上游引擎 + 二开模板语法** | 模板引擎会变；本地 21 个 `.j2` 已改 v2 语法（`page_title` + `_resume_document.j2`），冲突时保语法适配 |
| 迁移文件 | **上游编号 + 本地补新迁移** | 绝不改已发布的 revision；本地新迁移接到上游 head 之后（见 0074 空迁移汇合的先例） |
| `schemas/resume_document.py` 等核心模型 | **上游 + 本地不变量层**（`document_invariants.py`） | 模型改动必须重新过 `test_document_shape_invariants.py` |
| 测试 | **二开断言不动，上游新测试照收** | 本地测试锁二开不变量（E4） |

冲突解决后必须：`v2_gate.py --phase 1`（数据仍是全 v2）+ `--phase 5`（同形不变量）。

## 4. 合并后验证（按顺序，全过才算合并完成）

```text
1. backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --all
   （期望：Phase 0-6 全 PASS；任何 FAIL 先解决再继续）
2. 后端定向（backend 目录）：
   .venv\Scripts\python.exe -m pytest tests/test_resume_coverage.py tests/test_resume_dedupe.py ^
     tests/test_document_save_prune.py tests/test_ai_write_invariants.py ^
     tests/test_document_shape_invariants.py tests/test_fork_regression.py ^
     tests/test_section_visibility_exports.py tests/test_resume_hidden_sections.py -q
3. 前端（frontend 目录）：
   npm run typecheck
   npm run lint
   npm run test -- src/features/profile-library/forkRegression.test.ts src/components/resume/SectionVisibilityPanel.test.tsx src/components/resume/PreviewSectionsControl.test.tsx
4. 真实库冒烟（start.cmd 后，方案文档 §6.4 的九步）：
   [ ] 简历列表能打开旧记录
   [ ] 详情预览正常，隐藏板块确实不出现
   [ ] 生成一份新简历：技术栈不出现、项目不重复
   [ ] AI 修订同一份：技术栈不出现、项目不重复、项目数量不变
   [ ] 覆盖清单「从资料补上这段」：内容出现、无重复
   [ ] 「AI 润色这段」：先补齐再润色，结果有变化
   [ ] 隐藏一个板块：刷新 + 导出 HTML/PDF/Word 均不出现
   [ ] 以这份简历为底稿再生成一次：新记录 format_config 无 hidden_sections
   [ ] 投递台：队列简历下拉、招呼语生成、分页条数切换正常
```

## 5. 回滚（任何一步不对就退，不要"在坏数据上继续修"）

```bat
:: 1) 代码回退到合并前
git revert -m 1 <合并提交哈希>        （或 git reset 前先确认没有别人在用本分支）

:: 2) 数据库回退（WAL 模式：必须先删 -wal/-shm，否则残留 WAL 会把恢复后的库改回坏状态）
stop.cmd
del backend\data\resume_forge.db-wal backend\data\resume_forge.db-shm
copy /y backend\data\resume_forge.db.<合并前备份名>.bak backend\data\resume_forge.db
start.cmd

:: 3) 验证：v2_gate.py --phase 0（备份可用）+ --phase 1（数据仍全 v2）
```

## 6. 已知的重复/冲突源（下次同步前先看这里）

| 源 | 现状 | 处置 |
|---|---|---|
| 迁移文件名前缀 | 历史上 0069/0070 各有两份，2026-11-04 已重编号为 0076/0077（revision 字符串未动，alembic 无感） | 新增迁移一律取 `git ls backend/migrations/versions` 里**未用过**的 4 位前缀，落名前先查重 |
| `scripts/convert_resume_documents.py` vs `scripts/normalize_resume_documents.py` | 功能重叠：前者不能消费旧版式键（hidden_sections），后者可以（Phase 1 的正式脚本） | 本轮保留后者；**下次同步时二选一合并**，删掉前者前先 grep 引用 |
| `scripts/import_portrait.py::_backup_database` 与 `v2_gate.py --backup` | 同一套 `sqlite3.backup` 写法的两份拷贝 | 允许；若上游改动其一，另一份同步对齐 |
| `docs/fork-v2-compatibility-plan.md` 的任务卡 | Phase 0-6 已全部执行完 | 新会话不要再按任务卡重跑；以 `v2_gate.py --all` + 本 runbook 为准 |
| 并行会话同时在本仓库工作 | 2026-11-04 实际发生过：一个会话的 staged 文件被另一个会话的提交扫走 | 并行工作期间**不要 `git add -A`/`commit -a`**；提交前 `git status` 逐文件核对 stage 区 |
