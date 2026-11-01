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

### 旧资料迁移（新增）
- 上游 R-46 决定"旧资料不自动显示"；本地用户需要原资料，因此新增一次性脚本
  `scripts/import_legacy_profile_to_new_model.py`：读取旧 `user_profile` + 教育/经历/项目/技能/校园/奖项，
  映射到新版 `profile_entry` 默认组（基本信息、总结、教育、经历、项目、技能、语言证书）。
  脚本先复制数据库备份，旧表不删，可回滚。真实库已执行（19 个条目）。

### 后端回放（已回放）
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
- [x] 看图模型兜底（`vision_fallback`；岗位/资料/进度四个带图入口，保留 `run_until_disconnect`）
- [x] 17 套模板合并（catalog + layout + tag/column/list；9 套 j2 去 fit-scale、补语言与缩放变量）
- [x] 自制样式模板恢复（创建/编辑/预览/出现在可选清单）
- [x] 岗位类型默认社招、按 JD 推断
- [x] API Key 编辑：上游新设置页已是「留空保持不变 + 可重输」，无需回放旧控件
- [x] 岗位排序/批量选择：上游已有，采用上游实现

### 前端
- [x] i18n：采用上游运行时 + zh-CN/en-US；本地新增文案全部进语言包
- [x] 三栏制作台、revision/冲突、版本、大纲、来源、模板试用、精确 PDF 预览：采用上游
- [x] 模板画廊：上游画廊 + `category` 分组（用 CSS 属性显示分类，避免改变既有 DOM/文案 AST）
- [x] `/skills` 模板管理：恢复内置样式画廊、复制内置、导入 HTML、导入参考、自制样式模板，全部 i18n
- [x] 隐藏板块控件（制作台左栏）、招呼语确认开关、按链接导入、Ego Lite 选项
- [ ] 模板画廊的“真实页数/试用”仍需用真实模板逐套点一遍（自动化已覆盖组件）
- [ ] 9 套本地模板的中英文 label/description 仍回退后端中文（英文界面待补）

## 本地刻意偏离（可回退）

### 资料页日期：直接输入（刻意偏离，已实测）
- 上游实现：`PartialDateSelect` 的「年/月/日」三个联动 Select；年份约 130 项、虚拟列表。
- 实测问题：在 Windows 125% 缩放 / Ego Lite（Chromium 156）下点年份会整页抖动；
  固定宽度、关闭虚拟列表、编辑态关闭 `content-visibility` 都试过，仍不能稳定复现/根治。
- 最终方案：**新版资料库的日期改为单输入框** `PartialDateInput`（`2022` /
  `2022-09` / `2022-09-15` / 中文日期，失焦归一化），彻底移除弹层、虚拟列表与
  定位重排；旧的 `PartialDateSelect` 保持上游原样，供旧资料组件使用。
- 回退：`ProfileFieldInputs.tsx` 的 import 换回 `PartialDateSelect`，删除
  `PartialDateInput.tsx` 与 4 条 `dateFields.*.input*` 文案即可。
- 取舍：与上游 UI 不同（打字 vs 选择），但改动仅 1 个新组件 + 1 行 import + 4 条文案；
  Ego Lite 实测可正常输入，不再触发弹层。

## 决策记录
- 模板：保留本地 17 套；上游 `scholar` 作为新增可选模板保留（合计 18，待最终确认）。
- `/skills`：保留模板创作/导入/自制模板管理，并整合上游模板试用/对比。
- 本地重复功能（批量导出/对比选岗/用量/AI 任务）：改用上游实现，不保留本地代码。

## 验收进度
- 后端全量测试：回放后首轮 39 失败已逐项收口（招呼语测试配置、模板策略测试、示例填充率），最终全量运行中。
- 前端全量：683 文件 / 4783 用例通过；`tsc` / `build` 通过。
- 模板：18 套 HTML 全部渲染成功；cpp PDF 冒烟 1 页 / 103KB；布局/标签/颜色守卫通过。

## 验收闸门
1. 后端全量测试通过；前端全量 vitest / tsc / build 通过。
2. 17 套模板 HTML/PDF/Word 快照与迁移前对比；画廊分组、试用、`/skills` CRUD。
3. 制作台三栏、实时预览、保存、revision 冲突、版本恢复、大纲、来源、精确预览。
4. 真实库迁移后业务数据完整，备份导出/恢复可用。
