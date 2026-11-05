# 2.0 移植进度日志（追加式）

> 格式：`时间 | 任务号 | 结果 | 证据/闸门原始输出 | commit`

---

- 2026-11-06 03:0x | §2.4 | 1.x 开工指纹 | `git rev-parse HEAD` = a09b63e43cac1edd957f84daf7794b18cdf0023e；`git status --porcelain | wc -l` = 0；分支 = fix/v2-single-model；`backend/data/resume_forge.db` = 160,989,184 字节（与计划 §1.1 一致）；8005 未监听（1.x 未运行） | —
- 2026-11-06 03:0x | §4.1 | 冻结 tag + 建仓 | `git tag fork-1x-frozen-20261106 HEAD` 成功（对 1.x 唯一写操作）；`git clone --depth 1 --branch v2.0.0 file:///D:/飞牛文件同步/工作/简历通 简历通-2.0` 成功（4266 文件）；rm .git 后 `git init -b main` + 单提交 + `git tag upstream-v2.0.0` + `git switch -c feat/fork-port` | d893243
- 2026-11-06 03:0x | §4.2 | audit 副本 | `git clone 简历通-2.0 简历通-2.0-audit` + `git switch -c feat/data-bridge` | —
- 2026-11-06 03:0x | §4.3 | 基线验证 | `frontend/package.json` version = **2.0.0**；`ls backend/migrations/versions | wc -l` = **1**（0001_baseline_v2.py，远小于 78）；`git log --oneline` 仅 1 行；分支 feat/fork-port | —
- 2026-11-06 03:0x | §4.4 | 隔离配置 | 新建 `backend/.env`（CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174，.gitignore 已忽略不入库）；新建 `frontend/.npmrc`（npmmirror）；config.py 浏览器常量 9333→**9343**、9334→**9344**（见 blocked.md B-1） | 见下两条提交
- 2026-11-06 03:0x | §4.5 | 专用启停脚本 | 新建 `start-2.0.cmd`（**加 -NoBrowser：红线#4 夜间禁开任何浏览器进程**，其余按 §4.5 模板）、`stop-2.0.cmd`、`scripts/stop-2.0.ps1`（只按 runtime\*.json 的 process_id 记录停，永不扫端口；已核实 Save-ProcessRecord 写 `process_id` 字段） | 见下两条提交
