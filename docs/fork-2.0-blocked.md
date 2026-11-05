# 2.0 移植阻塞清单

> 格式：任务号 | 现象 | 已试方案 | 证据 | 建议

---

## 【验收轮追加，2026-11-06 04:15】逆向误杀风险 + 报告两处失实

### V-1（高）1.x 的 stop.cmd 会误杀正在运行的 2.0 后端

**现象**：§2.2① 只防了「2.0 的 stop 误杀 1.x」，**反向没防**。早上若对 1.x 运行 `stop.cmd`，它的兜底 `Stop-UnrecordedResumeForgeService` 会枚举全部监听端口、用 `uvicorn app.main:app` 匹配、再用健康检查确认「是 ResumeForge」——正在监听 8010 的 2.0 后端三条全满足，会被一起杀掉。

**实测证据**（2026-11-06 04:11）：
```
Get-NetTCPConnection -State Listen -LocalPort 8010 → OwningProcess = 23668
PID 23668 commandline = ...\简历通-2.0\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
PID 23668 parent = 27584（2.0 的 launcher，runtime/backend.json 记录的正是它）
curl 8010/api/health → {"status":"ok","name":"ResumeForge","version":"2.0.0"}
```
1.x 兜底逻辑见 `scripts/ResumeForge.Common.ps1:379-470`；健康判定 `Test-ResumeForgeHealthPayload` 只看 status/name，不看版本。

**影响**：停 2.0 是可逆的（重跑 start-2.0.cmd 即可），但会让「停 1.x」这个动作产生意料之外的副作用。

**建议处置（按代价排序）**：
1. 停 1.x 时显式走「只按 PID 记录」的路径：`powershell -File scripts\Stop-ResumeForge.ps1 -SkipBackend:$false` 不能避免兜底；更稳的是先 `curl 8010/api/health` 确认 2.0 状态，停完 1.x 后检查 8010 是否还活，不活就重启 2.0。
2. 或在 2.0 端口上做区分（例如 2.0 用 `--host 127.0.0.1 --port 8010` 并且改 `app_name`，让健康 payload 与 1.x 不同）——需改 2.0 代码，留待下一轮。
3. 晨间验收把这条列为必查项（见 §17 第 3 项）。

### V-2（中）晨间报告「开工时 8005 未监听」失实

**现象**：报告 §1 写「8005 未监听=1.x 未运行」。实测 1.x 后端整夜都在运行。

**证据**：
```
PID 24444（监听 8005，version 1.0.2，命令行为 简历通\backend\.venv\Scripts\python.exe -m uvicorn ... --port 8005）
StartTime = 2026/11/05 16:28:54   ← 早于夜间会话开始
1.x runtime/backend.json 记录 PID = 6232（另一个进程，同样活着且监听 8005）
```
即 1.x 上当时有两个后端进程并存，报告只看到「8005 未监听」这一项的判断依据不成立。

**影响**：不影响 2.0 的产出；但「1.x 整夜在跑」意味着夜间对 1.x 的任何写操作风险更高，不能以「它没在跑」为前提。

**已核实无事**：1.x 四项指纹与我开工前记录完全一致（HEAD a09b63e4 / dirty 0 / 分支 fix/v2-single-model / DB 160,989,184 字节），对 1.x 的写操作只有那一次 `git tag`。

### V-3（低）报告称「5174 前端在跑」，实测无监听

**证据**：`curl 5174` → 000（无连接）；`简历通-2.0/runtime/frontend.json` 不存在。8010 根路径带 `Accept: text/html` 返回 200（静态 dist 由后端同源提供，dist mtime 11-06 03:37）。功能上没问题，但「前端 5174 已起」的表述应改为「前端由 8010 同源提供 dist」。

### V-4（低）2.0 后端存在两个 uvicorn 进程

**证据**：PID 27584（launcher/记录值，不监听）→ 子进程 23668（实际监听 8010）。这是 uvicorn reload/父子的正常形态，但 `stop-2.0.ps1` 只按 27584 的 PID 停，`taskkill /T /F` 会连带 23668（已验证脚本 45-46 行无端口扫描，只按记录停）。**结论：stop-2.0.ps1 可用**，无需修改。

---

- B-1 | §2.2②（硬约束：2.0 浏览器默认端口改 9343/9344）与卡片 N5「禁止」栏注记（2.0 保持 9333 默认，改配置是运行时的事）存在文字冲突 | 按 §2 开头「这一节不是建议，是硬约束。违反任何一条，本轮作废」优先级执行：改了 `backend/app/config.py` 两个常量（DEFAULT_BROWSER_PORT=9343、DEFAULT_WEBFORM_BROWSER_PORT=9344）。夜间不起任何浏览器，无运行时影响 | config.py:43-50 | 如用户认可 N5 注记口径，回退该 2 行即可（git show 即见 diff）
- B-2 | §4.5 模板的 start-2.0.cmd 未带 -NoBrowser，而不带时 Start-ResumeForge.ps1 会在启动完自动 `Start-Process $pageUrl` 打开默认浏览器（scripts/ResumeForge.Process.ps1:421-429） | 加了 `-NoBrowser` 参数，其余与模板一致 | 红线#4「禁开任何浏览器进程」 | 无
- B-1（更新） | 实测发现 §2.2② 改 `DEFAULT_BROWSER_PORT=9343` 会打红上游测试 `tests/test_apply_api_config_browser.py::test_browser_status_reports_stopped`（断言 `port == 9333`，且 9333 共被 10 处上游测试钉死）；E4 禁改断言 | 按 E5「以代码为准」回退出厂常量为 9333（9344 无测试钉住，保留）；§2.2② 的意图改在**运行时配置**上达成：已对 2.0 实例 `PUT /api/apply/config` 写入 `browser_port=9343`（N5 卡注记原文「2.0 保持 9333 默认，改配置是运行时的事」正是此口径）。§10.1 KEPT 里「端口改 9343」由该运行时配置满足 | pytest 该文件 16 passed；GET /api/apply/config → browser_port=9343 | 若要把它做成出厂默认（改常量），需同步把上游测试断言期望值改为 DEFAULT_BROWSER_PORT 引用——属于改断言，留待用户拍板
- B-3 | 开发计划 §14.3 对闸门两处的字面口径无法同时满足：①「2.0 仓单提交 = rev-list HEAD == 1」在第一张卡提交后（E6）永久不成立，与「闸门必须能变绿」矛盾；②pytest 必须在 cwd=backend 下跑（conftest `from app import database` 依赖 `python -m pytest` 把 cwd 塞进 sys.path），而 N4 卡示例从仓库根跑 | ① 按 §3 的真实不变量实现为「upstream-v2.0.0 提交链数==1 且是 HEAD 祖先」；② 闸门 subprocess 用 cwd=BACKEND。两处都写进 fork_gate.py 模块 docstring | scripts/fork_gate.py 头注释 | 无

- B-4 | 1.x 的 tests/test_apply_migration_qa.py 不移植 | 该文件验证 1.x 的 0010 迁移在真实生产库副本上的往返兼容，硬编码 1.x 迁移链与 backend/data/resume_forge.db 副本；2.0 迁移链是 0001/0002 全新链，语义完全不适用（E5：以代码为准） | 文件头注释（覆盖 0010/0009） | 若用户要 2.0 版迁移 QA，需按 0002 重写新文件（本轮不做，非断言修改）
