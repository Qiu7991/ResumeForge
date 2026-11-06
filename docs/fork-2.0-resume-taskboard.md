# N8 简历侧移植任务板（分支 feat/resume-side）

> 计划：`简历通-2.0-N8简历侧移植计划.md`（§6 卡片 R0–R8）
> 基线分支：`feat/fork-port`（88ae5ac）→ 本轮分支 `feat/resume-side`
> 隔离口径：**线1（2.0 二开）**；线2（BossHunter / ai_jobs）零触碰。

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| R0 分支与三件套 + phase_9 | [x] | 26a878c / 闸门 PASS=2 FAIL=0 SKIP=10 | 从 feat/ai-jobs-sidecar 直接 `git switch feat/fork-port`，**未合并线2**；QueueItemEditor.test.tsx → BLOCKED-Q1 |
| R1 落点复核 | [ ] | | |
| R2 生成结果去重 | [ ] | | |
| R3 技术栈开关（默认关） | [ ] | | |
| R4 覆盖清单补全 | [ ] | | R1 预判 EXISTS（`resume_profile_append.py` + `/append-profile-entries`） |
| R5 画像导入（改目标） | [ ] | | |
| R6 测试移植 | [ ] | | |
| R7 对抗审查 | [ ] | | |
| R8 全量闸门与报告 | [ ] | | |

## 红线自检（每卡复核）

- [x] 不合并 `feat/ai-jobs-sidecar` / `feat/ai-jobs-frontend`
- [x] 不碰 `backend/app/services/ai_jobs/**`
- [x] 不给 `application_routers.py` 加 ai_jobs 路由
- [x] 不给 `task_runner.py` 加 AI 互斥块
- [x] 只新增 `fork_gate.py` 的 `phase_9`，phase_0..phase_8 逐字未改
