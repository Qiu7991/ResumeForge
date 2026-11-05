# 2.0 移植任务板

> 恢复规则：新会话第一件事读本文件，找到第一个非 [x] 项继续，不重做已完成项。
> 最后更新：2026-11-06 05:45

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| N0 环境搭建 | [x] | 完成，见 d893243 前基线 + 77d1baa/8738c5b/本次提交 | 闸门 phase 0 全绿后提交 |
| N1 落点校对 | [x] | 完成（EXISTS 29 / MOVED 2 / GONE 12）| docs/fork-2.0-baseline.md 已替换占位桩 |
| N2 迁移文件 | [x] | 0002_fork_apply_greeting_plan_aijob（单头，ast OK，未 apply）| 增量：greeting_confirmed×2+resume_generation_plan+ai_job_link；失败列上游已有不重复建 |
| N3 投递台后端 | [x] | 完成（代码全落位；-k apply 30 失败根因=上游测试语义，N4 消除）| phase2 PASS=4 FAIL=1 |
| N4 投递台测试 | [x] | -k apply 437 passed / 0 failed | phase2 全绿；migration_qa 不适用记 blocked |
| N5 BOSS 适配器 | [x] | 三处修复全落位；-k boss 229 绿、-k apply 442 绿；phase 3 = 3 PASS 0 FAIL | Ego 分支+扩展挂载一并移植；前端 import_url 流程缺口记 B-6（N7） |
| N6 AI 求职后端 | [ ]（范围外） | ai_job_link 表+模型已就位（N2/N9） | 服务层/API/前端未移；task_runner 互斥块待带上 |
| N7 前端收口 | [ ]（范围外） | typecheck/vitest/build 已绿（最小镜像） | 队列面板确认 UI/ai-jobs 页面未移 |
| N8 简历侧二开 | [ ]（范围外） | resume_generation_plan 表+模型已就位 | dedupe/画像/技术栈开关未移 |
| N9 全量闸门 + 报告 | [x] | **PASS=20 FAIL=0 SKIP=9**；晨间报告已写 | 567 定向测试全绿；1.x 指纹前后一致 |

环境快照（N0 时点）：
- 后端 8010 运行中（runtime/backend.json PID 6908），空库迁移 0001_baseline_v2 已应用
- 前端 Vite 5174 运行中（runtime/frontend.json PID 21352）
- venv：backend/.venv（Python 3.12.10，requirements + dev 全装）
- 前端依赖：npm ci 完成（npmmirror）
- apply_config.browser_port 已置 9343（运行时配置，§2.2② 口径见 blocked.md B-1）
