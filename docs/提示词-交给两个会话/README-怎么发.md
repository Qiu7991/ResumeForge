# 提示词分发说明（照着发就行）

> 目录：`D:\飞牛文件同步\工作\简历通\docs\提示词-交给两个会话\`
> 一共 4 个文件、2 个会话、2 轮（先发 → 后发）。

---

## 两个会话怎么认

| 代号 | 会话标题长什么样 | 判断依据（它做过什么） |
|---|---|---|
| **v2 会话** | 标题带「简历通v2适配」 | 它建了 `fix/v2-single-model` 分支、做过 `resume_forge.db.pre-v2-normalize-*.bak` 备份、跑完了 Phase 0–3、写了 `docs/quality/fork-baseline.md` |
| **sidecar 会话** | 标题是「请读取 D:\飞牛文件同步\工作\AI求职集成-交接文档.md…」 | 它做完了 AI 求职 sidecar 的 P0–P4、写过 `f2f8177f` 那个红队修正提交 |

⚠️ 别搞反：**v2 会话是刚跑完 Phase 0–3 的那个**，不是最早写 sidecar 的那个。

---

## 四个文件对应的会话与顺序

```
v2 会话
  └─ 第 1 轮：A_先发_给v2会话_对抗性审查.md
        ↓ 等它报完告、P0 修完
  └─ 第 2 轮：B_后发_给v2会话_第二轮Phase456.md

sidecar 会话
  └─ 第 1 轮：C_先发_给sidecar会话_对齐进度.md
        ↓ 等它报完告
  └─ 第 2 轮：D_后发_给sidecar会话_第二轮清理.md
```

**两个会话可以同时开始**（A 和 C 可以同时发）。
B 和 D 是第二轮的，等第一轮报告回来再发。

---

## 逐个文件的发送时机

### A_先发_给v2会话_对抗性审查.md  →  v2 会话

**什么时候发**：现在就可以发（如果它已经跑完 Phase 0–3）。

**它会做什么**：只读审查自己的四个提交，七个攻击线索，每条都要写探针跑出真实输出。
只修 P0，不继续 Phase 4。

**它做完会给你**：`docs/quality/v2-adversarial-review.md` + P0 修复提交。

**你验收**：
```bat
cd /d D:\飞牛文件同步\工作\简历通
backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --phase 1
backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --phase 2
backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --phase 3
```
三条都应该全绿。

---

### C_先发_给sidecar会话_对齐进度.md  →  sidecar 会话

**什么时候发**：现在就可以发，和 A 同时。

**它会做什么**：**不改任何业务代码**。跑 sidecar 的 36 个测试确认健康、写
`docs/ai-jobs-v2-read-paths.md`（读取口清单）、补晨间验收清单、做 parity 核对。

**为什么不让它写代码**：工作树有 50 个未提交改动，一半是招呼语/投递台相关，
和 sidecar 文件挤在一起。现在动手会纠缠不清，回滚时无法区分谁的改动。

**它做完会给你**：36 passed 的确认 + `docs/ai-jobs-v2-read-paths.md`。

---

### B_后发_给v2会话_第二轮Phase456.md  →  v2 会话

**什么时候发**：A 跑完、P0 修完、phase 1/2/3 全绿之后。**不要提前发。**

**它会做什么**：
- Phase 4 静态守卫（`scripts/check_v2_boundary.py`，AST 实现）
- Phase 5 同形不变量测试 + 二开回归包
- Phase 6 合并 runbook
- 新增 `scripts/v2_status.py`（一条命令看状态）
- 有余力做预存量清理（D1 补 mock 消 20 条、D2 数据集状态隔离、D3 挑几条）

**它做完会给你**：`D:\飞牛文件同步\工作\简历通-round2-report.md` + 多个提交。

**你验收**：
```bat
backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --all
backend\.venv\Scripts\python.exe -I scripts\v2_status.py
```
第一个应该 21 通过 / 0 失败。第二个给你一份人话状态报告。

---

### D_后发_给sidecar会话_第二轮清理.md  →  sidecar 会话

**什么时候发**：C 跑完之后。可以和 B 同时。

**它会做什么**：
- **任务 F（排第一）**：审计那 50 个未提交改动，产出 `docs/quality/uncommitted-audit.md`
- 任务 E：修掉前端 6 处写死的站点名（`types/job.ts` / `JobTable.tsx` / `JobFilterBar.tsx`），
  让 `test_qa_browser_sites_adversarial.py` 从 1 failed 变 17 passed
- 任务 G：写 `docs/ai-jobs-v2-adaptation-plan.md`（v2 合并后怎么改 sidecar）
- 任务 H：写 `docs/ai-jobs-todo-inventory.md`（所有待办合成一张表）

**它做完会给你**：四份文档 + 站点名修复提交。

**为什么任务 F 排第一**：纯只读、零风险、而且你现在最需要它——
照着它 3 分钟就能把那 50 个未提交改动切开提交。

---

## 时间线（假设现在 02:00 开始）

| 时间 | v2 会话 | sidecar 会话 |
|---|---|---|
| 02:00–03:00 | A 对抗性审查 | C 对齐进度 |
| 03:00–03:30 | 修 P0 | （等） |
| 03:30–06:00 | B Phase 4/5/6 | D 审计 + 站点名修复 |
| 06:00–08:00 | B 预存量清理（有余力） | （等） |
| 08:00 | 两人都写报告、停下 | 同左 |

到 9 点你应该拿到：
- `v2_gate.py --all` 21/21 绿
- `scripts/v2_status.py` 能跑
- 4 份新文档（对抗审查 / 读取口清单 / 未提交审计 / sidecar 适配计划）
- 前端测试从 33 failed 降到 13 failed（补 mock 消 20 条）
- sidecar 站点名测试从 1 failed 变 17 passed

---

## 如果你只想做最低限度的事

只发 **A** 和 **C**。这两份都是"先发"的，不依赖任何前置条件，而且都不会弄坏东西。
拿到报告后再决定要不要发 B 和 D。

---

## 四个文件如果搞混了，看这个

| 文件名开头字母 | 给谁 | 第几轮 | 会不会改代码 |
|---|---|---|---|
| **A** | v2 会话 | 第 1 轮 | 只修 P0 |
| **B** | v2 会话 | 第 2 轮 | 会（Phase 4/5/6） |
| **C** | sidecar 会话 | 第 1 轮 | **不会** |
| **D** | sidecar 会话 | 第 2 轮 | 只改站点名那 3 个文件 |

记忆法：**A/B 给 v2，C/D 给 sidecar**（字母顺序对半切）。
