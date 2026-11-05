# AI 求职适配 · 三方契约核对表（A1）

> 2026-11-06 夜。三方：① 1.x 适配层（简历通 @ a09b63e4）② 引擎 2.4.0（BossHunter @ 77f3572f）
> ③ 2.0 目标（简历通-2.0 @ feat/ai-jobs-sidecar）。只读核对，每行有证据。
> **核对结论：22 条引擎路径全部存在；2 处字段不兼容（必须改造，留给 A2）；衔接点全部就位。**

## 表 1 · 引擎路径核对（1.x 调用 → 2.4.0 路由 → 字段）

| # | 引擎路径（方法） | 1.x 用途（调用文件） | 2.4.0 存在性 | 字段兼容性 |
|---|---|---|---|---|
| 1 | `GET /api/health` | 连接三态+版本窗口（client.py） | server.py:1063 ✅ | 响应含 version，窗口由适配层算 ✅ |
| 2 | `GET /api/config` | config_sync 读引擎配置 | server.py:2551 ✅ | 读整个 dict ✅ |
| 3 | `POST /api/config` | config_sync 写回（合并 ai 段） | server.py:2560 ✅ | 引擎读 request.json 整体 ✅。**计划附录 B 写「GET/PUT」是笔误，实为 GET/POST**，1.x 用的就是 POST ✅ |
| 4 | `GET /api/jobs`（params: deleted, limit） | job_sync.py:169 / delivery_sync.py:45 拉岗位池 | server.py:1101 ✅ | 引擎读 deleted/limit/offset，1.x 传 deleted=active&limit ✅ |
| 5 | `GET /api/jobs/{id}` | greeting.py 单岗位详情 | server.py:2152 ✅ | 只读 ✅ |
| 6 | `GET /api/jobs/{id}/score-trace` | api/ai_jobs.py 五维评分详情 | server.py:2188 ✅ | 只读 ✅ |
| 7 | `POST /api/jobs/{id}/greeting` | greeting.py:68 写回招呼语 | server.py:2108 ✅ | ⚠️ **不兼容 ②**：引擎要求 `confirmed is True`（server.py:2117-2118 缺失即 400），1.x 只发 `{"greeting": text}` → 见「必须改造」 |
| 8 | `POST /api/jobs/{id}/greeting-selection` | greeting.py:90 确认选择 | server.py:2164 ✅ | 引擎读 selection/edited_greeting/confirmed；1.x 发 `{"selection":"original","confirmed":True}` ✅ |
| 9 | `GET /api/history`（params: limit, include_unresolved, include_monitor_conversations） | replies.py:32 回复收件箱 | server.py:1323 ✅ | 三个参数引擎逐个读（1325-1327）✅ |
| 10 | `GET /api/history/unresolved-replies/count` | replies.py:36 | server.py:1360 ✅ | 只读 ✅ |
| 11 | `POST /api/history/{id}/open-chat` | replies.py:48 | server.py:1369 ✅ | 1.x 发 `{}`，引擎不读 body ✅ |
| 12 | `POST /api/history/{id}/prepare-reply` | replies.py:57 | server.py:1410 ✅ | 同上 ✅ |
| 13 | `POST /api/history/{id}/reply` | replies.py:66 记录回复 | server.py:2346 ✅ | ⚠️ **不兼容 ①**：1.x 发 `{"content": content}`，引擎读 `body.get("message")`（2361）→ 见「必须改造」 |
| 14 | `POST /api/history/{id}/dismiss` | replies.py:74 | server.py:2410 ✅ | 1.x 发 `{}`，引擎不读 body ✅ |
| 15 | `POST /api/resume/upload`（multipart） | resume_sync.py:110 简历 DOCX 同步 | server.py:3312 ✅ | 引擎读 `request.files.get("file")`（3315）；1.x multipart 字段名 "file" ✅ |
| 16 | `GET /api/workbench` | delivery/tasks/gate/api 任务状态轮询 | server.py:1460 ✅ | 只读 ✅ |
| 17 | `GET|POST /api/workbench/preflight` | status.py:166 六项预检 | server.py:1505 ✅（method 数组） | GET 无 body ✅ |
| 18 | `POST /api/workbench/task` | tasks.py:112 启动任务 | server.py:1725 ✅ | 引擎读 mode + options（可省）；1.x 发 `{"mode": mode}` ✅ |
| 19 | `POST /api/workbench/task/{id}/stop` | tasks.py 停止 | server.py:1815 ✅ | 路径参数 ✅ |
| 20 | `POST /api/workbench/deliver` | delivery.py:59 **发送（红线 S2）** | server.py:1825 ✅ | 引擎读 job_ids + direct_send（可省）；1.x 发 `{"job_ids": [...]}` ✅ |
| 21 | `POST /api/workbench/reject` | delivery.py:75 拒绝 | server.py:2005 ✅ | 引擎读 job_ids ✅ |
| 22 | `GET /api/stats`、`GET /api/activity` | api/ai_jobs.py 运行记录 | server.py:1080/1090 ✅ | 只读 ✅ |

