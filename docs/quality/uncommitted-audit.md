# 未提交改动归属审计（2026-11-04 02:15 采集）

- 分支 `fix/v2-single-model` @ `f7df4afd`；**57 项 = 35 修改 + 22 未跟踪**（含 2 项已知按设计未跟踪的 `frontend/.npmrc`、`frontend/runtime/`，以及 1 个未跟踪目录）。
- 方法：只读 `git status --porcelain` / `git diff`（逐文件看过 diff 内容，非按文件名猜）。
- **本文档只是审计，未执行任何 git 写操作。**

## 一句话总结

57 项里：**A 类（招呼语/投递台，22 项）与 B 类（覆盖补全，4 项）是完整、自洽、有测试的功能切片，应该提交**；**C 类（显隐/技术栈，13 项）全部落在 v2 会话所有权区，需用户与 v2 会话对账**；**D 类（文档/配置，18 项）里有一个高危项 `scripts/v2_gate.py` 未入库**；E 类（无法归类）为 0。

---

## A 类：招呼语 / 投递台相关（22 项）→ **应该提交**

一句话：这是「自定义打招呼语基准」完整功能（用户拍板过的 v3 招呼语改版的后端部分）+ 投递队列分页修复 + 队列简历搜索排序，前后端 + 测试 + 提示词 + CHANGELOG 条目自洽成套。

| 文件 | 变化 | 说明 |
|---|---|---|
| `backend/app/schemas/apply/config.py` | +2 | 新字段 `greeting_baseline`（≤4000 字，注释写明"只约束风格不覆盖事实"） |
| `backend/app/schemas/apply/records.py` | +2 | 预览请求新增可选 `resume_id`（编辑弹窗刚选中、未保存的简历优先） |
| `frontend/src/types/apply/config.ts` | +2 | 同字段的 TS 类型 |
| `backend/app/services/job/job_match.py` | 29± | `build_greeting_messages`/`generate_greeting` 接 `greeting_baseline` 参数，基准以 `<USER_GREETING_BASELINE>` 注入 system 并声明"不得把基准示例当用户事实" |
| `backend/app/prompts/apply_greeting.md` | 93± | 提示词改版（第一句只写投入方式/项目能力，不写学历届别） |
| `backend/app/api/apply.py` | 24± | 预览端点透传 baseline + resume_id 覆盖 |
| `backend/tests/test_apply_greeting_prompt.py` | 29± | 提示词/基准注入的测试更新 |
| `backend/tests/test_apply_greeting_and_privacy_qa.py` | +55 | 新增基准与隐私 QA 用例 |
| `frontend/src/api/apply.ts` | +3 | 预览请求带新字段 |
| `frontend/src/components/apply/ApplySettingsModal.tsx` | +8 | 设置弹窗加「自定义打招呼语基准」编辑框 |
| `frontend/src/components/apply/queue/QueueTable.tsx` | 7± | 分页器 pageSize 改受控 state（修"切 20 条/页被重置回 10"） |
| `frontend/src/components/apply/queue/QueueTable.test.tsx` | +24 | 分页回归测试 |
| `frontend/src/components/apply/queue/QueueItemEditor.tsx` | 4± | 配合简历选择/预览的新字段 |
| `frontend/src/hooks/remoteSearchOptions.ts` | 49± | 队列简历远程搜索：本岗位简历排最前、收藏补后去重、来源标签 |
| `frontend/src/hooks/remoteSearchOptions.test.ts` | 未跟踪新文件 | 上一行的测试 |
| `frontend/src/i18n/messages/{zh-CN,en-US}.applyQueue.ts` | 5±/5± | 队列文案 |
| `frontend/src/i18n/messages/{zh-CN,en-US}.applySettings.ts` | +3/+3 | 「打招呼语基准」设置文案 |
| `frontend/src/i18n/messages/{zh-CN,en-US}.hooksUi.ts` | +4/+4 | 远程搜索来源标签文案 |

