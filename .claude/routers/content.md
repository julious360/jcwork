# content.md — Content Department

Parent: `claude.md`. Scope: capture → voice → publish.

## Skills

- `.claude/skills/transcript-to-newsletter/` — transcript → sectioned newsletter
  (Markdown + inlined HTML email). **Thick**: carries the HTML template and voice guide.
- `.claude/skills/ad-concept-brief/` — reuse for ad copy; same voice constraints.

## Reference files

| File | Use |
|---|---|
| `.claude/skills/transcript-to-newsletter/references/voice.md` | tone rules, banned phrasing |
| `.claude/skills/transcript-to-newsletter/references/newsletter.template.html` | email shell, table-based, inline CSS |
| `.claude/skills/ad-concept-brief/references/brand-tokens.json` | palette, fonts, forbidden claims |
| `agent/config/brand_guide.yaml` | source of truth the tokens JSON mirrors |
| `agent/config/campaign.yaml` | ICP + value proposition; every piece is written to this reader |

## Pipeline

```
YouTube URL ──► os/connectors/youtube_transcript.py ──► memory/inbox/transcripts/YYYY-MM-DD-slug.md
                                                              │
                       claude -p "/transcript-to-newsletter <file>"
                                                              ▼
                                       memory/outbox/newsletters/YYYY-MM-DD-slug.{md,html}
```

Weekly automation: `os/routines/local/weekly-newsletter.sh` (Mon 07:00).

## Voice, in one line

Confident and plain-spoken; concrete over clever; no hype, no exclamation marks,
no "guaranteed / #1 / risk-free / instantly". Full rules in `references/voice.md`.
