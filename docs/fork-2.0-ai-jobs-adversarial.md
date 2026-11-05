# AI 求职适配层 · 对抗审查报告（A7）

> 2026-11-06 夜 · 会话 A。审查对象：feat/ai-jobs-sidecar 分支的 ai_jobs 适配层。
> 方法：攻击 → 观察 → 判定 → 证据（命令输出 / 测试名 / 文件:行号）。不改被测代码。
> **结论：F1–F4 全部 PASS；通用五类 A/B/C/D/E：A/B/C PASS（测试+探针），D PASS（分支级回退+定向测试），E DEFERRED（前端由会话 B 产出，晨间合并后补验）。**

## F 类（AI 特有安全边界，必须全 PASS）

### F1 凭据不落库 — **PASS**

**攻击**：`grep -rn -i "api_key|token|cookie" backend/app/services/ai_jobs/ backend/app/schemas/ai_jobs.py`，逐条定性每个命中是否构成持久化路径。

**观察到**（全部命中，共 12 处有效行）：

| 位置 | 内容 | 定性 |
|---|---|---|
| schemas/ai_jobs.py:4、settings.py:5、config_sync.py:6 | 「不存任何 Key、Token、Cookie」等安全声明 | 注释 |
| config_sync.py:34,44 | 读简历通 LLM Profile 的 api_key → 组进**发往引擎** `POST /api/config` 的 payload | 引擎侧凭据（S3 口径：引擎落到它自己的私有凭据文件）；**不是**简历通落库路径 |
| config_sync.py:47-49 | max_tokens | 非凭据 |
| status.py:103,105 | 只用 api_key 的**有无**做预检布尔与提示文案（「缺少 API Key」/会话密钥警告），不返回 Key 值 | 只读探测 |
| manager.py:58,106,132,145,223 | `owner_token`：进程自生成 uuid（仅用于「只停自己启动的 sidecar」所有权判定），存 DATA_DIR/ai-jobs/<ds>/engine/sidecar.json | 本地运行态，非外部凭据 |

**决定性证据**：持久化唯一路径 `settings.save_ai_jobs_config` 整对象序列化 `AiJobsConfig`，其全部字段为 `enabled/engine_python/engine_repo/engine_port/proxy_port/browser_port/auto_start/use_resumeforge_llm/auto_import_ready_jobs/last_dataset_id/engine_version`（schemas/ai_jobs.py:18-35 实测 grep）——**无任何凭据字段**。phase_8 检查 8 同步 PASS。

### F2 发送闸门默认关 — **PASS**

**攻击**：不设置 `AI_JOBS_ALLOW_SEND`，直接 `POST /api/ai-jobs/deliver`；并穷尽 `/api/workbench/deliver` 的调用路径。

**观察到**：
- 调用路径唯一性：`grep -rn "workbench/deliver" backend/app` 仅 `services/ai_jobs/delivery.py:78` 一处真实调用（另一处是注释）；phase_8 检查 4 证明 ai_jobs 之外无引擎端口直连。
- API 层闸：`api/ai_jobs.py` deliver 端点先查 `delivery.send_gate_open()` → 403「发送闸门未打开：设置环境变量 AI_JOBS_ALLOW_SEND=1…（默认关）」。
- 行为证据（测试，全部绿）：
  - `test_ai_jobs_send_gate.py::test_api_deliver_rejected_when_gate_closed` — 未设置 → 403 且 detail 含 AI_JOBS_ALLOW_SEND；
  - `test_gate_default_closed` / `test_gate_explicit_truthy_opens`（1/true/YES/on）/ `test_gate_non_truthy_stays_closed`（0/""/false/no/random）；
  - `test_api_deliver_allowed_when_gate_explicitly_opened` — 显式打开才走通。
- 本轮执行环境：`AI_JOBS_ALLOW_SEND` 全程未设置（红线 4）。
- 服务层仍有 `confirm=True` + 待确认白名单 + 双 busy 检查（delivery.py:60-75），闸门打开后仍需二次确认。

### F3 版本窗口 — **PASS**

**攻击**：假引擎分别返回 `2.3.9` 与 `3.0.0`。

**观察到**（现场探针，MockTransport 实测输出）：
```
version='2.3.9'  reachable=True version_ok=False reason='BossHunter 版本 2.3.9 不在支持范围（2.4.x），请升级或降级引擎后重试'
version='3.0.0'  reachable=True version_ok=False reason='BossHunter 版本 3.0.0 不在支持范围（2.4.x），请升级或降级引擎后重试'
version='2.4.1'  reachable=True version_ok=True  reason=''
```
- 任务启动同样被挡：`tasks._require_sidecar`（tasks.py:90-91）在 `version_ok=False` 时抛 422（health.reason 原文），**不降级硬跑**。
- 边界参数化测试：`test_version_in_window`（2.4.0/2.4.7/v2.9.3/2.4 → True；2.3.9/3.0.0/""/abc → False）、`test_health_version_mismatch_marks_not_ok`，全绿。

### F4 许可证边界 — **PASS**