**判断依据**：diff 实证功能闭环（schema→API→prompt→设置 UI→测试）；CHANGELOG 第一条（"招呼语不再介绍学校/专业…新增自定义打招呼语基准"）与 memory 中「11-03 招呼语 v3 定稿、设置页可自定义打招呼语基准」的用户拍板一致——这不是半成品，是做完没收尾提交。
**注意**：`CHANGELOG.md` 里这一类只有 5 行中的一条，另两条属 B/C 类（见 D 类说明），拆分提交时需要 hunk 级挑选或整文件随最后一批走。

## B 类：覆盖补全 / 投影相关（4 项 + CHANGELOG 交叉）→ **应该提交**

一句话：「从资料补上这段」从假动作修成真能补入（含板块名/插入顺序/AI 润色入口 + coverage_notes 只清已补项）。

| 文件 | 变化 | 说明 |
|---|---|---|
| `frontend/src/features/profile-library/projectionContent.ts` | +325 | 资料投影补入：`ensureSection` 按板块顺序插入、技能 inline 板块合并、按名称定位原始条目 |
| `frontend/src/features/profile-library/projectionContent.test.ts` | +50 | 上述行为测试 |
| `backend/tests/test_resume_coverage.py` | +67 | coverage_notes 收窄（只移除已补进正文的名字）的测试 |
| `frontend/src/features/profile-library/fillCoverageNote.test.ts` | 未跟踪新文件 | 补全动作的测试 |

