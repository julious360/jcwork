---
name: transcript-to-newsletter
description: Turn a raw transcript (YouTube, podcast, call recording) into a publish-ready newsletter — Markdown plus an inlined-CSS HTML email. Use when asked to write a newsletter, repurpose a video or podcast, or turn long-form content into an issue.
---

# Transcript → Newsletter

Input: a transcript file in `memory/inbox/transcripts/`.
Output: two files in `memory/outbox/newsletters/`, same slug:
`YYYY-MM-DD-slug.md` and `YYYY-MM-DD-slug.html`.

## Procedure

1. Read the transcript. If it is raw ASR, fix only obvious mis-transcriptions of
   product and person names — never smooth the speaker's phrasing away. Their
   phrasing is the asset; it is what makes ad copy convert.
2. Read `references/voice.md`. Every rule there is a hard constraint.
3. Extract, in this order:
   - **One claim.** The single argument the issue makes. If you can't state it in
     one sentence, the transcript has two issues in it — pick one and say so.
   - **Three supports.** Each is a section: a concrete example, a number, or a
     mechanism. No section that only restates the claim.
   - **Verbatim quotes.** At least two, unedited, attributed. These carry the voice.
   - **One takeaway.** Something the reader can do this week.
4. Write the Markdown first. Then fill `references/newsletter.template.html` with it —
   do not write the HTML from scratch, and do not add `<style>` blocks (Gmail strips
   them; the template is table-based with inline CSS for that reason).
5. Mine the leftovers: any pain-point language that didn't make the issue goes to
   `memory/inbox/transcripts/<slug>.pains.md` as candidate ad angles for
   `/ad-concept-brief`.

## Structure (fixed)

| Section | Length | Job |
|---|---|---|
| Subject line | ≤ 55 chars | the claim, no colon-clickbait |
| Preheader | ≤ 90 chars | the second sentence, not a repeat of the subject |
| Cold open | 2–3 sentences | the specific situation, no throat-clearing |
| Section 1–3 | 100–180 words each | one support each, `##` headed |
| Pull quote | 1–2 sentences | verbatim, attributed |
| This week | 3 bullets max | what to actually do |
| Sign-off | 1 sentence | plain |

## Hard limits

- 700–1000 words total. Over 1000 means a section is a second issue — cut it.
- Zero em-dash-driven build-ups, zero "In today's fast-paced…", zero exclamation marks.
- Every number traceable to the transcript. If the speaker said "about a third",
  write "about a third", not "33%".
- Links: max 3, each on its own line in Markdown, each an explicit `<a>` in HTML.

## Self-check

- [ ] Subject ≤ 55 chars, preheader ≤ 90, distinct from each other
- [ ] Word count 700–1000
- [ ] ≥ 2 verbatim quotes, attributed
- [ ] Voice rules in `references/voice.md` all pass
- [ ] HTML renders standalone (no external CSS/JS/fonts, images have `alt` and width)
- [ ] `.pains.md` written with the unused pain language

## Headless

```bash
# one file
claude -p "/transcript-to-newsletter memory/inbox/transcripts/2026-08-21-agency-ops.md" \
  --allowedTools "Read,Write,Bash(ls:*)" --output-format text

# whole inbox, newest first (see os/routines/local/weekly-newsletter.sh)
./os/routines/local/weekly-newsletter.sh
```
