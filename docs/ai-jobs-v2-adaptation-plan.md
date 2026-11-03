# sidecar 的 v2 合并后适配计划（对照 `docs/ai-jobs-v2-read-paths.md`）

- 日期：2026-11-04。前置：v2（`fix/v2-single-model`）定稿并合并回 sidecar 正式分支**之后**再动手；动手前先跑 `docs/ai-jobs-v2-read-paths.md` 复核一遍行号（下文行号为 2026-11-04 工作区实测，`api/apply.py` 当前带并行会话未提交改动，合并后行号可能平移）。
- 结论先行：**没有"必须改"的读取口**。三处直读 `content` 的地方全部是形状无关用法；真正要做的只有"验证 + 一次预期内的重传"。本计划把 round2 要求的表格如实填成核验结论，并给出触发升级的条件——一旦条件命中，表格立即从"可不改"变"必须改"。

## 1. 必须改的（v2 合并后会坏的）

**无。** 三处被点名的读取口逐一核验如下（这也是"为什么不坏"的证据链，合并后照此回归即可）：

| 文件 | 行号（2026-11-04 实测） | 现在怎么读 | 为什么不需要改 | 回归命令 |
|---|---|---|---|---|
| `services/ai_jobs/resume_sync.py` | L44（`document_for_record`）→ L46（`build_export`）→ L47（`artifact.content` = DOCX 字节） | 导出走 v2 感知管线：`document_for_record` 负责 v1→v2 记忆转换/v2 直通，`build_export` 是 v2 原生出口（v2 整改 T4 已确认导出链直通 v2） | 内容模型变化被管线吸收，本文件不感知 | `pytest tests/test_ai_jobs_resume_sync.py -q`（6 例，含 DOCX 魔数断言） |
| `services/ai_jobs/resume_sync.py` | L96（`"content": record.content` 进语义哈希） | content 作为**不透明 dict** 序列化进 sha256，不解析内部字段 | 形状无关；哈希只要求"同内容同键" | 同上 + `pytest tests/test_ai_jobs_resume_sync.py::test_sync_skips_when_content_unchanged -q` |
| `services/job/job_match_context.py` | L77（`job_resume_text`） | `json.dumps({"title","job_title","content"})` 整包透传给匹配模型 | 透传不解析；模型自由阅读 v2 结构 | `pytest tests/test_ai_jobs_e2e.py tests/test_ai_jobs_delivery.py -q`（投递链路冒烟）+ 第 4 节探针 P1 |
| `api/apply.py` | L250（招呼语预览的 `resume_text`） | 同上透传，经 `job_match.py` L177–178 `strip_data_urls` + 8000 字截断进提示词 | 同上 | `pytest tests/test_apply_greeting_prompt.py tests/test_apply_greeting_and_privacy_qa.py -q` + 第 4 节探针 P2 |

> ⚠️ 行号时效：`api/apply.py` 与 `services/job/job_match.py` 当前有并行会话未提交改动（见 `docs/quality/uncommitted-audit.md` A 类）。合并后如行号漂移，以 `grep -n "resume.content"` 重新定位。

## 2. 可以不改的（形状无关，逐条理由）

1. **`resume_sync.py` L96 哈希**——不解析字段；唯一后果见第 4 节顺序建议里的"一次性重传"。
2. **`_queue.py` 全文**——只碰 `resume_id` / `resume.title`，与内容模型无关（grep `\.content` = 0 命中）。
3. **`ai_jobs/greeting.py` 全文**——只读写 `ai_job_link.greeting` 文本快照，不读简历内容。
4. **`api/ai_jobs.py` 全部引擎代理端点**——简历内容在 sidecar 链路里只出现两次：上传 DOCX（字节流）与引擎侧文本（引擎自己的模型）。简历通的 v2 收口对引擎是黑盒。
5. **`resume_sync.py` 的 `default_render_context`/`record.template` 等版式读取**——这些列不在 v2 收口范围（收口只动 `content` 与 `format_config` 旧键），签名未变。

## 3. 需要验证但不确定的（每条带验证方法）

