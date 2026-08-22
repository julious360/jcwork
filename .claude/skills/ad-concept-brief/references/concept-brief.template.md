# Concept: {{ concept_name }}

- **Pain point (verbatim):** {{ quote }}
- **Source:** {{ subreddit / query / transcript }}
- **Angle:** {{ one sentence — the argument, not the wording }}
- **Distinct from:** {{ recent concept it must not resemble, and why it doesn't }}

## Copy

| Field | Text | Chars |
|---|---|---|
| Primary text | {{ ... }} | {{ n }}/125 |
| Headline | {{ ... }} | {{ n }}/40 |
| Description | {{ ... }} | {{ n }}/30 |
| CTA | {{ Learn more / Get started }} | — |

Destination: `{{ landing_page_url from campaign.yaml }}`

## Visual direction

- **Format:** {{ 1:1 | 4:5 | 9:16 }} · {{ static | video }}
- **Focal point:** {{ the single thing the eye lands on }}
- **Palette use:** background `paper`, subject on `ink`, one `primary` accent,
  `accent` reserved for {{ ... }}
- **Type:** Inter Tight display / Inter body. Text coverage target ≤ 15% (limit 20%).
- **Logo:** {{ corner }}, clear space ≥ cap-height.
- **Do not:** {{ the obvious cliché for this category }}

## Validator expectations

| Check | Expected |
|---|---|
| Aspect ratio | {{ x }} ± 0.02 |
| Min width | ≥ 1080px |
| Palette coverage | ≥ 25% |
| Max ΔE | ≤ 12 |
| Text coverage | ≤ 20% |
| Forbidden claims | 0 |

## Test hypothesis

If {{ ICP }} sees {{ angle }}, CPA lands under {{ target_cpa }} because {{ reason }}.
Kill criteria: spend ≥ 3 × target_cpa with upper CPA bound above `cpa_max`.
