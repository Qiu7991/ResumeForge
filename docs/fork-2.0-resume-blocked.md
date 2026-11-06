# N8 简历侧移植 · 阻塞清单

> 只登记「查清了但做不下去」的项。查不清的写进 progress。
> 状态口径：`[BLOCKED]` 未做；`[DEFERRED]` 按计划本就留人工。

## BLOCKED-Q1：1.x 的 `QueueItemEditor.test.tsx` 无法在 2.0 落地

- **计划位置**：§1.4 与卡片 R0 步骤 4「cp 1.x 的 QueueItemEditor.test.tsx」
- **现象**：拷入后 3 个用例全红（`5 passed / 3 failed`）。
- **根因**：不是测试写得不对，也不是 2.0 有 bug，而是该测试断言的两个功能只在 1.x
  投递台的后续迭代里存在，2.0 的 `QueueItemEditor.tsx`（127 行）没有：
  | 测试断言 | 2.0 现状（证据） |
  |---|---|
  | 「查看岗位 JD」→ 拉 `/jobs/{id}` → 渲染 `.apply-queue-jd-body` | `grep -rn "apply-queue-jd\|getJob" frontend/src/components/apply/queue/QueueItemEditor.tsx` 无命中 |
  | 「收起岗位 JD」不重复请求 | 同上 |
  | 项目下拉 → `previewGreeting` 带 `focus_project` | 组件无项目下拉；`frontend/src/api/apply.ts:185` 只有 `focus_project?: string` 类型位 |
- **为什么不修**：红线 §2.2#4 禁止改测试断言；补这两个功能属于投递台（N3/N4 已验收，
  §13 明确「不碰」）。
- **处置**：撤回拷入文件，2.0 目录保持干净。**不影响 N8 任何一张卡**（该测试与简历
  生成侧无关）。
- **留人工**：若要把这两个编辑器增强一起移植，另开一张投递台卡，从 1.x 的
  `QueueItemEditor.tsx`（311 行）整文件移植 + 补 18 个 i18n key。

## DEFERRED-1：画像导入的 `--apply`

真数据迁移需老板在场确认（计划 §9.4、§R5 禁止项）。本轮只做 `--dry-run`。

## DEFERRED-2：去重的相似度阈值

沿用 1.x 的确定性规则（身份键完全相同才合并），不做阈值调优（计划 §9.4）。
