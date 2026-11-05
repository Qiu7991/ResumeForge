# AI 求职适配任务板（分支 feat/ai-jobs-sidecar）

> 恢复规则：新会话第一件事读本文件，找到第一个非 [x] 项继续。
> 会话 A（后端）在 简历通-2.0 工作；会话 B（前端）在 简历通-2.0-fe 独占 frontend/**。
> 开工基线：feat/fork-port @ 88ae5ac（13 提交），2026-11-06 夜。

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| A0 分支与闸门 phase 8 | [x] | 5cb7dc7；phase 8 基线 PASS=5 FAIL=7 SKIP=2 | 前端 3 项按约定 SKIP 待 B |
| A1 契约核对 | [x] | 4cd19df；22 路径全过、2 处不兼容留 A2 | contract.md 已产出 |
| A2 后端适配层 | [x] | 82f240a；L3 PASS=9 FAIL=3 SKIP=2 | 2 处契约改造 + 闸门反转已落地 |
| A3 后端测试 | [x] | bdb0985+本次；125P/1S（SK-1）| 2 处 2.0 缺失常量已补 |
| A4 路由注册与互斥 | [x] | L3 全绿；24P apply_task_runner | mutex+send_gate 13 用例新增 |
| A5 前端页面（只读部分） | [ ] | 由会话 B 承担 | A 不碰 frontend/** |
| A6 前端页面（写入部分） | [ ] | 由会话 B 承担 | A 不碰 frontend/** |
| A7 对抗审查 | [x] | F1-F4 全 PASS；A-D PASS，E DEFERRED 待 B | adversarial.md |
| A8 全量闸门与晨间报告 | [ ] | | |
