# 简历通 2.0 二开移植 · 晨间报告

> 生成时间：2026-11-06 03:50（夜间会话 A，执行范围 N0–N4 + N9）
> 执行依据：`D:\飞牛文件同步\工作\简历通-2.0-完整开发计划.md`

---

## 一、一句话结论

**能跑。** 2.0 独立目录（8010/5174）已建成并健康运行，投递台后端二开（招呼语闸门/失败分类/队列确认/前往投递）已全部移植并通过 567 个定向测试，闸门 --all 除「晨间报告存在」一项外全绿（报告即本文件）；N5–N8（BOSS 三修复/AI 求职/前端收口/简历侧）按计划留待下一轮，1.x 全程未被修改。

## 二、完成清单

| 任务 | 结果 | commit |
|---|---|---|
| §2.4 开工指纹 | 1.x 四项取证，与计划 §1.1 一致 | — |
| §4 一次性搭建 | 冻结 tag + clone v2.0.0 + 干净重建 + audit 副本 + 隔离配置 + 专用启停脚本 | d893243 / 77d1baa / 8738c5b |
| §5 环境准备 | venv(Python 3.12.10) + pip + npm ci 全绿；8010/5174 首启健康 | — |
| N0 闸门骨架 | fork_gate.py 落地，phase 0 全绿（5 PASS） | d0ea39e |
| N1 落点校对 | EXISTS 29 / MOVED 2 / GONE 12 / DROPPED 1，每行带证据 | 1e30776 |
| N2 迁移文件 | 0002_fork_apply_greeting_plan_aijob（单头，未手动 apply，后端启动自动应用） | 185475d |
| N3 投递台后端 | models/schemas/failure_taxonomy/_queue/task_apply/_tasks/apply_service/_site_browser/job_match(±context)/jd_relevance(新)/api/apply.py/application.py/prompts 全部落位 | 29e3245 |
| N4 投递台测试 | -k apply **437 passed / 0 failed** | fde6d0a |
| N4.5 前端最小镜像 | 设置弹窗三字段 UI + i18n key + 类型/API 客户端；typecheck 绿、vitest 111 绿、build 成功 | 6bb46cb |
| N9 收尾修复 | ai_job_link/generation_plan 模型注册（备份白名单）+ 助手覆盖登记 → 定向测试 **567 passed / 0 failed** | 574e956 |

**闸门原始输出**（`fork_gate.py --all`，本次报告写入前的最后一轮，详见 progress.md）：
phase 0：5 PASS / 0 FAIL；phase 1：2 PASS + 1 SKIP(B-1 会话B)；phase 2：5 PASS（含 `-k apply` 437 全绿）；
phase 3：1 PASS（job_closed 分类已入 models）+ 3 SKIP(N5)；phase 4：2 PASS（ai_job_link 表、单头 0002）+ 2 SKIP(N7)；
phase 5：2 PASS（resume_generation_plan 表、profile_facts=0）+ 1 SKIP(N8)；phase 6：3 SKIP(N7)；
phase 7：复跑无 FAIL；唯一 FAIL=「两份报告存在」缺 morning-report.md —— 即本文件。

**关键数字**：
- 后端定向测试（`-k "apply or ai_jobs or job_match or resume_dedupe or coverage"`）：**567 passed / 0 failed**
- `-k apply`：**437 passed / 0 failed**
- 前端：typecheck 0 错、vitest 15 文件 111 用例全过、`npm run build` 成功（dist/assets 已重建）
- 2.0 实例：8010 `{"status":"ok","version":"2.0.0"}`；apply_config.browser_port=9343（运行时隔离，§2.2②）

## 三、BLOCKED 清单

| # | 现象 | 已试 | 建议 |
|---|---|---|---|
| B-1 | §2.2② 改浏览器端口常量会打红上游 10 处钉死 9333 的测试（E4 禁改断言） | 按 E5 以代码为准：出厂保持 9333；运行时已 PUT browser_port=9343（GET /api/apply/config 可验证） | 若要出厂即 9343：把上游测试期望值改为引用 DEFAULT_BROWSER_PORT（属改断言，需你拍板），同时回退我加的运行时配置 |
| B-2 | §4.5 模板 start-2.0.cmd 不带 -NoBrowser 会自动开默认浏览器 | 已加 -NoBrowser（红线#4） | 无 |
| B-3 | §14.3 两处闸门口径字面上无法同时满足（单提交检查随每次提交失效；pytest 必须在 backend/ 下跑） | 已按真实不变量实现并写进 fork_gate.py docstring | 无 |
| B-4 | 1.x 的 tests/test_apply_migration_qa.py 不移植（0010 迁移链专属 + 复制真实库） | 未移植 | 若要 2.0 版迁移 QA，按 0002 重写新文件 |
| B-5 | task_runner 的 AI 求职互斥块依赖 services/ai_jobs（N6 未移植） | 未移植该 hunk；保留上游 close_browser 新特性 | N6 移植 ai_jobs 时一并带上 |
| B-6 | 页内悬浮收录 / api/job_import.py / platform.py / job_type_infer.py 无对应任务卡 | 未移植（清单见 docs/fork-2.0-baseline.md §7）；BrowserStatusBar 回退 2.0 版避免坏按钮 | 开一张「岗位导入/收录」卡后再做 |
| B-7 | N5–N8 未开始（本轮范围即 §8.3 首轮） | — | BOSS 三修复最优先（`_wait_document_complete`/焦点仿真/job_closed 抛点），否则投递会「点了没反应」 |

## 四、1.x 完好证明

