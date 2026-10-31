# 上游完整对齐 · 回放清单

分支：`sync/upstream-full-20261101`（从 `upstream/main` `ba6856b1` 起步）
备份：`D:/飞牛文件同步/工作/_backups/ResumeForge-20261101-pre-upstream`（含 zip 与 SHA256）

## 策略

以 upstream 代码为新基线，**只回放上游没有的本地功能**；上游 10-28 已原生具备的
批量导出、AI 对比选岗、用量计费、通用 AI 任务，统一采用上游实现，不再保留本地副本。

## 已完成

### 阶段 0 / 1：基线与数据迁移
- 上游基线：后端 `pytest`、前端 `vitest` / `tsc` / `build` 均通过（记录见会话）。
- `scripts/migrate_local_db_to_upstream.py`：把本地 0046→0047/0048 分叉对齐到上游
  0046 共同祖先，再跑上游 0047→0068；实测业务表行数不变、integrity ok、上游应用可启动。

### 后端回放（第一批）
- 隐藏板块：`resume_sections.py` 增加 `normalized_hidden_sections` /
  `resolved_hidden_sections` / `resolved_visible_sections`；HTML / PDF / Word /
  Markdown/txt 四个渲染器统一使用可见列表；`validated_format_config` 保留非空
  `hidden_sections`。测试：`tests/test_resume_hidden_sections.py`。
- 招呼语闸门：`ApplyConfigIn.require_greeting_review`（默认开）；未确认招呼语的队列
  条目按 `greeting_missing` 软跳过，不拿默认招呼语群发；提示词改为「前 15 字必须有
  信息量」。测试：`tests/test_apply_greeting_gate.py`。
- 岗位按链接/当前页导入：`/api/jobs/import-url`、`/api/jobs/import-current` +
  `services/job/job_type_infer.py`（默认社招，实习/校招需明确字样）。
  测试：`tests/test_job_import_url.py`、`test_job_type_infer.py`。
- Ego Lite 与随应用扩展：`browser_locator.py`、`BrowserChoice=ego`、
  `_start_arguments` 挂载 `--load-extension`；扩展目录
  `backend/app/services/browser/extension/`。测试：`tests/test_browser_ego.py`。

## 待回放

### 后端
- [ ] 看图模型兜底（`vision_fallback` + 四个带图识别端点；需保留上游 `run_until_disconnect` 语义）
- [ ] 17 套模板合并（catalog + layout + tag/column/list 三张附表 + 9 套 j2 rebase）
- [ ] 自制模板 `custom_template_options` 保留（上游已返回空）
- [ ] API Key 编辑态可替换/可清除（上游设置页结构已变）
- [ ] 岗位排序/类型/批量选择等本地 UX（先核对上游是否已有）

### 前端
- [ ] i18n：直接采用上游运行时 + zh-CN 语言包；本地新增文案进 zh-CN（不复制守卫）
- [ ] 三栏制作台、revision/冲突、版本、大纲、来源、模板试用、精确 PDF 预览：采用上游
- [ ] 模板画廊：上游画廊 + 恢复 `category` 分组 + 本地缩略图参数（resumeId/format_config）
- [ ] `/skills` 模板管理：恢复本地导入/复制/自制模板 UI，迁移到 i18n，并接入上游试用
- [ ] 17 套模板在画廊/管理页的 label/description/category key
- [ ] 隐藏板块控件、招呼语确认、链接导入、Ego 选项、看图提示等本地 UI 回放

## 决策记录
- 模板：保留本地 17 套；上游 `scholar` 作为新增可选模板保留（合计 18，待最终确认）。
- `/skills`：保留模板创作/导入/自制模板管理，并整合上游模板试用/对比。
- 本地重复功能（批量导出/对比选岗/用量/AI 任务）：改用上游实现，不保留本地代码。

## 验收闸门
1. 后端全量测试通过；前端全量 vitest / tsc / build 通过。
2. 17 套模板 HTML/PDF/Word 快照与迁移前对比；画廊分组、试用、`/skills` CRUD。
3. 制作台三栏、实时预览、保存、revision 冲突、版本恢复、大纲、来源、精确预览。
4. 真实库迁移后业务数据完整，备份导出/恢复可用。
