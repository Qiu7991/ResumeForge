# N8 简历侧移植任务板（分支 feat/resume-side）

> 计划：`简历通-2.0-N8简历侧移植计划.md`（§6 卡片 R0–R8）
> 基线分支：`feat/fork-port`（88ae5ac）→ 本轮分支 `feat/resume-side`
> 隔离口径：**线1（2.0 二开）**；线2（BossHunter / ai_jobs）零触碰。

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| R0 分支与三件套 + phase_9 | [x] | 26a878c / 闸门 PASS=2 FAIL=0 SKIP=10 | 从 feat/ai-jobs-sidecar 直接 `git switch feat/fork-port`，**未合并线2**；QueueItemEditor.test.tsx → BLOCKED-Q1 |
| R1 落点复核 | [x] | 0b80f73 / baseline.md | 去重·技术栈 GONE；覆盖清单 EXISTS；画像导入**目标无需改写** |
| R2 生成结果去重 | [x] | c9e87fa / 闸门 PASS=6 FAIL=0 SKIP=6 | 6 用例绿；E13 对照 6→5 / 2→1；砍掉 limit_resume（E15） |
| R3 技术栈开关（默认关） | [x] | 9076765 / 闸门 PASS=9 FAIL=0 SKIP=3 | 三条写路径（生成/手工/修订）+ 设置卡；默认 False |
| R4 覆盖清单补全 | [x] | 086381f / 自建分区 EXISTS 且 45 项测试全绿 | 内置分区差异 → DEFERRED-3（未移植，已说明边界） |
| R5 画像导入（改目标） | [x] | c7a9f1f / 闸门 **PASS=12 FAIL=0 SKIP=0** | 1.x 本写 claims（非 profile_facts）；三文件零改动 + `--dry-run` 别名；dry-run 已跑，**未 --apply** |
| R6 测试移植 | [x] | 闸门 PASS=12 FAIL=0 SKIP=0 / 定向 97 绿 | 1.x 9 用例零改动；另补 3 条 (容错/v2 文本项/API 往返) |
| R7 对抗审查 | [x] | b68cc88 / A 3/3 · **B 4/4** · C 3/3 · D 2/2 | B③ 打出真实泄漏并修掉（手写创建路径） |
| R8 全量闸门与报告 | [ ] | | |

## 红线自检（每卡复核）

- [x] 不合并 `feat/ai-jobs-sidecar` / `feat/ai-jobs-frontend`
- [x] 不碰 `backend/app/services/ai_jobs/**`
- [x] 不给 `application_routers.py` 加 ai_jobs 路由
- [x] 不给 `task_runner.py` 加 AI 互斥块
- [x] 只新增 `fork_gate.py` 的 `phase_9`，phase_0..phase_8 逐字未改