**攻击**：`grep -ril "polyform|bosshunter" backend/ frontend/`（--include py/ts/tsx）+ 引擎源码文件名抽查。

**观察到**：
- 内容命中 16 个文件，逐类定性：全部为**注释/docstring/字符串常量/HTTP 路径**（如 application_routers.py:105 注册注释、ai_job_link.py 模型 docstring、manager.py:68 `"bosshunter.main"` 是以子进程拉起引擎的 CLI 模块名字符串、test_assistant_coverage.py:55 的覆盖豁免说明文案、0002 迁移的表注释）。
- `import bosshunter` / `from bosshunter`：**0 命中**（phase_8 检查 7 的 import_hits=无）。
- 引擎源码文件名（server.py 等）在 backend/app 下：**0 命中**（find 实测）；无 LICENSE/COPYING 命中。
- polyform 6 处命中全部位于 `.venv` 第三方 SPDX 许可证目录（packaging/pip 的 `_spdx.py` 数据），非仓库源码、非引擎许可证文本。
- A3 期间的合规动作：`tests/fixtures/fake_bosshunter.py` 系 1.x 自建测试桩（Apache-2.0 头、纯 MockTransport/HTTPServer 桩、零引擎代码），因文件名含 "bosshunter" 被冻结版 phase_8 检查 7 判 FAIL（E10 不许改闸门）→ 合规改名 `fake_sidecar.py` + 3 处引用更新（git mv 保历史，见 blocked.md NOTE-2）。

## 通用五类

### A 数据丢失 — **PASS**
- 引擎岗位脏数据：`test_missing_title_is_skipped`（缺 title 行跳过不崩）；`import_engine_jobs` 对每行 strip/类型化（job_sync.py:112-134）。
- 超长招呼语：301 字 → 400（`test_ai_jobs_greeting.py::"好"*301` 用例，绿）；引擎侧同限 300（server.py:2114-2115 双保险）。
- 配置脏数据（现场探针）：`get_ai_jobs_config` 对损坏 JSON / 类型错乱 JSON 均重置默认值且不抛错：
  ```
  损坏JSON → AiJobsConfig engine_port= 8687 （默认值，未抛错）
  类型错乱 → AiJobsConfig engine_port= 8687
  ```
- 源数据零改动：适配层对引擎库只读（唯一写请求是 greeting/greeting-selection/deliver/reject 显式动作），简历通侧只写自己的 `ai_job_link`/`job`/`app_setting`。

### B 双重真相 — **PASS**
- 引擎状态 → 简历通状态的唯一映射点：`job_sync._status_for_job`；`test_sent_status_marks_job_applied`（引擎 sent → 简历通 JOB_STATUS_APPLIED，绿）+ `links[0].engine_status == "sent"` 快照断言。
- 已发送回写求职进度的幂等：`test_sync_is_idempotent`、`test_sync_ignores_non_delivered_statuses`、`test_sync_keeps_later_status`、`test_workbench_transition_syncs_tracker_once`（全绿）。
- 前端展示一致性归 E 类（会话 B 未合并，DEFERRED）。

### C 静默失败 — **PASS**
- 引擎未运行：`test_health_unreachable_gives_not_running_hint`（reason 含「sidecar 未运行」）。
- 非 JSON 响应：`test_non_json_response_is_bad_response`。
- 连接错误归一化：`test_connect_error_maps_to_not_running`；HTTP 错误归一化 `{message, code}`：`test_http_error_uses_sidecar_error_field`。
- 重试纪律：`test_get_retries_once_on_5xx`（GET 单次重试）、**`test_post_never_retries`**（POST 绝不重试——防重复投递）。
- 超时分档（计划 §9 逐字）：`_TIMEOUTS = {"health": 2.0, "read": 5.0, "task": 15.0, "long": 30.0}`（client.py:26）；`attempts = 2 if method == "GET" else 1`（client.py:80）。

### D 回退 — **PASS（分支级）**
- 回退路径 = `git switch feat/fork-port`（AI 求职整支不生效，投递台回到已验收态）——分支隔离即回退，不提供「删目录级」回退。
- 本分支上投递台回归证据：`-k apply_task_runner` 24 passed；A8 将再跑全量 `-k "ai_jobs or apply"`。
- 如实记录的耦合点：`apply/task_runner.py` start() 的 AI 互斥块是**懒导入**（`from ..ai_jobs.gate import try_clear_stale_ai_busy` 在锁内调用）——若只删 ai_jobs 目录而保留该行，apply 启动会 ImportError；这不是受支持的回退方式（受支持的是整支回退），仅作知会。

### E 可见变化 — **DEFERRED**
- 前端 AiJobsPage/17 组件/i18n 由会话 B（简历通-2.0-fe，分支 feat/ai-jobs-frontend）产出，晨间合并后才能做「同引擎状态两版展示一致」的比对；本报告不替 B 背书。合并后复验项已列入晨间报告「醒来先做」。

## 附：本轮未做（红线内不做）
- 未启动真实引擎/浏览器、未调用真实 `/api/workbench/deliver`（E11/S2）；所有行为证据来自进程内 MockTransport 桩与单元/集成测试。
