# 2.0 移植进度日志（追加式）

> 格式：`时间 | 任务号 | 结果 | 证据/闸门原始输出 | commit`

---

- 2026-11-06 03:0x | §2.4 | 1.x 开工指纹 | `git rev-parse HEAD` = a09b63e43cac1edd957f84daf7794b18cdf0023e；`git status --porcelain | wc -l` = 0；分支 = fix/v2-single-model；`backend/data/resume_forge.db` = 160,989,184 字节（与计划 §1.1 一致）；8005 未监听（1.x 未运行） | —
- 2026-11-06 03:0x | §4.1 | 冻结 tag + 建仓 | `git tag fork-1x-frozen-20261106 HEAD` 成功（对 1.x 唯一写操作）；`git clone --depth 1 --branch v2.0.0 file:///D:/飞牛文件同步/工作/简历通 简历通-2.0` 成功（4266 文件）；rm .git 后 `git init -b main` + 单提交 + `git tag upstream-v2.0.0` + `git switch -c feat/fork-port` | d893243
- 2026-11-06 03:0x | §4.2 | audit 副本 | `git clone 简历通-2.0 简历通-2.0-audit` + `git switch -c feat/data-bridge` | —
- 2026-11-06 03:0x | §4.3 | 基线验证 | `frontend/package.json` version = **2.0.0**；`ls backend/migrations/versions | wc -l` = **1**（0001_baseline_v2.py，远小于 78）；`git log --oneline` 仅 1 行；分支 feat/fork-port | —
- 2026-11-06 03:0x | §4.4 | 隔离配置 | 新建 `backend/.env`（CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174，.gitignore 已忽略不入库）；新建 `frontend/.npmrc`（npmmirror）；config.py 浏览器常量 9333→**9343**、9334→**9344**（见 blocked.md B-1） | 见下两条提交
- 2026-11-06 03:0x | §4.5 | 专用启停脚本 | 新建 `start-2.0.cmd`（**加 -NoBrowser：红线#4 夜间禁开任何浏览器进程**，其余按 §4.5 模板）、`stop-2.0.cmd`、`scripts/stop-2.0.ps1`（只按 runtime\*.json 的 process_id 记录停，永不扫端口；已核实 Save-ProcessRecord 写 `process_id` 字段） | 见下两条提交
- 2026-11-06 03:1x | §5 | 环境准备 | venv=Python 3.12.10；pip install requirements+dev 全绿（aliyun）；npm ci 全绿（npmmirror）；首次启动 8010 → `{"status":"ok","name":"ResumeForge","version":"2.0.0"}`，空库迁移 0001_baseline_v2 自动应用，Vite 5174 HTTP 200 | —
- 2026-11-06 03:2x | §2.2② 运行时落地 | browser_port=9343 | 上游测试钉死 9333（E4 禁改断言）→ 出厂常量回退 9333；对 2.0 实例 `PUT /api/apply/config` 写入 browser_port=9343（见 blocked.md B-1 更新）；tests/test_apply_api_config_browser.py 16 passed | —
- 2026-11-06 03:2x | N0 | 闸门骨架全绿 | `python -I scripts/fork_gate.py --phase 0` 原始输出：`PASS 2.0 基线单提交且未被改写 — upstream-v2.0.0 提交数=1，是 HEAD 祖先=True` / `PASS 版本是 2.0.0 — frontend/package.json version=2.0.0` / `PASS 迁移文件数 < 10 — 数量=1 ['0001_baseline_v2.py']` / `PASS 8010 健康检查 — 响应={'status': 'ok', 'name': 'ResumeForge', 'version': '2.0.0'}` / `PASS baseline 文档存在 — docs\fork-2.0-baseline.md` / `汇总：PASS=5 FAIL=0 SKIP=0` exit=0。baseline.md 为 N0 占位桩（见文件内说明），N1 替换为真表。基线 -k apply 实测：**415 passed, 1 failed**（失败即 B-1 所述 9333 断言，回退常量后复测 16 passed；全量 -k apply 复跑在 N3 前重测） | 本次提交

- 2026-11-06 03:3x | N1 | 落点校对完成 | EXISTS/需改造 29 条、MOVED 2 条、GONE 12 条、DROPPED 1 条（明细见 docs/fork-2.0-baseline.md）；GONE 本轮做：greeting_confirmed×2+ai_job_link+resume_generation_plan（N2）、greeting 闸门/分类/基准/队列打回+jd_relevance（N3）；GONE 范围外：BOSS 三修复（N5）、ai_jobs 全家（N6/N7）、resume_dedupe/import_portrait/技术栈开关（N8）；无卡待办：job_import/extension/platform/job_type_infer；上游已原生 8 类不要移植 | 本次提交

- 2026-11-06 04:0x | N2 | 迁移文件落地 | 新建 backend/migrations/versions/0002_fork_apply_greeting_plan_aijob.py（合并 1.x 0069/0070/0075；含历史行回填）；head 查询输出：heads=['0002_fork_apply_greeting_plan_aijob']（单头）；ast.parse OK；**未对任何库执行 apply**（N2 禁止项）；失败三列/分类列 2.0 已原生具备，不重复建 | 本次提交