**判断依据**：CHANGELOG 第 2–3 条明说是修真实缺陷（"原按钮走 v2 AI 修订，修订不能新增整条项目，点完预览没变化"）；测试齐全。`profile-library/**` 在 round2 文档的 v2 所有区名单里，但改动内容与 v2 单模型收口正交（投影层，非 resume/**），且 CHANGELOG 已写好条目——按"完成的功能切片"应该提交；因跨越所有权线，保守起见也可与 C 类一起由用户签字。
**综合判：应该提交，但建议用户扫一眼 ownership 一行。**

## C 类：显隐 / 技术栈 / 去重相关（13 项）→ **需要用户决定（与 v2 会话对账）**

一句话：板块级显隐（`section.hidden`）的前后端类型 + 两个新组件 + 文案 + 测试，以及 v2 已提交代码缺失的配套测试——**全部落在 v2 会话所有权区，且不知道 v2 对抗审查是否预期它们存在**。

| 文件 | 变化 | 说明 |
|---|---|---|
| `backend/app/schemas/resume_document.py` | +2 | v2 section 新增 `hidden: bool = False`（**v2 所有区**） |
| `frontend/src/types/resumeDocument.ts` | +2 | 同字段 TS 类型 |
| `frontend/src/components/resume/PreviewSectionsControl.tsx/.test.tsx` | 未跟踪新文件 | 预览弹窗「板块」显隐/排序控件（**resume/** 所有区**） |
| `frontend/src/components/resume/SectionVisibilityPanel.tsx/.test.tsx` | 未跟踪新文件 | 制作台「显示板块」面板（**resume/** 所有区**） |
| `frontend/src/i18n/messages/{zh-CN,en-US}.document.ts` | 2± | 文档编辑器文案 |
| `frontend/src/i18n/messages/{zh-CN,en-US}.resume.ts` | +4/+4 | 显隐文案 |
| `frontend/src/i18n/messages/{zh-CN,en-US}.workbench.ts` | +10~11 | 「板块」弹层/隐藏技术栈文案（`workbench.sectionsVisibility.*`） |
| `backend/tests/test_document_html.py` | +13 | 板块 hidden 的 HTML 导出断言（**test_document_** 所有区**） |
| `backend/tests/test_generation_preferences.py` | +35 | v2 文档形态的 tech_stack strip 测试（**test_generation_** 不在禁区，但内容属 v2 技术栈话题） |
| `backend/tests/test_resume_dedupe.py` | 未跟踪新文件 | ⚠️ **`resume_dedupe.py` 的改动已在 `e38502f2`（v2 Phase 2）提交，但它的测试文件一直没入库**——已提交代码处于"无测试保护"状态 |

**判断依据**：`section.hidden` 类型 + CHANGELOG 第 4–5 条（预览「板块」弹层、制作台「显示板块」）是一套完整功能，且与 morning-report §5 说的"三处 E6 文档-代码冲突"同源——**很可能是 v2 会话对抗审查后正在做的下一步（修"Markdown/TXT 丢自建板块"）的工作现场**。sidecar 会话无权替它决定提交还是继续改。
**专项建议（无争议的一份）**：`backend/tests/test_resume_dedupe.py` 单独尽早提交——它是已提交代码缺的测试，不是半成品。

## D 类：文档 / 配置（18 项）→ 分级

| 文件 | 变化 | 判断 | 依据 |
|---|---|---|---|
| `scripts/v2_gate.py` | 未跟踪 | **应该提交（高优先）** | v2 闸门本体。Phase 0–3 的全部验收、晨报引用、晨间清单第 0 步都靠它，但它从未 `git add`——现在只存在于这一台机器的工作区，误删/误清即失传，且 `docs/quality/fork-baseline.md` 引用的结果将不可复现 |
| `docs/quality/fork-baseline.md` | 10± | 应该提交 | 对抗审查 L5 对"6 条推断失败"的改注（引用时必须注明"推断"），是基线文档的勘误 |
| `docs/quality/v2-adversarial-review.md` | 未跟踪 | 应该提交（v2 会话的审查产出，用户需要它留档） | 审查报告本体 |
| `docs/fork-v2-compatibility-plan.md` / `.review.md` | 未跟踪 | 应该提交 | 方案文档 + 审查标注，morning-report 多处引用 |
| `docs/night-shift-v2.md` / `night-shift-v2-paste.txt` / `round2-v2-phases456.md` / `fork-v2-phase-prompts.txt` / `adversarial-review-v2.md` / `alignment-ai-jobs.md` / `morning-handoff-ai-jobs.md` / `sidecar-round2.md` | 未跟踪 | 需要用户决定 | 会话编排用的过程文档/提示词（含给两个会话的指令原文）。留档有价值，但含工作流私货；且 `docs/` 已有同类已入库文档，建议入库前用户过一眼是否有不想公开的内容（仓库是公开 fork） |
| `docs/提示词-交给两个会话/` | 未跟踪目录 | 需要用户决定 | 同上 |
| `CHANGELOG.md` | +5 | 应该提交，但要**最后**提交 | 5 条新条目分别属于 A（招呼语）、B（覆盖补全 ×2）、C（显隐 ×2）——单独先提交会让 CHANGELOG 描述不存在于库里的功能；随最后一类功能提交，或 hunk 拆分 |
| `frontend/.npmrc`、`frontend/runtime/` | 未跟踪 | 保持未跟踪（现状正确） | 首晚交接文档明示保留不动（本地 npm 镜像配置与运行时产物） |

## E 类：无法归类

无。57 项全部可归入 A–D。

## 建议的收尾顺序（供用户照抄，本文档不执行）

1. `scripts/v2_gate.py` + `docs/quality/fork-baseline.md` + `docs/quality/v2-adversarial-review.md`（v2 验证链闭合，最急）
2. `backend/tests/test_resume_dedupe.py`（已提交代码补测试）
3. A 类整批（招呼语功能 + 投递台修复，含 CHANGELOG 第 1 条 hunk）
4. B 类整批（覆盖补全，含 CHANGELOG 第 2–3 条 hunk）
5. C 类：等 v2 对抗审查结论后，由 v2 会话自己收（含 CHANGELOG 第 4–5 条 hunk）
6. 过程文档由用户过目后决定入库或移出仓库

> ⚠️ 全程未执行 `git add` / `commit` / `stash` / `checkout`——以上仅为审计结论。
