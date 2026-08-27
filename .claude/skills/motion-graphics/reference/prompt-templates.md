# Prompt / spec templates

Use these to turn a vague request into a fully-specified one — either by filling
in the blanks yourself from context, or asking the user for the specifics a
template needs. A spec with hex colors and second-by-second timing produces a
correct result on the first pass; "make a cool intro" doesn't.

Platform → resolution, when the user names one:

| Platform | Resolution | Aspect |
|---|---|---|
| YouTube | 1920x1080 | 16:9 |
| Instagram Reels / TikTok | 1080x1920 | 9:16 |
| Twitter/X | 1280x720 | 16:9 |
| Square (Instagram post) | 1080x1080 | 1:1 |

## Text animation intro

```
[duration]s at [width]x[height], 30fps.
Background: solid [hex].
Text: "[TEXT]" in [color], [weight], [size]px, centered, [font].

- 0.0s: invisible (opacity 0, scale 0.8)
- 0.0–0.8s: fades in + scales to 1.0 via spring
- 0.8–[duration-1]s: holds
- [duration-1]–[duration]s: fades out
```

## Animated counter / number reveal

```
[duration]s at 1920x1080, 30fps.
Background: [hex]. Large number counter, centered, counts [start] → [end].

- interpolate the number smoothly over [duration]s
- format: [commas / $ / % / none]
- number: [size]px, [color], bold
- label below: "[label]", [size]px, [color]
```

## List / bullet reveal

```
[duration]s at 1920x1080, 30fps.
Background: [hex]. Title "[TITLE]" at top, [size]px, [color], bold.

Items (reveal one by one):
1. "[item 1]"  2. "[item 2]"  3. "[item 3]"

- title: spring scale 0→1 over 0.5s
- each item: slides in from left, 0.4s stagger, spring(damping: 15, stiffness: 120)
- left margin 10%, evenly spaced vertically, small colored bullet before each
```

## Social media story / reel (portrait)

```
15s at 1080x1920, 30fps. Background: gradient [hex1] → [hex2], top→bottom.

0–3s:  hook line "[HOOK]", centered, spring bounce in, white, 72px bold
3–8s:  three points appear in turn — "[p1]" @3.5s, "[p2]" @5.0s, "[p3]" @6.5s,
       each sliding up from below via spring
8–12s: big stat "[NUMBER]" springs in, then "[context]" fades in below
12–15s: CTA "[CTA TEXT]" pulses gently (scale 1.0→1.03 looping),
        "[handle/url]" fades in below
```

## Progress bar / timeline

```
[duration]s at 1920x1080, 30fps.
Background: [hex]. Title "[TITLE]" top, centered, [size]px.

Bar: background [light hex], height 20px, width 80%.
Fill: [accent hex], interpolate 0%→100% (clamp) over [duration-2]s.
Live "%" label above the bar. Milestone labels at 25/50/75/100%, each
fading in as the bar reaches it.
```

## Logo reveal

```
[duration]s at 1920x1080, 30fps. Background: [hex].
Logo: public/logo.png, centered.

- 0.0–0.3s: invisible
- 0.3–1.0s: scales 0.5→1.0, spring(stiffness: 80, damping: 12)
- 1.0–1.3s: tagline "[TAGLINE]" fades in below
- holds until [duration-0.5]s
- [duration-0.5]s–end: fades out
```

## Multi-scene videos

For anything longer than ~5s of a single idea, build one composition per scene and
compose with `<Sequence>` rather than one large template — see
`reference/code-examples.md` (Example 3).
