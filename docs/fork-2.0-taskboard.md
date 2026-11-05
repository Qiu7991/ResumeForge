# 2.0 移植任务板

> 恢复规则：新会话第一件事读本文件，找到第一个非 [x] 项继续，不重做已完成项。
> 最后更新：2026-11-06 03:00

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| N0 环境搭建 | [x] | 完成，见 d893243 前基线 + 77d1baa/8738c5b/本次提交 | 闸门 phase 0 全绿后提交 |
| N1 落点校对 | [ ] | | 只读，产出 fork-2.0-baseline.md |
| N2 迁移文件 | [ ] | | 只写文件不 apply |
| N3 投递台后端 | [ ] | | greeting_confirmed/失败分类/闸门/队列 |
| N4 投递台测试 | [ ] | | 移植 5 个测试文件 |
| N5 BOSS 适配器 | [ ] | | 本轮范围外（§8.3） |
| N6 AI 求职后端 | [ ] | | 本轮范围外（§8.3） |
| N7 前端收口 | [ ] | | 本轮范围外（§8.3） |
| N8 简历侧二开 | [ ] | | 本轮范围外（§8.3） |
| N9 全量闸门 + 报告 | [ ] | | 收尾必做 |

环境快照（N0 时点）：
- 后端 8010 运行中（runtime/backend.json PID 6908），空库迁移 0001_baseline_v2 已应用
- 前端 Vite 5174 运行中（runtime/frontend.json PID 21352）
- venv：backend/.venv（Python 3.12.10，requirements + dev 全装）
- 前端依赖：npm ci 完成（npmmirror）
- apply_config.browser_port 已置 9343（运行时配置，§2.2② 口径见 blocked.md B-1）
