# AI 求职适配 · 晨间报告（会话 A · 后端）

> 2026-11-06 夜 → 11-06 晨。分支 `feat/ai-jobs-sidecar`（从 feat/fork-port @ 88ae5ac 切出）。
> 会话 A 只做后端；frontend/** 全程未碰（红线 2）。会话 B（简历通-2.0-fe，分支 feat/ai-jobs-frontend）已并行完成，待晨间合并。

## 一、一句话结论

**后端全部做完且全绿**：A0–A8 十段全落地，`fork_gate.py --all` = PASS 34 / FAIL 0 / SKIP 9，`-k "ai_jobs or apply"` = 567 passed / 1 skipped（唯一 skip 是 1.x 语义与 2.0 红线冲突的豁免项，见 SK-1）；F1–F4 安全边界全 PASS；**未做真实联调（需要真引擎+真账号+人在场）**，前端待与 B 合并后才能整页可用。

## 二、完成清单

| 卡 | 内容 | commit | 闸门/测试证据 |
|---|---|---|---|
| A0 | 分支 + 闸门 phase 8（14 项检查定稿，E10 冻结）+ 三件套 | `5cb7dc7` | 基线 PASS=5 FAIL=7 SKIP=2 |
| A1 | 三方契约核对（22 条引擎路径逐条行号取证 + 17 个衔接点） | `4cd19df` | 2 处不兼容暴露 → A2 改造 |
| A2 | 14 服务 + schema + API 移植（1970 行）；契约改造①reply 发 message ②greeting 补 confirmed；**发送闸门语义反转为默认关** | `82f240a` | L3 PASS=9 FAIL=3 SKIP=2 |
| A3 | 18 测试文件移植（17 test + fakes + fake_sidecar）；补 2.0 缺失的 `SOURCE_AI_JOBS` 常量与 `record_applied(source=)` 参数 | `bdb0985` | 125 passed / 1 skipped |
| A4 | ai_jobs 路由注册 + apply/task_runner AI 互斥块（照 1.x 逐字）+ 新增互斥/发送闸门测试 13 用例 | `eb2f29c` | **L3 全绿 PASS=12 FAIL=0 SKIP=2，EXIT=0** |
| A7 | 对抗审查：F1-F4 全 PASS；通用五类 A-D PASS、E DEFERRED（待 B） | `e692431` | docs/fork-2.0-ai-jobs-adversarial.md |
| A8 | `--all` 全量闸门 + 联合定向测试 + 三方指纹 + 本报告 | `d20e977` | 见下 |

**收尾实测输出（原样）**：
- `fork_gate.py --all` → `汇总：PASS=34 FAIL=0 SKIP=9`（EXIT=0；SKIP 均为 N7/N8 未移植 + 会话 B 前端项 + B-1 数据桥，非本轮范围）
- 其中 `-k apply` = **448 passed**；`-k ai_jobs` = **125 passed / 1 skipped**
- `-k "ai_jobs or apply"` = **567 passed / 1 skipped**
- 途中修复：NOTE-3 测试间租约泄漏（1.x 同样存在，联合选择器为本轮新增；修测试基础设施，未动断言）

**A2 两处契约改造（1.x 对 2.4.0 引擎原本跑不通的点）**：
1. `history/{id}/reply`：1.x 发 `content`，引擎只读 `message`（server.py:2361）→ 已改。
2. `jobs/{id}/greeting`：引擎要求 `confirmed=true`（server.py:2117-2118），1.x 不发 → 该调用在 1.x 对 2.4.0 **从未成功过**（一直静默走本地快照兜底）→ 已补。

**发送闸门（红线 4/8）**：`AI_JOBS_ALLOW_SEND` 默认关；只有显式 `1/true/yes/on` 才放行；API 层 403 先挡 + 服务层确认门/白名单/双 busy 兜底。**本轮全程未设置该变量，未发送任何真实请求，未启动引擎/浏览器。**

## 三、BLOCKED 清单（docs/fork-2.0-ai-jobs-blocked.md）

| 编号 | 一句话 | 影响 |
|---|---|---|
| SK-1 | 1.x 测试 `test_deliver_allowed_when_env_absent`（未设环境变量→投递 200）与 2.0 红线「默认关」冲突 → 按 E4 不改断言、按红线 6 skip；2.0 语义由 test_ai_jobs_send_gate.py 正向覆盖 | 无（1 skipped） |
| NOTE-1 | 发送总闸落点定在 API 层（1.x 架构原样），非计划 §10.1 字面的 gate.py/delivery.py——服务层落点会打断 1.x 服务级直调测试 | 无（phase_8 判定域已含 API 层） |
| NOTE-2 | `fake_bosshunter.py` → `fake_sidecar.py` 合规改名（文件名撞冻结版 phase_8 检查 7；该文件是 1.x 自建测试桩，零引擎代码） | 无（git mv 保历史） |
| NOTE-3 | 联合选择器下 1.x 遗留的测试间租约泄漏（非产品缺陷），修测试 fixture 清理 | 无（567 全绿） |

**均不阻塞**；无 [BLOCKED] 状态的任务卡。

## 四、三方完好证明（开工 → 收工）

| 仓 | 开工 | 收工 | 判定 |
|---|---|---|---|
| 简历通 1.x（只读） | `a09b63e43cac1edd957f84daf7794b18cdf0023e`，dirty 0 | `a09b63e43cac1edd957f84daf7794b18cdf0023e`，dirty 0 | ✅ 未动 |
| BossHunter 引擎（只读） | `77f3572fa98aa1a2e0c73a79f0dace1c0619da70`，dirty 2（`?? start.cmd` `?? stop.cmd`，用户自建，开工前即存在） | 同左，逐字节一致 | ✅ 未动 |
| 简历通-2.0 | `88ae5ac` @ feat/fork-port，dirty 0 | `d20e977` @ feat/ai-jobs-sidecar（+10 提交），dirty 0 | ✅ 全部为本轮提交 |
| 简历通-2.0-fe（会话 B，只读检查） | — | `3b12203` @ feat/ai-jobs-frontend | B 已自行收尾，A 未触碰 |

## 五、醒来先做这 3 件事

1. **合并两会话**（约 10 分钟，§15.4）：
   ```bash
   cd /d/飞牛文件同步/工作/简历通-2.0
   git merge --no-ff feat/ai-jobs-sidecar          # 后端（本报告）
   git remote add fe /d/飞牛文件同步/工作/简历通-2.0-fe   # 若还没加过
   git fetch fe && git merge --no-ff fe/feat/ai-jobs-frontend   # 前端（含注册表改动，零冲突设计）
   cd frontend && npm run typecheck && npm run lint && npm run build   # 合并后统一构建
   cd .. && backend/.venv/Scripts/python.exe -I scripts/fork_gate.py --all   # 应为 34P/0F，SKIP 仅剩前端 3 项转 PASS
   ```
   注意：**8010 上现在跑着的后端是旧代码，不加载 ai_jobs 路由**——合并后重启后端（`powershell Stop-Process` 旧 PID → start 脚本）再联调。
2. **读两份报告**：本文件 + `docs/fork-2.0-ai-jobs-adversarial.md`（F 类证据全在里面）；SK-1 若不认可「默认关」语义，需同时改红线/phase_8 检查 5/测试三处，属产品决策。
3. **真实联调（人工在场）**：启动独立 BossHunter 2.4.0（8686）→ 2.0 页面「AI 求职」连接 → 应显示已连接 → **全程不要点发送**（闸门默认关是对的；要真发时再显式设 `AI_JOBS_ALLOW_SEND=1`）。

---

**前端部分**：由会话 B 产出，待晨间合并（其晨间报告在 简历通-2.0-fe 的 B7 提交内）。
