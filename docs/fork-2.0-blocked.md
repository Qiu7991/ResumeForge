# 2.0 移植阻塞清单

> 格式：任务号 | 现象 | 已试方案 | 证据 | 建议

---

- B-1 | §2.2②（硬约束：2.0 浏览器默认端口改 9343/9344）与卡片 N5「禁止」栏注记（2.0 保持 9333 默认，改配置是运行时的事）存在文字冲突 | 按 §2 开头「这一节不是建议，是硬约束。违反任何一条，本轮作废」优先级执行：改了 `backend/app/config.py` 两个常量（DEFAULT_BROWSER_PORT=9343、DEFAULT_WEBFORM_BROWSER_PORT=9344）。夜间不起任何浏览器，无运行时影响 | config.py:43-50 | 如用户认可 N5 注记口径，回退该 2 行即可（git show 即见 diff）
- B-2 | §4.5 模板的 start-2.0.cmd 未带 -NoBrowser，而不带时 Start-ResumeForge.ps1 会在启动完自动 `Start-Process $pageUrl` 打开默认浏览器（scripts/ResumeForge.Process.ps1:421-429） | 加了 `-NoBrowser` 参数，其余与模板一致 | 红线#4「禁开任何浏览器进程」 | 无
- B-1（更新） | 实测发现 §2.2② 改 `DEFAULT_BROWSER_PORT=9343` 会打红上游测试 `tests/test_apply_api_config_browser.py::test_browser_status_reports_stopped`（断言 `port == 9333`，且 9333 共被 10 处上游测试钉死）；E4 禁改断言 | 按 E5「以代码为准」回退出厂常量为 9333（9344 无测试钉住，保留）；§2.2② 的意图改在**运行时配置**上达成：已对 2.0 实例 `PUT /api/apply/config` 写入 `browser_port=9343`（N5 卡注记原文「2.0 保持 9333 默认，改配置是运行时的事」正是此口径）。§10.1 KEPT 里「端口改 9343」由该运行时配置满足 | pytest 该文件 16 passed；GET /api/apply/config → browser_port=9343 | 若要把它做成出厂默认（改常量），需同步把上游测试断言期望值改为 DEFAULT_BROWSER_PORT 引用——属于改断言，留待用户拍板
- B-3 | 开发计划 §14.3 对闸门两处的字面口径无法同时满足：①「2.0 仓单提交 = rev-list HEAD == 1」在第一张卡提交后（E6）永久不成立，与「闸门必须能变绿」矛盾；②pytest 必须在 cwd=backend 下跑（conftest `from app import database` 依赖 `python -m pytest` 把 cwd 塞进 sys.path），而 N4 卡示例从仓库根跑 | ① 按 §3 的真实不变量实现为「upstream-v2.0.0 提交链数==1 且是 HEAD 祖先」；② 闸门 subprocess 用 cwd=BACKEND。两处都写进 fork_gate.py 模块 docstring | scripts/fork_gate.py 头注释 | 无
