# AI 求职前端移植 · 进度日志（会话 B）

追加式日志：时间 / 阶段 / 结果 / 关键输出 / commit。

---

## 2026-11-06 夜 B0 建分支与三件套

- 起点确认：分支 feat/fork-port，HEAD 88ae5ac（13 提交），工作树干净 ✅
- `git switch -c feat/ai-jobs-frontend` ✅
- 创建本三件套（taskboard / progress / blocked）
- 待提交：chore(ai-jobs-fe): 建分支与三件套

## 2026-11-06 夜 B1 数据层

- 前置：frontend/node_modules 缺失 → npm install（npmmirror，356 包，9s）
- 移植 frontend/src/types/aiJobs.ts（178 行，纯类型，含 isAiTaskActive）与
  frontend/src/api/aiJobs.ts（189 行，19 个端点，全部经后端 /api/ai-jobs 代理）
- 2.0 的 client.ts 同构：RequestBudgetKind 含 "task"，request<T> 签名一致，逐字移植零适配
- npm run typecheck ✅ 绿
- commit: 6de76f2
