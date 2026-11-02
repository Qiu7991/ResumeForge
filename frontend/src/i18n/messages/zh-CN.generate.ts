// SPDX-License-Identifier: Apache-2.0
/**
 * 生成配置阶段（GenerationConfigStage）：模型未配置提示、通用/岗位两种生成口径的说明、
 * 简历名称、美化档位说明、篇幅与版式、职业场景标题、补充要求，以及底部动作。
 *
 * 顶部「当前模型」提示（`generate.config.model-hint` / `model-unknown`）与生成任务文案仍在
 * `zh-CN.workbench.ts`（生成弹窗与后台任务共用），这里只放本阶段新增的 key；通用动作
 * 「取消」复用 `common.action.cancel`，不在领域包里复制。
 */
const generate = {
  // ── 顶部提示 ──────────────────────────────────────────────────
  "generate.config.llmMissing":
    "尚未配置大模型 API，请先到「设置」页完成配置（支持 DeepSeek / 豆包 / Kimi / OpenAI 等）",
  "generate.config.jobHint":
    "系统会根据目标岗位的 JD，从完整个人资料与经历总结文件中筛选并排序相关信息；原始资料不会被修改。",
  "generate.config.generalHint":
    "通用简历不针对任何岗位：系统会使用当前方案包含的板块（只受篇幅预算限制），保留各方向的经历与技能；原始资料不会被修改。",

  // ── 简历名称（仅通用简历显示；留空由后端按约定命名）────────────
  "generate.config.titleName": "简历名称",
  "generate.config.titlePlaceholder": "留空则自动命名为「姓名-通用简历-时间」",

  // ── 内容美化 ──────────────────────────────────────────────────
  "generate.base.title": "底稿",
  "generate.base.placeholder": "选择底稿简历",
  "generate.base.useProfile": "不使用底稿（从「我的资料」重新生成）",
  "generate.base.inheritLayout": "沿用底稿的模板与版式",
  "generate.base.inheritLayoutHint": "关闭后可单独挑模板",
  "generate.base.hintSelected":
    "将以这份简历为底稿：复制它的正文，再按岗位 JD 调整取舍与表达；底稿本身不会被修改，生成结果是一条新记录。",
  "generate.base.hintNone":
    "选一份已生成的简历当底稿，比「从资料重写」更能保住你已经改好的措辞；不选则按原来的方式从资料生成。",
  "generate.base.enhanceDisabledHint":
    "已选底稿：不再做「美化拓展」，模型只在底稿上按岗位做取舍与表达调整。",
  "generate.config.headingJob": "岗位适配与内容美化",
  "generate.config.headingGeneral": "内容美化",
  "generate.config.enhanceJob": "根据岗位要求美化拓展经历",
  "generate.config.enhanceGeneral": "用资料里的总结文件补足经历细节",
  "generate.config.enhanceJobHint":
    "基于已有经历和总结文件补足表达细节，突出与岗位相关的能力，不修改个人资料原文。",
  "generate.config.enhanceGeneralHint":
    "基于已有经历和总结文件补足表达细节，突出资料本身的重点，不修改个人资料原文。",
  "generate.config.enhanceOffHint": "关闭后仅筛选和整理原有资料，不进行拓展。",

  // ── 篇幅与版式 ────────────────────────────────────────────────
  "generate.config.layoutSection": "篇幅与版式",
  "generate.config.layoutHint":
    "默认 1 页 A4 + 标准字号。生成后如果内容塞不下，可以在预览里一键增加页数或缩小字号，不必重新生成。",
  /** 岗位广场的生成配置只让定 5 个参数，其余版式生成后去简历界面调。 */
  "generate.config.layoutHintEssential":
    "这里只定模板、篇幅、简历语言与字体；版式预设、板块顺序、字号行距边距等，生成后在简历界面随时可调。",

  // ── 补充要求 ──────────────────────────────────────────────────
  "generate.config.extraRequirements": "补充要求（选填）",
  "generate.config.extraPlaceholder":
    "例如：突出后端性能优化经历；不要出现「负责…」这类空泛表述；把实习经历放在教育经历前面。",
  "generate.config.extraHint":
    "这段要求会附在生成提示词后面，只影响表达方向；事实锚定、篇幅上限和防虚构规则不变。",

  // ── 底部动作 ──────────────────────────────────────────────────
  "generate.config.start": "开始生成",
  "generate.config.analyze": "先看匹配报告",
  "generate.config.directStart": "直接生成",
  "generate.config.analyzing": "正在分析岗位与资料…",

  // ── 岗位匹配报告 ──────────────────────────────────────────────
  "generate.plan.title": "岗位匹配报告",
  "generate.plan.subtitle":
    "先确认每条岗位要求由哪个项目/事实来证明，再按这份计划生成；可迁移的会明确标注，不会写成直接经验。",
  "generate.plan.analyzingHint": "正在拆解 JD 并核对资料库里的项目与事实，通常需要 20–60 秒。",
  "generate.plan.analysisFailed": "生成匹配报告失败",
  "generate.plan.coverage": "覆盖情况",
  "generate.plan.coverage.direct": "直接证据",
  "generate.plan.coverage.transferable": "可迁移",
  "generate.plan.coverage.gap": "缺口",
  "generate.plan.requirement": "要求",
  "generate.plan.weight": "权重 {weight}",
  "generate.plan.match.direct": "直接",
  "generate.plan.match.transferable": "可迁移",
  "generate.plan.match.none": "无证据",
  "generate.plan.ref.project": "项目",
  "generate.plan.ref.experience": "经历",
  "generate.plan.ref.claim": "事实",
  "generate.plan.selectedCount": "已选 {count} 条证据",
  "generate.plan.quotes": "可引用原文",
  "generate.plan.noEvidence": "这条要求暂时没有可核对证据，生成时不会硬写。",
  "generate.plan.gapHint":
    "缺口不代表不能投；生成时会用相邻能力靠拢，但不会声称你具备这条要求。",
  "generate.plan.warnings": "需要留意的核对项",
  "generate.plan.action.back": "返回修改配置",
  "generate.plan.action.skip": "跳过报告，直接生成",
  "generate.plan.action.generate": "按此方案生成",
  "generate.plan.action.saving": "正在保存选择…",
  "generate.plan.action.reanalyze": "重新分析",
  "generate.plan.empty": "模型没有拆出可用的岗位要求，请重试或直接生成。",
} as const;

export default generate;
