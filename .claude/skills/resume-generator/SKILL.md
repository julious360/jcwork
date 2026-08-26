---
name: resume-generator
description: Build a self-contained, sellable resume-builder web app — a single HTML file with a live-editing form on one side and a polished, print/PDF-ready resume preview on the other, no backend or build step required. Use this whenever the user asks to build/create a "resume builder," "resume generator," "resume maker," "CV builder," or a resume/CV tool or template as a digital product (e.g. for Gumroad, Etsy, a portfolio site, or to hand off to someone else) — even if they just say "make me a resume tool" or reference building quick sellable digital products with Claude. Not for writing or filling in a single person's resume content directly (use plain writing for that) — this skill is specifically for building the reusable *tool* that lets anyone build their own resume.
---

# Resume Generator (digital-product resume builder)

Build a client-side resume-builder web app: a form on the left where someone types
their info, and a polished resume preview on the right that updates live and prints
cleanly to PDF. The whole thing ships as **one HTML file** — no server, no build step,
no external dependencies — so it can be handed to a client, embedded in a course, or
sold as-is as a digital product.

## Start from the bundled template, don't write from scratch

`assets/resume-builder-template.html` is a complete, working implementation:
two-pane layout (form + live preview), repeatable Experience/Education/Projects
entries, a comma-separated Skills field, three visual themes (Classic/Modern/Minimal),
`localStorage` persistence so nobody loses their data on refresh, and print-specific
CSS that hides the editor and lays the resume out on a clean Letter page when the
user hits "Print / Save as PDF."

Copy it to the target output path and customize from there — it's much faster and
more reliable than generating the form-state/localStorage/print-CSS plumbing fresh
each time, and those parts are exactly where bugs hide (an input that doesn't sync
to the preview, a print stylesheet that clips a section, state that vanishes on
reload). Re-use the working mechanics; spend your effort on what actually
differentiates this build:

- **Visuals** — swap the palette, fonts, and accent treatment to match what the user
  asked for (their brand, a niche like "tech resume" or "creative portfolio resume,"
  or just "make it look premium"). Keep all three themes coherent with each other.
- **Sections** — add or rename sections the user needs (e.g. Certifications as its
  own section instead of folded into Projects, a Languages field, a Portfolio-links
  section). Keep the same pattern: a state array + a render function + a form-list
  renderer, mirroring how Experience/Education already work.
- **Copy and defaults** — placeholder text, section labels, and any starter content
  should fit the audience the user described.

Don't rebuild the two-pane layout, the theme system, or the persistence/print
mechanics from zero unless the user explicitly asks for a structurally different
tool (e.g. a multi-step wizard instead of a single form) — in that case still reuse
the render/print/localStorage functions, just restructure the input side.

## Non-negotiables (this is what makes it a usable product, not a demo)

- **Single self-contained file.** Inline `<style>` and `<script>`, no CDN links, no
  build tooling. It must open by double-clicking the `.html` file with nothing else
  installed.
- **ATS-friendly output.** The resume preview is real semantic HTML (`<h2>`, `<ul>`,
  paragraphs) — never render it as an image, canvas, or icon-heavy graphic. Avoid
  multi-column layouts inside the resume itself (tables/columns often scramble text
  extraction in applicant tracking systems); a single-column, top-to-bottom layout is
  the safe default even for the "Modern" theme.
- **Print CSS is a first-class feature, not an afterthought.** Verify `@media print`
  hides every editor control and renders only the resume, sized to `letter` (or `A4`
  if the user is outside the US) with sane margins. This is the actual export path —
  there is no separate "download PDF" button; print-to-PDF via the browser dialog
  *is* the export.
- **Data survives a refresh.** Every field write goes to `localStorage` immediately.
  Confirm this by editing a field, reloading, and checking the value is still there.
- **Looks like a product.** Real typography scale, spacing, and an accent color —
  not default browser form styling. Someone should be willing to pay for this.

## Workflow

1. If the user gave a specific style, audience, or brand, fold that into the theme
   customization now. If they didn't, ship the three bundled themes as-is — don't
   block on asking; a working default beats a stalled question here.
2. Copy `assets/resume-builder-template.html` to the requested output path (ask where
   if unclear — a sensible default is `resume-builder.html` in the current directory).
3. Make the customizations from the "Visuals / Sections / Copy" list above directly
   in the copied file.
4. **Verify it in a real browser before calling it done**, per this project's usual
   bar for UI work: open the file (Playwright headless Chromium is fine in a sandbox),
   fill in a sample entry per section, confirm the preview updates live, confirm
   reload keeps the data, and check the print layout (`page.emulateMedia({media:
   'print'})` or an actual print preview) shows only the resume with nothing clipped
   or overlapping. Fix anything broken before handing it back.
5. Tell the user what you built and how to use it: open the file, fill in the form,
   pick a theme, hit Print / Save as PDF (choose "Save as PDF" as the destination in
   the print dialog).
