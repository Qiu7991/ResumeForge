// SPDX-License-Identifier: Apache-2.0
/**
 * Apply-settings dialog: intervals, limits, breaker threshold, default greeting and the
 * dedicated browser port.
 *
 * `defaults.hint` is the template for the "factory default" readout; `defaults.on` /
 * `defaults.off` are the two values a switch field can show, so the sentence order stays
 * in the template instead of being glued together in code.
 *
 * The intro paragraph is one key on purpose: the source emphasised "successful
 * applications" with an inline tag, and splitting around it cannot be reordered for
 * English. One complete sentence per locale wins over keeping the emphasis.
 */
const applySettings = {
  "applySettings.defaultResume.label": "Default Resume (optional)",
  "applySettings.defaultResume.extra":
    "Used when a Job has no tailored Resume — lower priority than the job-specific one, higher than none. Changing it also affects items already in the queue.",
  "applySettings.defaultResume.placeholder": "Pick a general Resume (type to search)",
  "applySettings.greetingBaseline.label": "Custom greeting baseline",
  "applySettings.greetingBaseline.extra":
    "Paste your preferred template, structure or tone — you can also state your differentiator (e.g. “most of my projects were built end-to-end with AI tools”). It is the highest-priority constraint, but facts must still come from the Resume; leave empty to use the built-in baseline.",
  "applySettings.greetingReview.label": "Review the greeting before sending",
  "applySettings.greetingReview.extra":
    "When enabled, queued jobs without a confirmed greeting are skipped and marked \"greeting missing\"; the default greeting is never sent on your behalf.",
  "applySettings.title": "Apply settings",
  "applySettings.intro":
    "These settings decide the rhythm and the safety net of applying: jobs wait a random interval between each other, consecutive failures pause the run automatically, and the daily limit only counts successful applications.",

  "applySettings.defaults.on": "On",
  "applySettings.defaults.off": "Off",
  "applySettings.defaults.hint": "Factory default: {value}",

  "applySettings.interval.label": "Interval between jobs (seconds)",
  "applySettings.interval.required": "Enter the interval between jobs",
  "applySettings.jitter.label": "Random jitter (seconds)",
  "applySettings.dailyLimit.label": "Daily limit (successful applications)",
  "applySettings.dailyLimit.required": "Enter the daily limit",
  "applySettings.perTaskLimit.label": "Per-batch limit",
  "applySettings.breaker.label": "Consecutive-failure threshold",

  "applySettings.greeting.label": "Default greeting",
  "applySettings.greeting.extra":
    "Used when a queue entry has no greeting of its own; you can still preview and edit it job by job before applying.",

  "applySettings.site.label": "Current job site",
  "applySettings.site.extra":
    "Only one job site is supported for now, and more will follow; new sites need no manual configuration from you.",
  "applySettings.site.placeholder": "Use the default site",

  "applySettings.browser.label": "Browser used by the apply console",
  "applySettings.browserPort.label": "Debug port of the apply browser",

  "applySettings.skipSameCompany.label": "Apply to only one job per company",
  "applySettings.skipSameCompany.extra":
    'Applies within one batch only: when a company has several jobs in the same batch, only the first is applied to and the rest are marked "Skipped" with a reason; the same company can still be applied to in a later batch. Matching ignores spaces and letter case in the company name, and a failed attempt also counts as "already applied" (the greeting may already have been sent).',

  "applySettings.realGap.label": 'Allow "real gap" jobs into the queue by default',
  "applySettings.realGap.extra":
    "Off by default: jobs that hit a real gap need your per-job confirmation; when turned on they are still flagged in the records.",

  "applySettings.action.save": "Save settings",
  "applySettings.saved": "Apply settings saved",
  "applySettings.saveFailed": "Could not save the apply settings",
  "applySettings.greetingSalutation.label": "Start the greeting with a salutation",
  "applySettings.greetingSalutation.extra":
    "On by default. Turn it off and sentence 1 starts directly with the capability label — BOSS shows only the first 10–18 characters in the message list, and \"Hello,\" uses up 3 of them. Flip it to compare.",


  "applySettings.tab.cadence": "Pacing",
  "applySettings.tab.templates": "Greeting library",
  "applySettings.tab.blocklist": "Block list",

  "applySettings.blocklist.intro":
    "Matching Jobs are stopped at collection, enqueue and apply time. One entry per line; leave it empty to block nothing.",
  "applySettings.blocklist.companies": "Blocked companies",
  "applySettings.blocklist.companiesHint":
    "Compared by company name, ignoring spaces and case. For example: Acme Technologies Ltd.",
  "applySettings.blocklist.keywords": "Blocked keywords",
  "applySettings.blocklist.keywordsHint":
    "Skip a Job when its title or description contains one of these words; at least two characters, so one word cannot block a whole city. For example: outsourcing, on-site vendor",
  "applySettings.blocklist.save": "Save block list",
  "applySettings.blocklist.saved": "Block list saved",
  "applySettings.blocklist.saveFailed": "Could not save the block list",
  "applySettings.blocklist.loadFailed": "Could not load the block list, try again",

  "applySettings.templates.intro":
    "Save greetings you reuse as templates and pick them while editing a queue item. A body may use {company}, {job_title} and {name}.",
  "applySettings.templates.name": "Template name",
  "applySettings.templates.body": "Greeting body",
  "applySettings.templates.namePlaceholder": "For example: general opener",
  "applySettings.templates.bodyPlaceholder":
    "For example: Hello, I am {name}. I saw the {job_title} role and would like to talk.",
  "applySettings.templates.add": "New template",
  "applySettings.templates.remove": "Delete this template",
  "applySettings.templates.save": "Save greeting library",
  "applySettings.templates.saved": "Greeting library saved",
  "applySettings.templates.saveFailed": "Could not save the greeting library",
  "applySettings.templates.loadFailed": "Could not load the greeting library, try again",
  "applySettings.templates.empty":
    "No templates yet - click New template to write one, then pick it while editing a queue item.",
  "applySettings.templates.uses": "Used {count} times",
  "applySettings.templates.needName": "Give the template a name first",
  "applySettings.templates.needBody": "Write the greeting body first",
} as const;

export default applySettings;
