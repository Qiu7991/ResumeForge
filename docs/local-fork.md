# 本地二开与上游同步手册

本仓库是 [ResumeForge](https://github.com/magicapple123/ResumeForge) 的本地二开版：
`main` 只跟踪上游，二开改动全部落在独立分支上。目标有两条——**打开就能用**，以及
**以后还能继续跟上游更新**。本文记录哪些地方偏离了上游、为什么，以及下次合并时怎么走。

- 上游基线：`fa3a565`（2026-10-15，MIT 时期的最后一个提交）
- 二开分支：`feat/local-custom-20261030`（功能）→ `sync/security-20261031`（安全 + 批量导出）
- 公开 Fork：`Qiu7991/ResumeForge`，推送走 `ssh://git@ssh.github.com:443/Qiu7991/ResumeForge.git`

## 一、改动分层：先看新文件，再看改上游文件

合并冲突只发生在「同一个文件的同一段」。所以本地功能**尽量落在新文件里**，对上游客心
文件只做小切口修改。下表按这个标准分层。

### A. 纯新增文件（合并时几乎不会冲突）

| 功能 | 文件 |
| --- | --- |
| 岗位按链接/当前页导入 | `backend/app/api/job_import.py`、`frontend/src/pages/jobs/ImportJobUrlModal.tsx`、`useImportUrlParam.ts`、`useJobsImportBridge.ts` |
| 岗位类型推断（默认社招） | `backend/app/services/job/job_type_infer.py` |
| 浏览器定位（Chrome/Edge/Ego Lite） | `backend/app/services/browser/browser_locator.py` |
| 页内悬浮收录扩展 | `backend/app/services/browser/extension/{manifest.json,content.js}` |
| 看图模型兜底 | `backend/app/services/vision_fallback.py` |
| BOSS 详情解析（从 boss_search 拆出） | `backend/app/services/sites/boss_detail_parse.py` |
| 底稿派生 / 生成 runner 支撑 | `backend/app/services/resume/resume_base_derive.py`、`resume_runner_support.py` |
| 简历批量导出 | `backend/app/api/resumes/batch_export_routes.py`、`frontend/src/api/resumeBatchExport.ts`、`frontend/src/pages/resumes/BatchExportModal.tsx` |
| 9 套技术方向模板 | `backend/app/templates/resume_{php,java,node,ios,android,web,cpp,architect,dev}.html.j2` |

新增文件可以直接复用上游的公共能力，但**不要**为了"以后好合并"去复制上游代码；
上游的函数签名变了要跟着改，这是合并成本最低的形态。

### B. 修改了上游文件（合并时逐个过）

| 区域 | 文件 | 本地改动摘要 |
| --- | --- | --- |
| 隐藏板块 | `services/resume/resume_sections.py`、`resume_template_format.py`、`exporter.py`、`docx_exporter.py`、`pdf_exporter/render.py`、`export_pipeline.py` | `format_config.hidden_sections` 在预览/PDF/Word/文本四处同源生效 |
| 招呼语闸门 | `services/apply/task_apply.py`、`schemas/apply/config.py`、`api/apply.py`、`prompts/apply_greeting.md` | 未确认招呼语默认拒投（`require_greeting_review`），提示语按 JD 生成 |
| 浏览器 | `services/browser/browser_manager.py` | Ego Lite 选项、列表式启动参数、扩展加载开关 |
| 岗位 | `api/jobs.py`、`schemas/job.py`、`services/sites/boss_search*.py`、`frontend/src/pages/JobsPage.tsx` 等 | 收录时间排序、复选框常驻、类型默认社招、链接导入接线 |
| 生成/修订 | `resume_generate_runner.py`、`GenerateResumeModal.tsx`、`ResumeReviseModal.tsx`、`api/client.ts`（`ai` 预算） | 可选底稿、180s 预算、等待秒数与耗时提示 |
| 设置 | `components/settings/ApiKeyInput.tsx`、`LLMConfigCard.tsx` | 编辑态空框替换、显示后可编辑、清除已保存密钥 |
| 导出 | `api/resumes/export_routes.py` | 仅新增 `save_copy` 参数（批量导出不往保存目录刷 N 份副本；上游同名参数） |
| 模板库 | `resume_template_catalog.py`、`resume_template_layout.py`、`TemplateGalleryModal.tsx` 等 | 新增 9 套模板及其版式数据 |

## 二、刻意与上游不同的地方（合并时不要"顺手改回去"）

1. **批量导出参数**：上游只从「设置 → 批量操作」读格式/字号/页数，请求体只有 id。
   本仓库没有那套批量设置，`batch_export_routes.py` 把 `format` 放进请求体（默认 PDF），
   字号/页数/版式沿用每份简历自己的记录。以后移植设置页时，把 `payload.format` 换成
   `read_batch_operation_config(db).export` 即可，其余逻辑与上游一致。
2. **没有 i18n**：上游 10-26 起全站迁移到 `t()` + `useLocale`，本仓库仍是中文直写。
   合并上游前端时，要么整批接受 i18n（路径 3），要么把上游新组件里的 `t("key")`
   换回中文；不要只引入 key 却缺语言包（界面会显示 key）。
3. **模板界面**：上游 10-23 已整体下线模板画廊，本仓库仍保留并扩展了模板库。
   这是产品取向差异，合并前先决定保不保留（见 `docs/upgrading.md` 的上游同步一节）。
4. **隐藏板块是用户意图**：被隐藏的专业技能/校园经历/荣誉奖项**不放进简历、不润色**，
   不要以"内容更完整"为理由恢复。
5. **单文件 500 行预算**：本地新增 9 套模板把 `resume_template_layout.py` 顶到 714 行，
   已按仓库规则登记书面豁免（到期 2026-11-15）。合并上游后优先按上游新结构迁移，
   不要再往这个文件里堆数据。
6. **站点名只出现在后端注册表**：前端生产代码禁止硬编码 `BOSS`/`zhipin` 等字样
   （`test_qa_browser_sites_adversarial.py` 钉住），新页面用"当前招聘网站"这类措辞。

## 三、新增功能的兼容性约定

写新功能时按这几条做，下次合并的成本基本就是"改 import"：

- **能加文件就不改文件**：新端点放新模块（`api/resumes/batch_export_routes.py` 是范本），
  新组件放新文件，再在聚合处加一行 `include_router` / 一个 import。
- **给上游函数加可选参数，不改默认行为**：`_export_record(..., save_copy=True)` 是范本；
  默认值保持上游语义，本地调用方显式传非默认值。
- **参数名与上游对齐**：即使实现不同，也沿用上游的字段名/响应头名
  （`X-Batch-Exported` / `X-Batch-Skipped` / `X-Batch-Skipped-Detail`），合并时只对实现。
- **测试跟着功能走**：新端点配 `backend/tests/test_*.py`，前端 API 配 `*.test.ts`；
  纯 UI 改动至少保证现有页面测试不红。
- **改动点登记**：新增偏离上游的行为，补到本文第二节，而不是只写在提交信息里。

## 四、合并上游 playbook

```bash
# 0) 工作区必须干净；先备份（scripts/../backup-resumeforge.sh 或 _backups/tools）
git status --short

# 1) 拉上游（直连不通时用镜像；镜像只读，fetch 够了）
git fetch upstream main            # 或 gh-proxy / ghfast 镜像
git switch -c sync/upstream-$(date +%Y%m%d) upstream/main

# 2) 把本地二开合进来（或反向：在二开分支 merge upstream/main）
git merge --no-commit feat/local-custom-20261030

# 3) 冲突逐个过：先跑测试确认语义，再决定取哪边
git diff --name-only --diff-filter=U
```

已知冲突热点（2026-10-30 试跑：56 个冲突 / 3946 文件）：

- `services/resume/resume_sections.py`、`resume_template_layout.py`、`resume_generate_runner.py`
- `exporter.py` / `pdf_exporter/` / `docx_exporter.py`（隐藏板块与页数口径）
- `JobsPage.tsx` / `JobTable.tsx` / `BatchToolbar.tsx`（排序、复选框）
- `GenerateResumeModal.tsx`、`ResumeLayoutControls.tsx`、`ApiKeyInput.tsx`（上游可能已删除）
- 前端全面 i18n 化带来的"大面积文本冲突"——优先接受上游结构，再把本地中文文案填回去。

**验收清单（每次合并后必跑）**：

1. `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` 全绿（含 500 行预算守卫）。
2. `frontend`: `npx tsc --noEmit` + `npx vitest run` 全绿 + `npm run build`。
3. 起服务（`ps7 -f scripts/Start-ResumeForge.ps1 -NoBrowser`），5173/8005 均 200。
4. 冒烟：打开一份简历 → 预览 → 导出 PDF（页数正常）；投递台启动浏览器；岗位广场排序/导入。
5. 许可证：上游 10-20 起为 Apache-2.0。合入其代码后保留上游 `LICENSE`、补 `NOTICE`、
   在改动文件头标注修改；本仓库自有代码的许可证声明以届时 `LICENSE` 为准。

## 五、已知债务

- `resume_template_layout.py` 714 行（豁免到期 2026-11-15）——合并上游后按新结构拆分。
- `test_new_modules_api.py` 514 行（豁免到期 2026-11-15）——拆出 `test_job_import_api.py`。
- 上游 10-28 的「AI 对比选岗」「AI 任务与用量计费」尚未移植；后者依赖上游
  `ai_task_runner` / `batch_operation` 底座，移植前先评估是否连带引入设置页。
- 本地未跟踪：`frontend/.npmrc`（npmmirror 镜像配置）、`frontend/runtime/`（调试产物），
  不要提交。
