# AI 求职前端移植任务板（会话 B · 分支 feat/ai-jobs-frontend）

> 恢复规则：新会话第一件事读本文件，找到第一个非 [x] 阶段继续，严禁重做已完成项。
> 分工：B 只做前端，独占 4 处注册表（zh/en .namespaces.ts、appRoutes.tsx、pages/registry.ts）。
> A（后端）在 D:\飞牛文件同步\工作\简历通-2.0 分支 feat/ai-jobs-sidecar 上并行，本仓不碰 backend/**。

| 阶段 | 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|---|
| B0 | 建分支与三件套 | [x] | 见 git log | 起点 88ae5ac 已确认 |
| B1 | 数据层（types + api 客户端） | [x] | 6de76f2 | typecheck 绿 |
| B2 | i18n 双包（144+144 key）+ namespaces 注册 | [x] | f4def85 | en 聚合点=en-US.ts（无 en-US.namespaces.ts），见 blocked 备注-1 |
| B3 | 只读组件 8 个（含 .test.tsx） | [x] | 见 git log | GreetingEditor 提前随批，7 测试绿 |
| B3.5 | B-6 页内收录 import_url 自动导入 | [x] | 4ec08a2 | 后端 POST /jobs/import-url 需 A 补（E10） |
| B4 | 写入组件 5 个（含 .test.tsx） | [ ] | | |
| B5 | 页面与路由（registry + appRoutes + 侧栏） | [ ] | | |
| B6 | 发送闸门前端体现 | [ ] | | 闸门关→按钮禁用 |
| B7 | 收尾（typecheck/lint/vitest/build + 晨报） | [ ] | | build 必须做 |

## 红线（摘要）
1. 只改本目录，1.x / BossHunter / 简历通-2.0（A）只读。
2. 禁改 backend/**。
3. 禁改 zh-CN.ts / en-US.ts 主文件（500 行硬预算），只改 .namespaces.ts。
4. 禁拷 BossHunter 任何前端产物/源码。
5. 禁硬编码文案，全部走 i18n。
6. 禁 git reset --hard / checkout . / clean -fd / stash drop / push。
7. 禁改测试断言。
8. 禁重命名/搬文件/顺手重构。
9. 发送按钮在闸门关闭时必须不可点；二次确认不可去掉。