| # | 不确定点 | 为什么不确定 | 验证方法（合并后执行） |
|---|---|---|---|
| V1 | 匹配/招呼语提示词对 **v2 JSON 结构**的生成质量是否与 v1 时代持平 | 透传正确 ≠ 模型读得一样好；提示词没有写死字段示例（`apply_greeting.md` 已核），但模型侧行为只能实测 | P1：`pytest tests/test_ai_jobs_e2e.py -q` 全绿后，真人跑一次岗位匹配 + 一次招呼语预览，肉眼对比结论质量；劣化再考虑在提示词里补一段"简历 JSON 是 v2 文档结构"的说明（那是提示词改动，不是读取口改动） |
| V2 | v2 合并后**全库 content 被归一化改写一次**，`resume_sync` 的语义哈希全部失效 | 哈希键含 `record.content`（L96）；归一化改变字节 | 预期内一次性重传（幂等上传，无害）。验证：合并后第一次 `POST /api/ai-jobs/resume/sync` 应返回 `uploaded=true`，第二次应返回 `简历未变化`；两次都如此即符合预期，**不要修** |
| V3 | `document_for_record` 在"全部已是 v2"的库上是否仍零告警 | v2 整改改过转换器（读时消费 `hidden_sections`），全 v2 库应走直通分支 | 探针：`pytest tests/test_ai_jobs_resume_sync.py::test_export_produces_docx_bytes -q`；并检查 `_report` 为 `None`（直通时无转换报告）——若返回了带 warning 的报告，说明混入了非 v2 行，先查数据再查代码 |
| V4 | `ExportRequest(format="docx")` 的 `format_config` 旧键清理对 sidecar 导出的版式是否有可见变化 | v2 Phase 3 让旧版式键不再生效；sidecar 导出走同一管线，版式可能"变得和收口前不同"（如被隐藏板块真的消失） | 真人对比合并前后导出的 DOCX 各一份；变化属 v2 的预期修复（隐藏板块真隐藏），不是 sidecar 回归 |
| V5 | `schemas/resume_document.py` 若在 v2 会话后续继续加字段（如 `section.hidden` 已在工作区未提交），`resume_sync` 的哈希/导出是否受影响 | `section.hidden` 只影响**导出管线内**的过滤，不改变 `record.content` 本身 | 哈希无关（content 不含该字段时）；导出会如实隐藏——若用户在预览里藏了板块，投递给引擎的 DOCX 也会藏。**这是语义决策点**：投出去的简历是否应与预览一致？当前口径=一致（同一管线），建议保持并在验收时向用户说明 |

## 4. 改动顺序建议（当且仅当第 1 节的触发条件命中才动手）

1. **先改 `api/apply.py` 的招呼语透传**（如果提示词要加 v2 结构说明）——改动面最小、有现成测试（greeting 两文件）、`git checkout -- <file>` 单文件可回滚。
2. **再改 `job_match_context.py`**——同样单文件可回滚，但匹配链路调用点多（单岗/批量两路），改完必须跑 `test_job_match*.py` 全家。
3. **最后碰 `resume_sync.py`**——它连着导出管线与哈希缓存，动它要跑 `test_ai_jobs_resume_sync.py` + `test_ai_jobs_e2e.py` + 一次真人冒烟（上传→引擎侧能看到简历），排最后。
4. 全部做完再跑一次三件套：sidecar 专项 36 例、`test_apply_greeting_*.py`、前端 `AiJobsPage`/ai-jobs 组件测试。

## 5. 回滚方式

| 改动 | 回滚 |
|---|---|
| `api/apply.py` 提示词说明 | `git checkout -- backend/app/api/apply.py`（单文件；注意该文件若带并行会话改动则改用 `git revert <提交>`，不能整文件回退） |
| `job_match_context.py` | `git checkout -- backend/app/services/job/job_match_context.py` |
| `resume_sync.py` | `git revert <提交>`——它有 6 个配套测试，单文件 checkout 会让测试与实现错位 |
| 一次性重传（V2） | 不需要回滚；幂等 |

> 底线不变：任何一条动手前，先确认 round2 文档第五节的三问（审查完成？已合并？工作树干净？）。
