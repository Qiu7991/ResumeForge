# SPDX-License-Identifier: Apache-2.0
"""生产代码行数预算守卫（PR-18 扩面版）。

2026-10 大规模拆分（55 commits）后确立：生产代码单文件不得超过 500 行
（modular-code-planner 工作流 C 的红线）。新增文件超限会让本测试变红，
强制开发者在「继续膨胀」与「拆分/书面豁免」之间做显式决策。

PR-18（2026-10-13 审计）扩面与硬化：

1. **豁免必须带到期日**（``Exemption.expires``，ISO 日期）。到期后守卫变红并
   点名——防止白名单无声续期；续期必须显式改这条记录（新理由 + 新日期）。
   带「触发条件」的豁免保留原语义（条件仍然是主判据），到期日是兜底复核点。
2. **范围扩展到 scripts/（``*.py``）与 desktop/（``*.js``）**。这两个目录是
   CLI/工具脚本的现实：一次性任务脚本、带主流程的测量与打包工具，500 行的
   生产代码预算不适用，因此 scripts 用独立预算 800；desktop 维持 500
   （实测最大文件 470 行，零豁免起步）。扩面目标是「新增长文件必须自觉登记
   豁免」，不是追溯性大拆。

3. **CSS 纳入范围**（S1，2026-10-22）。此前 ``SCAN_SUFFIXES`` 只有
   ``.py/.ts/.tsx``，``frontend/src`` 下的样式表**完全不可见**——最大的
   ``styles/modules.css`` 已到 2056 行（预算的 4.1 倍）却从未被拦过。现在把
   ``.css`` 纳入同一 500 行预算。S1 当时只止血：存量 5 个超线文件登记带到期日
   （2026-12-31）的豁免，按分段标题拆分另立项。**该拆分已于 2026-12-31 到期日
   执行完毕**（5 个聚合清单 + 19 个平铺分片，均为纯搬迁），CSS 豁免清单现为空，
   与既有 ``.ts/.tsx`` 一样零豁免。
4. **幽灵豁免守卫**（S3）：豁免条目指向的文件若已不再超预算，
   ``test_exemptions_only_for_over_budget_files`` 变红——拆分完成后必须同批
   删除豁免，否则白名单只会越来越长、无人知道哪条还有效。

豁免必须在本文件登记并附书面理由 + 到期日；豁免是白名单不是许可，新增豁免
条目应同步到 ``.workbuddy/split-plan/`` 对应方案或交付报告。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("backend/app", "frontend/src")
# S1（2026-10-22）：样式表纳入同一预算。此前没有 .css，5 个样式表长期超线却
# 不可见（最大 2056 行）；现在把它们变成「可见但暂时豁免」，净效果是变严。
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".css"}
TEST_NAME_MARKERS = (".test.", ".spec.")
LINE_BUDGET = 500

# scripts/ 与 desktop/ 的扩面预算与排除目录（PR-18）。
SCRIPTS_ROOT = "scripts"
SCRIPTS_SUFFIXES = {".py"}
SCRIPTS_BUDGET = 800
DESKTOP_ROOT = "desktop"
DESKTOP_SUFFIXES = {".js"}
DESKTOP_BUDGET = 500
DESKTOP_EXCLUDED_DIRS = {"node_modules", "out", "payload", "dist", "build", "release", ".vite"}

# 测试文件扫描范围：后端按 tests/ 目录命名约定（test_*.py），
# 前端按共置命名约定（*.test.ts / *.test.tsx）。
TEST_SCAN_GLOBS = (
    "backend/tests/test_*.py",
    "frontend/src/**/*.test.ts",
    "frontend/src/**/*.test.tsx",
)


@dataclass(frozen=True)
class Exemption:
    """一条书面豁免：具体理由 + 到期日（ISO 日期，到期后守卫变红点名）。"""

    reason: str
    expires: str


# 现有豁免的结构性理由（monkeypatch 钉死 / 字面路径锚定 / 单一类内聚等）不随
# 时间变化，触发条件是主判据；到期日统一给 2027-06-30 作为强制复核的兜底点。
_STRUCTURED_BACKSTOP = "2027-06-30"
# 本会话多 PR 叠加增长导致的过线：拆分与行为修改必须分补丁，本批只豁免；
# 到期日 2026-11-15，届时拆分或续期（续期需要新理由）。
# 已按 2026-11-15 到期日执行拆分：两条测试豁免（test_resume_render_overrides.py /
# DocumentEditor.header.test.tsx）已拆分并删除，常量随之移除。
# CSS 历史存量（S1，2026-10-22）的豁免已于 2026-12-31 到期日执行拆分并全部删除，
# 因此不再需要 `_CSS_BUDGET_BACKSTOP` 常量——CSS 现在与 .py/.ts/.tsx 同档，零豁免。
# 二开移植（2026-11-08）期间长起来的文件走这一档：到期日 2026-12-31，
# 决策依据与逐文件理由见生产豁免清单里那一段。
_FORK_BACKSTOP = "2026-12-31"

# 测试文件书面豁免清单（路径相对仓库根；理由必须具体，禁止「暂缓拆分」式空话）
_TEST_EXEMPTIONS: dict[str, Exemption] = {
    # 2026-10-05 网申自定义字段修复批新增 4 条逐框建议守卫（+63 行）后 527 行，超线 27 行；
    # 本文件还被 test_file_size_budget 之外的哨兵用例以模块命名空间 monkeypatch 钉死
    # （见生产豁免中 live.py 条目说明），拆文件会分散哨兵落点。
    # 触发条件：>600 行或下批再增用例（届时拆 test_webform_live_custom.py）。
    "backend/tests/test_webform_live.py": Exemption(
        "过线 27 行，monkeypatch 哨兵与脚手架耦合", _STRUCTURED_BACKSTOP
    ),
    # 2026-11-02 界面修复批（任务 1 / 任务 6）的两条豁免（后端 549 行 / 前端 523 行）
    # 已按 2026-11-15 到期日执行拆分并删除：后端拆出 test_resume_photo_crop_render.py +
    # resume_render_fixtures.py，前端拆出 DocumentEditor.photoCrop.test.tsx +
    # src/test/documentEditorHeaderHarness.tsx——均为纯搬迁，用例数与断言逐条不变。
    # TrackerPage.test.tsx 的豁免（2026-10-13 PR-13 批新增用例后 517 行，超线 17 行）
    # 已于 2026-10-22 到期执行：按其自身预案拆出 TrackerPage.import-modal.test.tsx
    # （导入预览/深链域）+ src/test/trackerPageHarness.tsx，不再豁免。
    # 2026-10-22 之后该文件只守页面通用行为与统计卡配色（T9）。
    # ProfilePage.test.tsx 的豁免（触发条件 >800 行）已于 2026-10-13 到期执行：
    # 按其自身预案拆出 ProfilePage.webform.test.tsx + src/test/profilePageHarness.tsx，
    # 不再豁免。
    # ---- 二开移植（2026-11-08）：上游基线（d893243）这三个文件全部 <500 行 ----
    # 超线来自 1.x 二开移植的用例（覆盖清单逐条补入 / 投递台招呼语与隐私问答 /
    # 模拟面试教练轨道）。到期日 2026-12-31，届时按域拆出：
    #   test_append_profile_entries → 自建板块 / 内置板块 / 幂等 三片
    #   test_apply_greeting_and_privacy_qa → 招呼语闸门 / 隐私脱敏 两片
    #   test_interview → 教练轨道 / 报告附录 两片（这部分与生产代码 interview.py
    #   的拆分同批处理，避免测试与实现各拆一半）
    "backend/tests/test_append_profile_entries.py": Exemption(
        "二开加逐条补入用例（自建/内置/幂等），到期后按取数路径拆三片", _FORK_BACKSTOP
    ),
    "backend/tests/test_apply_greeting_and_privacy_qa.py": Exemption(
        "二开加招呼语闸门与隐私问答用例，到期后按域拆两片", _FORK_BACKSTOP
    ),
    "backend/tests/test_interview.py": Exemption(
        "二开加教练轨道用例，与 interview.py 拆分同批处理", _FORK_BACKSTOP
    ),
    # 合并上游 2.1.0（2026-11-13）：上游 451 行 + 二开的准入/投递结果用例 = 526。
    # 与上面的 ApplyQueuePanel.tsx 同屏，界面拆分时用例跟着一起拆。
    "frontend/src/features/apply/ApplyQueuePanel.test.tsx": Exemption(
        "合并后 526 行：上游已到 451，二开加准入提示与投递结果列用例；与同屏组件同批拆",
        _FORK_BACKSTOP,
    ),
}

# 书面豁免清单（路径相对仓库根；理由必须具体，禁止「暂缓拆分」式空话）
_EXEMPTIONS: dict[str, Exemption] = {
    # JS 资源字符串（表单快照/焦点面板脚本），两脚本共享
    # _CONTROL_HELPERS_JS，逐字符协议契约由 canary 测试钉死，拆分收益为负。
    "backend/app/services/webform/engine/scripts.py": Exemption(
        "内嵌 JS 页面协议资源，非逻辑", _STRUCTURED_BACKSTOP
    ),
    # LiveSession 的轮询/AI/写值核心读取 MAX_AI_CALLS/fill_current_page 等
    # 模块全局，被 test_webform_live 在 live 模块命名空间上 monkeypatch；
    # 搬走即静默失效（test_webform_live:984-1010 是哨兵）。
    "backend/app/services/webform/live.py": Exemption(
        "monkeypatch 钉死模块命名空间", _STRUCTURED_BACKSTOP
    ),
    # FormEngine 单一类内聚体，拆分只能做成 mixin 碎片化，无职责缝。
    "backend/app/services/webform/engine/core.py": Exemption(
        "单一类内聚，无拆分缝", _STRUCTURED_BACKSTOP
    ),
    # install_live_control_script 主体是单一注入脚本字符串（canary 整脚本
    # 断言），且 _load_face_data_uri 被 patch、_ASSET_DIR 为 __file__ 深度耦合。
    "backend/app/services/webform/live_control.py": Exemption(
        "patch + __file__ + 单一脚本资源", _STRUCTURED_BACKSTOP
    ),
    # 上一轮拆分后的编排核心；captures_dir/get_task_runner 被模块属性
    # patch。触发条件：>650 行或新增批次类型时迁出 StopAwareCdpClient。
    "backend/app/services/apply/task_runner.py": Exemption(
        "编排核心 + 两类模块属性 patch", _STRUCTURED_BACKSTOP
    ),
    # Wave3 拆分后的页面组合层（handlers + 会话持久化 + busy 联合态 +
    # 弹层组合），与 live.py 同等待遇的组合层豁免。
    "frontend/src/pages/WebFormPage.tsx": Exemption(
        "页面组合层（编排职责单一）", _STRUCTURED_BACKSTOP
    ),
    # 2026-10-12 AI 提速批接入共享连接池（client_pool）后各 +9 行（511/512 vs 500）。
    # 两文件是协议编排热点：monkeypatch 落点密集（payload/_build_payload/_client/
    # 模块级 retry 等），拆出"HTTP 调用层"会把重试/降级/用量接线的上下文切成两半。
    # 触发条件：>600 行或下次功能改动时先把传输层（_client/_timeout/_headers/_endpoint）
    # 迁入独立模块（届时本豁免撤销）。
    "backend/app/services/llm/openai_compat.py": Exemption(
        "过线 12 行，协议编排热点 + patch 落点密集", _STRUCTURED_BACKSTOP
    ),
    "backend/app/services/llm/anthropic.py": Exemption(
        "过线 11 行，协议编排热点 + patch 落点密集", _STRUCTURED_BACKSTOP
    ),
    # ---- 2026-10-13 生产审计会话：多 PR 叠加增长的声明式豁免（到期 2026-11-15）----
    # 以下三文件在本审计会话被 PR-02/03/07/08/09/10/11/13 多批同时改大
    # （datasets：数据集身份贯穿；resume_generator：硬 deadline/用量汇总；
    #   resume_risk：隐私最小化与降级契约）。
    # 行为已被各自批次的新增测试钉住；立即拆分会把「拆分」与「本会话行为修改」
    # 混在同一批，风险高。拆分留待专门批次（逐文件独立方案），到期不续期即红。
    # （tracker.py 与 ApplyRecordsPanel.tsx 两条豁免已于专门拆分批执行并删除：
    #   tracker 拆出 tracker_query/tracker_csv，ApplyRecordsPanel 拆出展示子组件。
    #   datasets.py / resume_generator.py / resume_risk.py 三条豁免也已于专门
    #   拆分批执行并删除：datasets 拆出 datasets_admin，resume_generator 拆出
    #   resume_generator_prompts，resume_risk 拆出 resume_risk_rules 与
    #   resume_risk_outbound——均为纯搬迁，monkeypatch 落点留在原模块。
    #   scripts 的两条（seed_demo_data / measure_api_perf）也已按到期日（2026-11-15）
    #   执行并删除：seed_demo_data 按数据域拆 scripts/demo_data/（8 个模块），
    #   measure_api_perf 拆 scripts/perf_slo|perf_env|perf_fixture|perf_measure——
    #   均为纯搬迁，脚本入口路径、CLI 参数与 --help 输出逐字不变。）
    # ---- S1（2026-10-22）：CSS 首次纳入预算时的历史存量（到期 2026-12-31）----
    # 这 5 个样式表在此前版本完全不在扫描范围（SCAN_SUFFIXES 无 .css），从未被拦过；
    # S1 只把它们变成「可见但暂时豁免」，挡住继续增长，不要求立即拆分。
    # 拆分必须平铺在 frontend/src/styles/ 下（禁止子目录，否则 antdOverrideGuard 的
    # 非递归 readdirSync 会看不见新文件），方案见行数预算审计报告 §6.1 / §6.5。
    #
    # 已按 2026-12-31 到期日执行拆分（样式表拆分批），**CSS 豁免清单现为空**：
    #   styles/modules.css   2164 行 → 聚合清单 + modules-{dialog,webform,workspace,interview,
    #                        templates,layout,home}.css（按文件内 12 个分段标题切 7 片）
    #   styles/base.css      1039 行 → 聚合清单 + base-{shell,guide,header,tasks,panels}.css
    #   styles/resume.css     925 行 → 聚合清单 + resume-{canvas,editor,panels}.css（按分段切）
    #   features/tou-tou/tou-tou.css 554 行 → 聚合清单 + styles/tou-tou-{orb,cards}.css
    #   styles/tracker.css    514 行 → 聚合清单 + tracker-{board,form}.css（按分段标题切）
    # 全部为纯搬迁（分片首尾拼接与拆分前原文逐字节一致），选择器 / 声明 / 媒体查询 /
    # 层叠顺序未变；`@import` 位于各聚合文件最前，入口仍是 index.css 与 TouTouOrb.tsx
    # 各自的那一条 import，没有第二套入口。
    # ---- 二开移植（2026-11-08）：上游 v2.0.0 基线全绿，这些是本地二开期间长起来的 ----
    #
    # 口径：**上游基线（d893243）逐个实测未超线**，超线全部来自本次 1.x 二开移植
    # （投递台 / 模拟面试教练 / 覆盖清单逐条补入 / 画像导入 / 板块显隐）。到期日统一
    # 2026-12-31：届时按"先拆行为、后拆文件"的次序处理，不与其它改动混批。
    #
    # 不立即拆分的理由（逐文件写具体，不写「暂缓拆分」）：
    # - apply.py / task_apply.py / browser_manager.py / job_match.py / InterviewPage.tsx /
    #   modules-interview.css：二开在这些文件里做的是**在既有职责内加分支**（招呼语闸门、
    #   前往投递换专用浏览器、教练轨道），拆开会让"一条业务链路"横跨两个模块，
    #   与 1.x 保持可回退的目标相冲突。
    # - portrait_import.py / interview.py（后端 api）：二开新增的整块能力（画像导入、
    #   教练参考答案落库），本可以作为独立模块拆出——列为到期日后的首选拆分对象。
    # - document_html.py / resume_profile_append.py：**本次刚过线**（503 / 518），
    #   document_html 只多 3 行（section 级 hidden 过滤），append 多的是双路径取数与
    #   幂等注释。这两条必须在下一批改动前处理掉，否则会继续借势增长。
    "backend/app/api/apply.py": Exemption(
        "二开加招呼语闸门/失败分类分支，拆分会切断单条投递链路", _FORK_BACKSTOP
    ),
    "backend/app/api/interview.py": Exemption(
        "二开加教练参考答案端点（整块能力，到期后优先拆出独立模块）", _FORK_BACKSTOP
    ),
    "backend/app/services/apply/task_apply.py": Exemption(
        "二开加站点适配分支，与 task_runner 同一条执行链", _FORK_BACKSTOP
    ),
    # browser_manager.py 的豁免已在合并上游 2.1.0（2026-11-13）时删除：合并后实测
    # 492 行 ≤ 500，原来的条目变成幽灵豁免。上游把投递浏览器那段落抽走后腾出了空间。
    "backend/app/services/job/job_match.py": Exemption(
        "二开加平台派生筛选（platform.py 已拆出），剩余为匹配主流程", _FORK_BACKSTOP
    ),
    "backend/app/services/profile/portrait_import.py": Exemption(
        "二开新增整块能力，到期后优先整体拆为 portrait_* 子模块", _FORK_BACKSTOP
    ),
    "backend/app/services/resume/document_html.py": Exemption(
        "本次刚过线 3 行（section 级 hidden 过滤），下批改动前必须处理", _FORK_BACKSTOP
    ),
    "backend/app/services/resume/resume_profile_append.py": Exemption(
        "本次刚过线 18 行（自建/内置双路径 + 幂等注释），下批改动前必须处理", _FORK_BACKSTOP
    ),
    "frontend/src/pages/InterviewPage.tsx": Exemption(
        "二开加教练入口与报告附录渲染，与面试页状态耦合", _FORK_BACKSTOP
    ),
    "frontend/src/styles/modules-interview.css": Exemption(
        "二开加教练卡片样式 74 行，与面试模块同一分段", _FORK_BACKSTOP
    ),
    # ---- 合并上游 2.1.0（2026-11-13）：合并后逐个实测"单侧未超、合起来超" ----
    #
    # 口径与上一段相同：**两边各自实测都在预算内**，超线全部来自"双方在同一文件里
    # 各加了一段"（上游改周边 + 我们加列/加分支）。合并期间拆文件会把冲突解决与
    # 结构重构混在一批，回滚粒度变差，所以本批只登记、不拆。
    #
    # 到期日 2026-12-31，与二开移植那批同批处理。逐文件说明为什么现在不拆：
    # - job_hunt_tasks.py：整条「采集→落候选→补 JD→建评分任务」的编排在这一个文件里，
    #   拆开会让一次采集跨两个模块（同 apply.py 的理由）。
    # - settings.py / _site_browser.py / interview.py：上游在本批把三个文件都推到 499
    #   左右（settings 479 / _site_browser 455 / interview 499），我们各自又加了几行；
    #   拆它们属于上游的结构问题，跟着上游节奏走比自己拆更省冲突。
    # - NativeJobHuntView.tsx / ApplyQueuePanel.tsx / JobsPage.tsx / apply.css：界面上
    #   一屏的编排（工具栏 + 表格 + 弹窗），拆成两半会让"一条交互横跨两个文件"。
    # - ApplyQueuePanel.test.tsx：与上一条同屏，用例跟着界面走。
    # - scripts/fork_gate.py：二开闸门脚本，命令清单是**顺序契约**（按 README 里的
    #   执行次序），拆成多个模块会让"跑哪几条、什么顺序"散落。
    "backend/app/api/job_hunt_tasks.py": Exemption(
        "二开采集全链路编排（采集→落候选→补JD→评分）在同一文件，拆开会切断单次采集", _FORK_BACKSTOP
    ),
    "backend/app/api/settings.py": Exemption(
        "合并后 502 行：上游已到 479，二开加采集相关设置读写；拆它属上游结构问题", _FORK_BACKSTOP
    ),
    "backend/app/services/apply/_site_browser.py": Exemption(
        "合并后 502 行：上游已到 455，二开加投递专用浏览器实例隔离", _FORK_BACKSTOP
    ),
    "backend/app/services/interview/interview.py": Exemption(
        "合并后 505 行：上游已到 499，二开加教练参考答案落库", _FORK_BACKSTOP
    ),
    # NativeJobHuntView.tsx 的豁免已删除（2026-11-13）：把「数据源与动作」那一区
    # 抽成 HuntSourceRow 之后降到 463 行，原条目成了幽灵豁免。
    "frontend/src/features/apply/ApplyQueuePanel.tsx": Exemption(
        "合并后 533 行：上游已到 481，二开加准入提示与投递结果列", _FORK_BACKSTOP
    ),
    "frontend/src/pages/JobsPage.tsx": Exemption(
        "合并后 511 行：上游已到 495，二开加导入时间列与候选抽屉", _FORK_BACKSTOP
    ),
    "frontend/src/styles/apply.css": Exemption(
        "合并后 501 行：上游已到 466，二开加投递结果列样式", _FORK_BACKSTOP
    ),
}

# scripts/（*.py，预算 800）的豁免清单：**当前为空**。
# 2026-10-22 拆分批已按到期日（2026-11-15）执行并删除最后两条
# （scripts/seed_demo_data.py、scripts/measure_api_perf.py，见上方历史记录）：
# 拆分后各文件行数均 ≤400，远低于 800 预算，不再需要任何豁免。
_SCRIPTS_EXEMPTIONS: dict[str, Exemption] = {
    # 合并上游 2.1.0（2026-11-13）：937 行。二开闸门脚本，命令清单是**顺序契约**
    # （README 里的执行次序就是它），拆成多模块会让"跑哪几条、什么顺序"散落。
    # 到期日与上方 _FORK_BACKSTOP 同批处理。
    "scripts/fork_gate.py": Exemption(
        "二开闸门脚本，命令清单是顺序契约，拆分会打散执行次序", _FORK_BACKSTOP
    ),
}

# desktop/（*.js，预算 500）：实测最大文件 470 行，零豁免起步——新增长文件
# 必须自觉登记豁免 + 到期日。
_DESKTOP_EXEMPTIONS: dict[str, Exemption] = {}


def _count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 20), b""))


def _find_over_budget(
    paths: list[Path], budget: int, exemptions: dict[str, Exemption]
) -> list[str]:
    """对给定文件清单做预算检查，返回超限文件描述（豁免过的跳过）。"""
    offenders: list[str] = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in exemptions:
            continue
        lines = _count_lines(path)
        if lines > budget:
            offenders.append(f"{rel} = {lines} 行")
    return offenders


def _missing_exemptions(exemptions: dict[str, Exemption]) -> list[str]:
    return sorted(rel for rel in exemptions if not (REPO_ROOT / rel).exists())


def _ghost_exemptions(
    exemptions: dict[str, Exemption], budget: int, root: Path = REPO_ROOT
) -> list[str]:
    """返回「文件仍存在但已不超预算」的豁免条目（S3：幽灵豁免）。

    不存在的文件由 ``_missing_exemptions`` 负责；这里只处理「拆完了忘删条目」——
    否则白名单只会越来越长，没人知道哪条还有效。
    """
    ghosts: list[str] = []
    for rel, exemption in exemptions.items():
        path = root / rel
        if not path.exists():
            continue
        lines = _count_lines(path)
        if lines <= budget:
            ghosts.append(f"{rel} = {lines} 行 ≤ {budget}（理由：{exemption.reason}）")
    return sorted(ghosts)


def _collect(root: str, suffixes: set[str], excluded_dirs: set[str] = frozenset()) -> list[Path]:
    base = REPO_ROOT / root
    assert base.exists(), f"扫描根目录不存在：{base}"
    paths: list[Path] = []
    for path in sorted(base.rglob("*")):
        if path.suffix not in suffixes:
            continue
        if any(part in excluded_dirs for part in path.relative_to(base).parts[:-1]):
            continue
        paths.append(path)
    return paths


def test_production_files_stay_under_line_budget() -> None:
    offenders: list[str] = []
    missing = _missing_exemptions(_EXEMPTIONS)
    paths: list[Path] = []
    for root in SCAN_ROOTS:
        paths.extend(
            path
            for path in _collect(root, SCAN_SUFFIXES)
            if not any(marker in path.name for marker in TEST_NAME_MARKERS)
        )
    offenders.extend(_find_over_budget(paths, LINE_BUDGET, _EXEMPTIONS))
    assert not missing, f"豁免清单里有已不存在的文件（请清理）：{missing}"
    assert not offenders, (
        f"{len(offenders)} 个生产文件超过 {LINE_BUDGET} 行预算：\n"
        + "\n".join(offenders)
        + "\n请拆分，或在 test_file_size_budget._EXEMPTIONS 登记书面豁免理由与到期日。"
    )


def test_test_files_stay_under_line_budget() -> None:
    """测试文件同样受 500 行预算约束（WaveT 拆分后的守门测试）。"""
    offenders: list[str] = []
    missing = _missing_exemptions(_TEST_EXEMPTIONS)
    paths: list[Path] = []
    for pattern in TEST_SCAN_GLOBS:
        paths.extend(sorted(REPO_ROOT.glob(pattern)))
    offenders.extend(_find_over_budget(paths, LINE_BUDGET, _TEST_EXEMPTIONS))
    assert not missing, f"测试豁免清单里有已不存在的文件（请清理）：{missing}"
    assert not offenders, (
        f"{len(offenders)} 个测试文件超过 {LINE_BUDGET} 行预算：\n"
        + "\n".join(offenders)
        + "\n请拆分，或在 test_file_size_budget._TEST_EXEMPTIONS 登记书面豁免理由与到期日。"
    )


def test_scripts_stay_under_line_budget() -> None:
    """scripts/（*.py）受 800 行预算约束（PR-18 扩面；CLI 脚本结构性长度，见模块注释）。"""
    offenders = _find_over_budget(
        _collect(SCRIPTS_ROOT, SCRIPTS_SUFFIXES), SCRIPTS_BUDGET, _SCRIPTS_EXEMPTIONS
    )
    missing = _missing_exemptions(_SCRIPTS_EXEMPTIONS)
    assert not missing, f"scripts 豁免清单里有已不存在的文件（请清理）：{missing}"
    assert not offenders, (
        f"{len(offenders)} 个 scripts 文件超过 {SCRIPTS_BUDGET} 行预算：\n"
        + "\n".join(offenders)
        + "\n请拆分，或在 test_file_size_budget._SCRIPTS_EXEMPTIONS 登记书面豁免理由与到期日。"
    )


def test_desktop_files_stay_under_line_budget() -> None:
    """desktop/（*.js，排除 node_modules/out/payload 等）受 500 行预算约束（PR-18 扩面）。"""
    offenders = _find_over_budget(
        _collect(DESKTOP_ROOT, DESKTOP_SUFFIXES, DESKTOP_EXCLUDED_DIRS),
        DESKTOP_BUDGET,
        _DESKTOP_EXEMPTIONS,
    )
    missing = _missing_exemptions(_DESKTOP_EXEMPTIONS)
    assert not missing, f"desktop 豁免清单里有已不存在的文件（请清理）：{missing}"
    assert not offenders, (
        f"{len(offenders)} 个 desktop 文件超过 {DESKTOP_BUDGET} 行预算：\n"
        + "\n".join(offenders)
        + "\n请拆分，或在 test_file_size_budget._DESKTOP_EXEMPTIONS 登记书面豁免理由与到期日。"
    )


def test_exemption_reasons_are_documented() -> None:
    """豁免必须带理由——防空话式白名单（如「暂缓拆分」）。"""
    vague = {"todo", "tbd", "暂缓", "待定", "later", "wip"}
    for exemptions in (_EXEMPTIONS, _TEST_EXEMPTIONS, _SCRIPTS_EXEMPTIONS, _DESKTOP_EXEMPTIONS):
        for rel, exemption in exemptions.items():
            assert exemption.reason.strip(), f"豁免缺理由：{rel}"
            assert exemption.reason.strip().lower() not in vague, (
                f"豁免理由是空话：{rel} -> {exemption.reason!r}"
            )


def test_exemptions_carry_expiry_and_are_not_expired() -> None:
    """豁免必须带到期日，且到期日不得早于今天（PR-18：防空无声续期）。"""
    today = datetime.date.today()
    stale: list[str] = []
    for exemptions in (_EXEMPTIONS, _TEST_EXEMPTIONS, _SCRIPTS_EXEMPTIONS, _DESKTOP_EXEMPTIONS):
        for rel, exemption in exemptions.items():
            try:
                expires = datetime.date.fromisoformat(exemption.expires)
            except ValueError as exc:
                raise AssertionError(
                    f"豁免到期日不是 ISO 日期（YYYY-MM-DD）：{rel} -> {exemption.expires!r}"
                ) from exc
            if expires < today:
                stale.append(f"{rel}（到期 {expires}，理由：{exemption.reason}）")
    assert not stale, (
        f"{len(stale)} 条豁免已到期，必须拆分或显式续期（改理由 + 新到期日）：\n" + "\n".join(stale)
    )


def test_exemptions_only_for_over_budget_files() -> None:
    """S3：豁免只能给「确实超预算」的文件；拆分完成后忘删条目即变红。"""
    registries = (
        ("_EXEMPTIONS", _EXEMPTIONS, LINE_BUDGET),
        ("_TEST_EXEMPTIONS", _TEST_EXEMPTIONS, LINE_BUDGET),
        ("_SCRIPTS_EXEMPTIONS", _SCRIPTS_EXEMPTIONS, SCRIPTS_BUDGET),
        ("_DESKTOP_EXEMPTIONS", _DESKTOP_EXEMPTIONS, DESKTOP_BUDGET),
    )
    ghosts: list[str] = []
    for name, exemptions, budget in registries:
        for ghost in _ghost_exemptions(exemptions, budget):
            ghosts.append(f"{name}: {ghost}")
    assert not ghosts, (
        f"{len(ghosts)} 条豁免指向的文件已不再超预算（幽灵豁免），请同批删除：\n"
        + "\n".join(ghosts)
    )


def test_ghost_exemption_detector_flags_under_budget(tmp_path: Path) -> None:
    """守卫自检：检测器必须真的能抓到幽灵豁免（防止空转的假绿）。"""
    (tmp_path / "small.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "big.py").write_text("x = 1\n" * 3, encoding="utf-8")
    exemptions = {
        "small.py": Exemption("测试用：已拆完仍留着条目", "2099-01-01"),
        "big.py": Exemption("测试用：确实超线", "2099-01-01"),
        "gone.py": Exemption("测试用：文件不存在，交给 _missing_exemptions", "2099-01-01"),
    }
    ghosts = _ghost_exemptions(exemptions, 2, root=tmp_path)
    assert len(ghosts) == 1, ghosts
    assert "small.py = 1 行 ≤ 2" in ghosts[0]
