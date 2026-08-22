# Voice

Derived from `agent/config/brand_guide.yaml` (`tone`, `forbidden_claims`) and applied
to every outbound word — newsletter, ad copy, landing page.

## Rules

1. **Confident, plain-spoken.** State the thing. "This breaks under load" beats
   "it's worth noting that this may potentially degrade".
2. **Concrete over clever.** A number, a name, or a mechanism in every paragraph.
3. **No hype.** No exclamation marks. No "game-changing", "revolutionary",
   "unlock", "supercharge", "seamless", "leverage" as a verb.
4. **No manufactured suspense.** Don't tease what's in the next section. Say it.
5. **Second person, present tense.** "You bill by retainer" not "Agencies that bill…".
6. **Short sentences carry the load.** Vary length, but the load-bearing sentence
   is short.
7. **Never claim on the product's behalf** beyond `campaign.yaml`'s
   `value_proposition`. No feature invented for a nice sentence.

## Banned outright

`guaranteed` · `#1` · `best in the world` · `risk-free` · `instantly`

(Enforced in code by `agent/creative/brand_validator.py` for ad copy. Same bar here.)

## Banned by convention

- "In today's fast-paced world" and every variant
- "Let's dive in" / "Let's unpack"
- Rhetorical question openers ("Ever wondered why…?")
- Emoji in body copy (subject lines: no)
- "As an AI" or any reference to how the piece was produced

## Reader

From `campaign.yaml` → `icp_description`. Assume they are competent, busy, and have
read three newsletters on this topic already. Earn the third paragraph.
