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

## 2026-11-06 夜 B2 i18n 双包

- 移植 zh-CN.aiJobs.ts / en-US.aiJobs.ts（各 155 行），grep -c '"aiJobs\.' 两侧均 144 ✅
- 注册差异（E5 以代码为准）：2.0 **没有 en-US.namespaces.ts**，英文聚合点就是 en-US.ts（338 行，
  无 500 行预算约束，预算只针对 zh-CN.ts）→ 中文注册进 zh-CN.namespaces.ts（import+spread 各一行），
  英文注册进 en-US.ts（import+spread 各一行）。已记入 blocked.md 备查表与晨报注册表清单。
- npx vitest run src/i18n：14 文件 335 passed / 1 skipped（既有 skip）✅
- npm run typecheck ✅
- commit: f4def85

## 2026-11-06 夜 B3 只读组件

- 移植 8 个只读组件：ActionCards / ConnectionCard / JobDetailDrawer / JobResultsTable /
  PreflightPanel / RunHistoryTable / ScoreTracePanel / StatusBadge（逐字未改）+ 1.x 已有的
  ScoreTracePanel.test.tsx、StatusBadge.test.tsx
- 适配偏差：JobDetailDrawer 硬 import GreetingEditor（1.x 中属写入组件）——E3 禁止改写组件，
  故将 GreetingEditor.tsx 提前随 B3 移植（原样），B4 剩 4 个（ConfirmationTable/ReplyInbox/
  SettingsForm/TaskProgress）
- 依赖核对：1.x 与 2.0 antd 同为 ^6.6.8、icons ^6.3.4；t/useLocale/types/api 导入路径全部一致
- vitest src/components/ai-jobs：2 文件 7 passed ✅；typecheck ✅