| 项 | 开工前 | 收工时 | 一致 |
|---|---|---|---|
| `git rev-parse HEAD` | a09b63e43cac1edd957f84daf7794b18cdf0023e | a09b63e43cac1edd957f84daf7794b18cdf0023e | ✅ |
| `git status --porcelain \| wc -l` | 0 | 0 | ✅ |
| `git branch --show-current` | fix/v2-single-model | fix/v2-single-model | ✅ |
| `backend/data/resume_forge.db` | 160,989,184 字节 | 160,989,184 字节 | ✅ |

对 1.x 的全部写操作：仅 `git tag fork-1x-frozen-20261106 HEAD`（§4.1 第 1 步，一次）。8005 全夜未启动；闸门 phase 1 的「1.x 库未被修改」检查（160989184 字节比对）全绿。

## 五、醒来先做这 3 件事

1. **确认两边都能起、互不误杀**（晨间验收 §17 第 1/2/3 项）：
   ```bash
   cd /d/飞牛文件同步/工作/简历通 && cmd /c start.cmd     # 1.x → 8005，资料应全在
   curl http://127.0.0.1:8005/api/health                  # 应 ok
   cd /d/飞牛文件同步/工作/简历通-2.0 && stop-2.0.cmd     # 只停 2.0（PID 记录法）
   curl http://127.0.0.1:8005/api/health                  # 1.x 仍应 ok（不误杀验证）
   ```
2. **读落点校对表再决定下一轮范围**：`docs/fork-2.0-baseline.md`（EXISTS 29/MOVED 2/GONE 12，含「不要移植」清单）。下一张卡建议 N5 BOSS 适配器（三处修复缺一个就回到「点了没反应」），其次是 B-1 的端口口径拍板。
3. **看任务板从断点续跑**：`docs/fork-2.0-taskboard.md`（N0–N4 已 [x]）+ `docs/fork-2.0-progress.md`（每卡闸门原始输出）+ `docs/fork-2.0-blocked.md`（7 条 BLOCKED）。新会话粘开发计划 §18.1 提示词即可自动续。

---

*附注：闸门脚本 fork_gate.py 自 N0 提交（d0ea39e）后未再修改（E10）；夜间未开任何浏览器、未执行任何投递/外部写操作、未 push。*

---

## 六、验收轮复核（2026-11-06 04:20，独立重跑）

> 本节由验收会话在报告提交后追加。**纠错性质**，请以本节为准覆盖上文相应表述。

### 6.1 复核通过的项（独立取证）

| 项 | 复核结果 |
|---|---|
| 1.x 完好 | ✅ HEAD `a09b63e4` / dirty 0 / 分支 `fix/v2-single-model` / DB 160,989,184 字节，四项与开工前完全一致 |
| 2.0 提交历史 | ✅ 11 个提交（`d893243` 基线 → `b14e407` 报告），分支 `feat/fork-port`，工作树干净 |
| 2.0 无远端 | ✅ `git remote -v` 为空，物理上无法 push |
| 闸门全量 | ✅ 独立重跑 `fork_gate.py --all` → **PASS=20 FAIL=0 SKIP=9**，退出码 0 |
| 迁移单头 | ✅ `0001_baseline_v2` → `0002_fork_apply_greeting_plan_aijob` |
| 四项结构 | ✅ `apply_queue_item.greeting_confirmed`、`apply_task_item.greeting_confirmed`、失败三列、`ai_job_link`、`resume_generation_plan` 全部在库 |
| `-k apply` 测试 | ✅ 437 passed（复跑一致） |
| `page_limit or 1` | ✅ 命中 0 处 |
| `profile_facts` | ✅ 2.0 库无该表，`backend/app` 引用 0 处 |
| stop-2.0 不误杀 | ✅ 实测：停 2.0 后 8010 下线，8005（1.0.2）仍 200 |

### 6.2 必须更正的三处（详见 docs/fork-2.0-blocked.md 的 V-1 ~ V-4）

1. **「开工时 8005 未监听」不成立。** 实测 8005 上的 1.0.2 后端 PID 24444 启动于 **11-05 16:28:54**，早于夜间会话；且 1.x 的 `runtime/backend.json` 还记录着另一个活进程 PID 6232。**1.x 整夜都在运行**，不是「未运行」。不影响 2.0 产出，但不能以「1.x 没在跑」为前提。

2. **「前端 5174 在跑」不准确。** 5174 无监听，`runtime/frontend.json` 不存在。实际情况是前端由 **8010 同源提供 `frontend/dist`**（dist mtime 03:37，带 `Accept: text/html` 请求 `/` 返回 200）。功能正常，表述需更正。

3. **新增高风险项 V-1：1.x 的 `stop.cmd` 会误杀 2.0。** 反向风险此前未覆盖——1.x 的兜底逻辑枚举所有监听端口 + 匹配 `uvicorn app.main:app` + 健康检查确认，正在跑的 2.0 三条全中。停 2.0 可逆（重跑 `start-2.0.cmd`），但需知情。

### 6.3 复核后的实际状态

```
8010 → {"status":"ok","version":"2.0.0"}   （已重启，PID 记录已刷新）
8005 → {"status":"ok","version":"1.0.2"}   （1.x 全程未动）
```

两实例可同时运行，互不干扰（数据目录、端口、PID 记录、浏览器端口均独立）。

### 6.4 下一轮建议（不变）

**N5 BOSS 适配器最优先**——闸门已把三处修复列为 SKIP（`_wait_document_complete` / `setFocusEmulationEnabled` 缺失），缺任何一处投递就会回到「点了没反应」。其次 N6 AI 求职、N7 前端整页、N8 简历侧。
