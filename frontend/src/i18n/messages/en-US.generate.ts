// SPDX-License-Identifier: Apache-2.0
/**
 * Generation config stage (GenerationConfigStage): the missing-model notice, the copy for
 * Job-specific and general generation, Resume name, enhancement hints, length and layout
 * presets, the career scenario heading, additional requirements, and the footer actions.
 *
 * The "current model" hint (`generate.config.model-hint` / `model-unknown`) and the generation
 * task copy stay in `en-US.workbench.ts` (shared with the generation dialog and background
 * tasks). The generic "Cancel" action reuses `common.action.cancel` instead of a copy here.
 */
const generate = {
  "generate.config.llmMissing":
    "No model service is configured yet. Set one up on the Settings page (DeepSeek, Doubao, Kimi, OpenAI and others are supported)",
  "generate.config.jobHint":
    "Based on the target Job's JD, the system selects and ranks relevant details from your full Profile and experience summary files; your original materials are not modified.",
  "generate.config.generalHint":
    "A general Resume targets no specific Job: the system uses the Sections included in the current Plan (constrained only by the page budget) and keeps experience and skills from every direction; your original materials are not modified.",
  "generate.config.titleName": "Resume name",
  "generate.config.titlePlaceholder": "Leave blank to auto-name it “Name - General Resume - Time”",
  "generate.base.title": "Base draft",
  "generate.base.placeholder": "Choose a base draft",
  "generate.base.useProfile": "No base draft (generate from My Profile)",
  "generate.base.inheritLayout": "Inherit the base draft's template and layout",
  "generate.base.inheritLayoutHint": "Turn off to pick a template separately",
  "generate.base.hintSelected":
    "This resume becomes the base: its content is copied and tailored to the job. The draft itself is not modified; the result is a new record.",
  "generate.base.hintNone":
    "Picking an existing resume as the base preserves wording you already polished better than regenerating from your profile. Leave empty to generate from the profile.",
  "generate.base.enhanceDisabledHint":
    "Base draft selected: content enhancement is skipped; the model only tailors the draft to the job.",
  "generate.config.headingJob": "Job tailoring and content enhancement",
  "generate.config.headingGeneral": "Content enhancement",
  "generate.config.enhanceJob": "Enhance and expand experience to match the Job requirements",
  "generate.config.enhanceGeneral":
    "Fill in experience details from the summary files in your Profile",
  "generate.config.enhanceJobHint":
    "Adds wording detail based on your existing experience and summary files, highlights the abilities relevant to the Job, and does not modify your Profile content.",
  "generate.config.enhanceGeneralHint":
    "Adds wording detail based on your existing experience and summary files, highlights what matters in your Profile, and does not modify your Profile content.",
  "generate.config.enhanceOffHint":
    "When off, existing Profile content is only selected and tidied, not expanded.",
  "generate.config.layoutSection": "Length and layout presets",
  "generate.config.layoutHint":
    "Defaults to one A4 page at the standard font size. If the content does not fit after generation, add pages or shrink the font in the preview with one click; no need to regenerate.",
  "generate.config.layoutHintEssential":
    "Only the template, page limit, field language and font are set here; layout presets, section order, font size, line height and margins can be adjusted in the resume editor after generation.",
  "generate.config.extraRequirements": "Additional requirements (optional)",
  "generate.config.extraPlaceholder":
    "e.g. Highlight backend performance work; avoid vague phrases like 'responsible for...'; put internships before education.",
  "generate.config.extraHint":
    "This requirement is appended to the generation prompt and only steers wording; fact anchoring, the page limit and the no-fabrication rules stay unchanged.",
  "generate.config.start": "Start generating",
  "generate.config.analyze": "Preview match report",
  "generate.config.directStart": "Generate directly",
  "generate.config.analyzing": "Analyzing the job and your profile…",
  "generate.plan.title": "Job match report",
  "generate.plan.subtitle":
    "Confirm which project or fact proves each requirement before generating; transferable evidence is labelled and never presented as direct experience.",
  "generate.plan.analyzingHint":
    "Breaking down the JD and checking your projects and facts; usually 20–60 seconds.",
  "generate.plan.analysisFailed": "Could not build the match report",
  "generate.plan.coverage": "Coverage",
  "generate.plan.coverage.direct": "Direct",
  "generate.plan.coverage.transferable": "Transferable",
  "generate.plan.coverage.gap": "Gaps",
  "generate.plan.requirement": "Requirement",
  "generate.plan.weight": "Weight {weight}",
  "generate.plan.match.direct": "Direct",
  "generate.plan.match.transferable": "Transferable",
  "generate.plan.match.none": "No evidence",
  "generate.plan.ref.project": "Project",
  "generate.plan.ref.experience": "Experience",
  "generate.plan.ref.education": "Education",
  "generate.plan.ref.claim": "Fact",
  "generate.plan.selectedCount": "{count} evidence selected",
  "generate.plan.quotes": "Quotable source",
  "generate.plan.noEvidence":
    "No verifiable evidence for this requirement; it will not be invented in the resume.",
  "generate.plan.gapHint":
    "A gap does not block applying; the resume will lean on adjacent strengths without claiming this requirement.",
  "generate.plan.warnings": "Items to double-check",
  "generate.plan.action.back": "Back to settings",
  "generate.plan.action.skip": "Skip report and generate",
  "generate.plan.action.generate": "Generate with this plan",
  "generate.plan.action.saving": "Saving selection…",
  "generate.plan.action.reanalyze": "Analyze again",
  "generate.plan.empty": "No usable requirements were found; retry or generate directly.",
} as const;

export default generate;
