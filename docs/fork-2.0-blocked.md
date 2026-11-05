# 2.0 移植阻塞清单

> 格式：任务号 | 现象 | 已试方案 | 证据 | 建议

---

- B-1 | §2.2②（硬约束：2.0 浏览器默认端口改 9343/9344）与卡片 N5「禁止」栏注记（2.0 保持 9333 默认，改配置是运行时的事）存在文字冲突 | 按 §2 开头「这一节不是建议，是硬约束。违反任何一条，本轮作废」优先级执行：改了 `backend/app/config.py` 两个常量（DEFAULT_BROWSER_PORT=9343、DEFAULT_WEBFORM_BROWSER_PORT=9344）。夜间不起任何浏览器，无运行时影响 | config.py:43-50 | 如用户认可 N5 注记口径，回退该 2 行即可（git show 即见 diff）
- B-2 | §4.5 模板的 start-2.0.cmd 未带 -NoBrowser，而不带时 Start-ResumeForge.ps1 会在启动完自动 `Start-Process $pageUrl` 打开默认浏览器（scripts/ResumeForge.Process.ps1:421-429） | 加了 `-NoBrowser` 参数，其余与模板一致 | 红线#4「禁开任何浏览器进程」 | 无
