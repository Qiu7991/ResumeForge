// SPDX-License-Identifier: Apache-2.0
/**
 * Display names the resume template catalog (`GET /api/resumes/templates`) sends in
 * Chinese: the built-in format presets. Section names and font size tiers reuse keys
 * from their own domains (`editor.section.*`, `resume.fontScale.*`).
 */
const enumsResumeCatalog = {
  "enumsResumeCatalog.formatPreset.standard": "Standard",
  "enumsResumeCatalog.formatPreset.compact": "Compact",
  "enumsResumeCatalog.formatPreset.spacious": "Spacious",
  "enumsResumeCatalog.formatPreset.mono_accent": "Monochrome accent",
  "enumsResumeCatalog.formatPresetDescription.standard":
    "Leaves the template's own layout unchanged",
  "enumsResumeCatalog.formatPresetDescription.compact":
    "Tighter line height and spacing with smaller margins - good for fitting one page",
  "enumsResumeCatalog.formatPresetDescription.spacious":
    "Larger line height and whitespace for a more relaxed look",
  "enumsResumeCatalog.formatPresetDescription.mono_accent":
    "A quiet dark-grey accent for formal, conservative applications",
  // Built-in resume templates (`RESUME_TEMPLATES[].name`); a user-imported template carries
  // its own name and must never be translated.
  "enumsResumeCatalog.template.classic": "Classic",
  "enumsResumeCatalog.template.modern": "Modern",
  "enumsResumeCatalog.template.compact": "Compact",
  "enumsResumeCatalog.template.elegant": "Elegant",
  "enumsResumeCatalog.template.technical": "Technical",
  "enumsResumeCatalog.template.minimal": "Minimal",
  "enumsResumeCatalog.template.scholar": "Academic",
  "enumsResumeCatalog.template.editorial": "Editorial",
  "enumsResumeCatalog.template.split": "Two-column",
  // Same templates' one-line descriptions (`RESUME_TEMPLATES[].description`).
  "enumsResumeCatalog.templateDescription.classic":
    "Deep-blue headings with a left colour bar; a steady, general-purpose layout",
  "enumsResumeCatalog.templateDescription.modern":
    "Teal accents and rounded tags; suits internet-industry roles",
  "enumsResumeCatalog.templateDescription.compact":
    "Thin separators and tight spacing; for content-heavy resumes that must fit one page",
  "enumsResumeCatalog.templateDescription.elegant":
    "Centred headings with serif type and generous whitespace; suits humanities, business and management roles",
  "enumsResumeCatalog.templateDescription.technical":
    "Colour-block headings with monospaced meta; high density, built for engineering roles",
  "enumsResumeCatalog.templateDescription.minimal":
    "Black and grey only, with hierarchy carried by type size; no colour blocks or decoration",
  "enumsResumeCatalog.templateDescription.scholar":
    "Pure black and white, bold headings with hairline rules, short entries in three columns; for research and academic roles",
  "enumsResumeCatalog.templateDescription.editorial":
    "Serif type with hairline dividers; suits humanities, content and management roles",
  "enumsResumeCatalog.templateDescription.split":
    "Two-column body with high density; for resumes with many roles and skills",
  "enumsResumeCatalog.template.php": "PHP backend",
  "enumsResumeCatalog.template.java": "Java",
  "enumsResumeCatalog.template.node": "Node.js",
  "enumsResumeCatalog.template.web": "Web frontend",
  "enumsResumeCatalog.template.ios": "iOS",
  "enumsResumeCatalog.template.android": "Android",
  "enumsResumeCatalog.template.cpp": "C/C++ systems",
  "enumsResumeCatalog.template.architect": "Architect",
  "enumsResumeCatalog.template.dev": "General tech",
  "enumsResumeCatalog.templateDescription.php": "Violet accents and soft section titles for PHP and backend roles",
  "enumsResumeCatalog.templateDescription.java": "Brick-red accents and a left bar, a steady enterprise look for Java and server roles",
  "enumsResumeCatalog.templateDescription.node": "Grass-green accents, underline titles and monospace details for Node.js and full-stack roles",
  "enumsResumeCatalog.templateDescription.web": "Indigo accents and a left bar, clean and versatile for web frontend roles",
  "enumsResumeCatalog.templateDescription.ios": "Graphite minimalism with generous whitespace and plain skill lists for iOS roles",
  "enumsResumeCatalog.templateDescription.android": "Android-green filled section titles and a tinted header for mobile roles",
  "enumsResumeCatalog.templateDescription.cpp": "Steel-blue accents, monospace details and filled titles for C/C++, embedded and systems roles",
  "enumsResumeCatalog.templateDescription.architect": "Deep purple accents and centered serif titles for architects and tech leads",
  "enumsResumeCatalog.templateDescription.dev": "Neutral blue-grey and soft section titles, a direction-neutral technical layout",
} as const;

export default enumsResumeCatalog;