**非引擎路径**：`/api/ai-jobs` 是简历通**自有** router 前缀（1.x api/ai_jobs.py:24，2.0 同名注册），不在表 1。
**计划附录 B 多列的两条**（`/api/workbench/greetings`、`/api/jobs/{id}/outreach-resume`）：1.x 适配层实际**不调用**（grep 0 命中），本轮不移植。

## 表 2 · 2.0 衔接点核对

| 衔接点 | 2.0 存在性 | 符号一致性 | 处置 |
|---|---|---|---|
| `services/export_pipeline.py` build_export | ✅ :297 | `build_export(request, resume, context) -> ExportArtifact`（inspect 实测） | 直接用 |
| `services/resume/document_io.py` document_for_record | ✅ :141 | `(db, record) -> tuple[dict, ConversionReport \| None]`（inspect 实测） | 直接用 |
| `services/resume/resume_delivery.py` default_render_context | ✅ :103 | `(db, record) -> dict`（inspect 实测） | 直接用 |
| `services/apply/task_runner.py` 互斥挂点 | ✅ :165 class TaskRunner | 2.0 无 AI 互斥块 → A4 加 | A4 |
| `models/ai_job_link.py` AiJobLink | ✅ :20 | 与 1.x **diff 完全一致** | 直接用（勿重建） |
| `models/job.py` JOB_STATUS_OPEN/APPLIED | ✅ :14/:16 | 常量名一致（值中文「开放中/已投递」） | 直接用 |
| `models/resume.py` ResumeRecord | ✅ :14 | 同名 | 直接用 |
| `models/setting.py` AppSetting(key,value) | ✅ :12-16 | key String(64) PK + value Text ✅ | 直接用（settings.py 的 ai_jobs_config 落点） |
| `models/tracker.py` ApplicationTrack | ✅ :217 | 同名 | 直接用 |
| `runtime/dataset_scope.py` current_dataset_id | ✅ :106 | 同名 | 直接用 |
| `config.py` DATA_DIR | ✅ :23 | 同名 | sidecar runtime 落 DATA_DIR/ai-jobs/<dataset>/ |
| `schemas/job.py` JobCreate | ✅ :106 | 唯一差异：job_type 默认值 1.x「社招」/ 2.0「校招」；job_sync 显式传全部所需字段、不含 job_type → **无影响** | 直接用 |
| `services/job/job_service.py` create_job_record / find_job_by_identity | ✅ :93/:86 | 签名一致 | 直接用 |
| `services/llm_settings.py` get_llm_config | ✅ :169 | 同名同签名（1.x:169 完全同位） | 直接用 |
| `services/api_key_session.py` session_key_configured | ✅ :32 | 同名 | 直接用 |
| `database.py` get_db | ✅ :176 | 同名 | 直接用 |
| `application_routers.py` | ✅ | 注册方式照既有路由 | A4 注册 |

## 表 3 · 版本窗口与凭据边界

| 项 | 当前位置 | 建议 |
|---|---|---|
| 引擎版本 | 2.4.0（pyproject.toml:7，grep 实测） | 窗口 `(2,4,0)–(3,0,0)` 原样移植，无需调整 |
| 版本窗口实现 | 1.x client.py:22-23 元组常量 + `version_in_window()` | 原样移植 |
| 发送闸门 | 1.x 仅 `api/ai_jobs.py:153` 的 `== "0"` 夜间总闸（**默认放行**） | 2.0 语义反转为**默认关**（计划红线 4/8、§12 F2）；phase_8 检查 5 把 `== "0"` 形态判 FAIL |
| 凭据边界 | 持久化 = `AiJobsConfig`（无凭据字段，schemas/ai_jobs.py:11-35）+ settings.py 整对象 JSON 落 AppSetting；`api_key` 只出现在 config_sync 发往引擎的 payload（:44），不回读不落库 | 原样移植；F1/phase_8 检查 8 双保险 |

## 必须改造（A2 执行，先记不改）

| # | 位置 | 现状（1.x） | 引擎 2.4.0 要求 | A2 处置 |
|---|---|---|---|---|
| ① | replies.py:66 | `post(.../reply, {"content": content})` | server.py:2361 只读 `body.get("message")`，空即 400 | 改发 `{"message": ...}`；**同时保留 `content` 键**（引擎忽略多余键，1.x 测试若断言 content 仍绿，避免动断言） |
| ② | greeting.py:68 | `post(.../greeting, {"greeting": text})` | server.py:2117-2118：`confirmed is not True` → 400 | 补 `"confirmed": True`。注：1.x 此调用在 2.4.0 引擎下**从未成功过**（一直走「写引擎失败保留本地快照」兜底），补上后行为才符合设计 |
