# Advisory punch list — EW_Studio_Collections_V3.0

This session has read-only access to `julious360/EW_Studio_Collections_V3.0` — every
item below is a real, machine-verified finding (`toolkit/uikit/audit.mjs` against the
live repo, this session), but none of it could be applied there directly. Apply by
hand, or re-run with push access attached.

**The zip / `VERSION` / folder-rename hand-off workflow stays exactly as-is** — that
was an explicit decision this session, not an oversight. The one change recommended
(#8) is a guard *in front of* that workflow, not a replacement for it.

Reproduce this whole list any time with:
```bash
node toolkit/uikit/audit.mjs /path/to/EW_Studio_Collections_V3.0
```

## 1. Restore the files the project's own docs say should be there

`README.md` and `DESIGNER-GUIDE.md` reference these as if they exist now; they don't:

| File | Referenced by |
|---|---|
| `CLAUDE.md` | Both — `DESIGNER-GUIDE.md` explicitly tells the reader to point an AI assistant at it *first* |
| `tools/image-annotator.html` | `DESIGNER-GUIDE.md` §5 (the screenshot-annotation workflow) |
| `md/product-blurbs.md` | `README.md`'s structure table |
| `overview.jpg`, `whats-included.jpg` | `README.md` |
| `.gitignore` | `README.md` says `images/`/`references/` are "gitignored" — no `.gitignore` is committed |

`export.sh` and `integrate.sh` are also missing (referenced in `CHANGELOG.md`'s v2.1
entry, the export/versioning workflow) — not machine-flagged above since changelogs
are deliberately excluded from that check (they narrate history and legitimately name
retired files), but confirmed by direct reading this session.

## 2. Fix 9 broken image references on the homepage

`html/index.html` references 9 images under `../links/` that don't resolve — the
"Explore" category icons and one creator photo:

```
explore_Orchestral.png, explore_Vocals & Choirs.png, explore_Drums_ Percussion.png,
explore_Synths & Production.png, explore_Pianos_Keys.png, explore_Cinematic_World.png,
explore_Bands_Brass.png, explore_Effects.png, you-creator_2.jpg
```

## 3. 9 orphaned assets in `links/`

Present, shipped, and referenced by nothing: `cat-brass.jpg`, `cat-choirs.jpg`,
`cat-drums.jpg`, `cat-effects.jpg`, `cat-orchestral.jpg`, `cat-pianos.jpg`,
`cat-synths.jpg`, `cat-world.jpg`, `usecase-creator.jpg`. Given the names (`cat-*` =
category), these look like the *intended* fix for #2 — the "Explore" section may be
supposed to use these files under different names. Worth checking before deleting
either set.

## 4. Version-stamp mismatch, all 4 pages

`VERSION` says `3.0`. The on-page banner on every page (`index.html`,
`producer-collection.html`, `hollywood-collection.html`,
`complete-collection.html`) still renders `v2.1`. The hand-off checklist in
`DESIGNER-GUIDE.md` itself calls for this to be bumped — it wasn't.

## 5. `collections-data.js` has drifted from `collections.json`

`html/assets/collections-data.js` — the generated `window.COLLECTIONS = {...}`
wrapper — no longer matches `data/collections.json`. Someone edited the JSON without
re-running the regenerate step `DESIGNER-GUIDE.md` §2 documents. Whatever changed in
the JSON (pricing? product list?) is **not currently live on the page**.

## 6. Delete the committed `html/_backup/` directory

Manual copies of `index.html`, `campaign.css`, and the three package pages are
checked into git. That's what git itself already does — the directory is redundant
version control layered on top of real version control, and it will silently drift
from the live files over time (it already has).

## 7. Self-host the two remaining Google Fonts

`READ-ME-FIRST.txt` promises *"No install, no internet needed."* Confirmed false:
every page load fetches from `fonts.googleapis.com` (Inter, DM Sans, and on the
homepage, Montserrat too — 12 blocked-request instances across 4 pages × 3
breakpoints in this session's headless test). Tachyon is already self-hosted
correctly as a `.woff2` under `html/assets/fonts/` — do the same for the other three
rather than the `<link>` to Google Fonts.

## 8. Add a gate before `export.sh` zips

The one change to the hand-off workflow. Once `toolkit/uikit/` (or a copy of it) is
reachable from this repo:

```bash
node toolkit/uikit/gate.mjs .   # must pass before export.sh runs
```

This would have caught #4 and #7 automatically before either shipped — both are
exactly the kind of defect a 20-second mechanical check catches and a human review
pass reliably doesn't.

## 9. Horizontal overflow, every page × every breakpoint (12 instances)

Content is wider than the viewport on all 4 pages at all 3 tested breakpoints
(390/834/1440px) — e.g. `index.html` at 1440px renders 1548px of content. Worth a
look at whatever's causing the overflow (a fixed-width element, an image without
`max-width: 100%`, or similar) since it's consistent across every page rather than
isolated to one.

## 10. Contrast — judgment call, not a mechanical failure

30 instances of white text (`#fff`) on the gold/red accent colors falling under the
WCAG AA 4.5:1 threshold — commonly 3.88:1 (white on `#ec4332` red) and as low as
2.1:1–2.47:1 (white on gold/blue tier accents) on real interactive elements: "Buy
Now," "Explore," and the "OP" plugin-count badge, not just decorative text. Not
auto-flagged as build-breaking (contrast can be a deliberate design choice), but
worth a design review given how many instances share the same pattern — this reads
like a systemic accent-color/white-text pairing decision, not scattered one-offs.

---

# Advisory — `julious360/INSTRUCTIONS`

Also read-only this session. Shorter list — this repo's problem isn't broken files,
it's that none of its real content ever fires automatically.

## What's there

Six markdown files, one commit (`Add ... AntiGravity.md`). Five are transcribed notes
from a video ("5 Claude Skills That Make You Unstoppable At Work") — genuinely sound
advice (interrogation method, perspective-shift review, chain-of-documents,
breakdown method, memory stacking). The sixth, `How I build Beautiful $10,000
Websites with AI AntiGravity.md`, is a 660-line design-prompt framework — patterns,
palettes, typography, interaction specs.

## The actual problem

**None of the six files has YAML frontmatter, so none can ever auto-trigger as a
Claude skill.** They're stored as prose someone has to remember to re-read — which,
per this session's own analysis, is exactly the failure mode `05-memory-stacking.md`
describes and recommends fixing. The fix described in that file was never applied to
the file itself.

## What to do with it

The same repair pattern this session applied to `brand-identity` /
`designing-websites` / `creative-director-sterling` in `jcwork`'s
`toolkit/skills/`: convert each of the five method notes into a real skill —
frontmatter with a `name` and a `description` specific enough to trigger on the right
task (not "use this skill for creative work," but naming the concrete situation:
starting a client deliverable with thin context → interrogation-method; reviewing a
finished doc before it goes out → perspective-shift). Reference this project's actual
recurring work (Meta Ads decisions, EastWest campaign copy) as worked examples
instead of generic placeholders, the same way `creative-director-sterling`'s rewrite
replaced roleplay with a concrete watchmaker-logo worked example.

For the 660-line AntiGravity doc: salvage the genuinely reusable parts (the pattern/
palette/typography/interaction structure) into `toolkit/skills/designing-websites`'s
token/CSS pipeline, which already covers the same ground with commands an agent can
actually run — most of the doc's *value* is the design-system thinking, not the
Google Stitch / AntiGravity Desktop App workflow wrapped around it, which
`designing-websites` already replaced for exactly this reason.
