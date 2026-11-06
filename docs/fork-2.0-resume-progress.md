# N8 简历侧移植 · 执行日志（追加式）

> 分支 `feat/resume-side`，从 `feat/fork-port`（88ae5ac）切出。
> 每张卡：闸门输出 → 本节 → 单独提交 → taskboard。

## R0 分支校验与三件套

### 现场探测（开工）

```
$ git branch -vv
* feat/ai-jobs-sidecar e5fb384 docs(ai-jobs): 夜间执行报告（A0-A8 全绿收工）
  feat/fork-port       88ae5ac feat(2.0): BOSS 适配器移植（三处修复/Ego 浏览器/页内收录扩展挂载/单测）
  main                 d893243 chore: 上游 v2.0.0 基线 (53b813a7)

$ git status --porcelain
（空）
```

### 分支处置：**只 switch，不 merge**

计划 §1.3 要求把 A/B 两条分支合回主线；但本轮指令明确「线1 与线2 保持物理隔离，
不合并 AI 求职那两条分支」。所以 R0 收窄为：

```
$ git switch feat/fork-port
Switched to branch 'feat/fork-port'
$ git switch -c feat/resume-side
Switched to a new branch 'feat/resume-side'
```

N8 只动简历生成链路，不需要 ai_jobs 的任何代码；跳过合并不影响 R1–R8 的落点。

### 补齐缺失测试（计划 §1.4）

```
$ cp "/d/飞牛文件同步/工作/简历通/frontend/src/components/apply/queue/QueueItemEditor.test.tsx" \
     frontend/src/components/apply/queue/
$ git status --porcelain
?? frontend/src/components/apply/queue/QueueItemEditor.test.tsx
```

### 闸门基线（phase 0，R0 时刻）

```
===== Phase 0 =====
PASS 2.0 基线单提交且未被改写 — upstream-v2.0.0 提交数=1，是 HEAD 祖先=True
PASS 版本是 2.0.0 — frontend/package.json version=2.0.0
PASS 迁移文件数 < 10 — 数量=2 ['0001_baseline_v2.py', '0002_fork_apply_greeting_plan_aijob.py']
PASS 8010 健康检查 — 响应={'status': 'ok', 'name': 'ResumeForge', 'version': '2.0.0'}
PASS baseline 文档存在 — D:\飞牛文件同步\工作\简历通-2.0\docs\fork-2.0-baseline.md

汇总：PASS=5 FAIL=0 SKIP=0
```

### phase_9 设计口径（E10：建好之后不再改）

`phase_9` 沿用 phase_5 的既有约定：**未开工的能力输出 SKIP 并注明「R2 未移植」**，
已存在的能力必须满足。这样 R0 时刻闸门不会因为「N8 还没做」而变红，R8 时刻全项转 PASS。

重入保护：`phase_7` 的内部实现是 `for p in sorted(PHASES): PHASES[p]()`，
新增 9 之后会形成 7↔9 递归。`phase_9` 内置 `_IN_PHASE_9` 重入标志，
被 phase_7 回调时立即返回（不改 phase_7 一个字符）。

### phase_9 首次运行（R0 收口，L3）

```
===== Phase 9 =====
SKIP resume_dedupe.py 可导入 — R2 未移植（resume_dedupe.py 不存在）
SKIP 去重已接进生成链路 — R2 未移植
SKIP 去重与截断分离 — R2 未移植
SKIP 技术栈开关设置项 show_tech_stack 存在 — R3 未移植（schemas/generation_preferences.py 不存在）
SKIP 技术栈开关默认关 — R3 未移植
SKIP 技术栈两条路径都生效 — R3 未移植（resume_tech_stack.py 不存在）
PASS 覆盖清单补入能力存在或已记 GONE — resume_profile_append.py=True resume_coverage.py=True GONE登记=False
SKIP scripts/import_portrait.py 存在 — R5 未移植
SKIP 画像导入无 profile_facts 引用 — R5 未移植
SKIP portrait_extract.md 存在 — R5 未移植
SKIP N8 定向测试绿 — R2/R3/R5 测试均未移植
PASS 前 8 阶段复跑无 FAIL — 复跑 FAIL=0

汇总：PASS=2 FAIL=0 SKIP=10
```

前端 typecheck / build（计划 R0 步骤 3）：

```
$ npx tsc --noEmit -p tsconfig.json   → exit 0
$ npm run build                        → ✓ built in 989ms
```

### 偏差与处置：QueueItemEditor.test.tsx 未落地（BLOCKED-Q1）

计划 §1.4 要求 `cp` 1.x 的 `QueueItemEditor.test.tsx` 进 2.0。实测该测试三项全红，
原因**不是 2.0 有 bug**，而是它断言的两个功能属于 1.x 投递台的后续迭代，2.0 的
`QueueItemEditor.tsx`（127 行）没有它们：

| 测试断言 | 2.0 现状 |
|---|---|
| 「查看岗位 JD」展开拉 `/jobs/{id}` 并渲染 `.apply-queue-jd-body` | 组件里没有任何 JD 相关代码 |
| 「收起岗位 JD」缓存不重复请求 | 同上 |
| 项目下拉 + `focus_project` 传给 `previewGreeting` | 组件里没有项目下拉；`api/apply.ts:185` 只有类型字段 |

**处置**：删掉拷入的文件（保持 2.0 目录干净），登记 BLOCKED 后继续。
红线 §2.2#4 禁止改测试断言，而补这两个功能属于投递台（N3/N4 已验收范围，
§13 明确「不碰」）。见 `fork-2.0-resume-blocked.md`。
