# Remotion core concepts

Five primitives cover almost every motion graphic.

## Composition

A video definition: a component plus metadata. Registered in `src/Root.tsx`.

```tsx
<Composition
  id="MyVideo"
  durationInFrames={150}   // 5s at 30fps
  fps={30}
  width={1920}
  height={1080}
  component={MyVideoComponent}
/>
```

`id` is what you pass to `npx remotion render <id> out.mp4`. A project can register
many compositions — one per scene, plus a top-level one that sequences them.

## `useCurrentFrame()` / `useVideoConfig()`

```tsx
import { useCurrentFrame, useVideoConfig } from "remotion";

const frame = useCurrentFrame();               // current frame number, starts at 0
const { fps, durationInFrames, width, height } = useVideoConfig();
```

Remotion calls your component once per frame and screenshots the result — there is
no continuous time between frames, so animation must be a pure function of `frame`.

## `interpolate()`

Maps an input range to an output range — the basic tool for fades, moves, scales.

```tsx
import { interpolate, useCurrentFrame } from "remotion";

const opacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });
```

Args: input value (usually `frame`), input range `[start, end]`, output range
`[startValue, endValue]`, options. Always set `extrapolateLeft`/`extrapolateRight`
to `"clamp"` unless you specifically want values to keep growing past the range.

## `spring()`

Physics-based animation — accelerates/decelerates like a real object, feels less
robotic than linear `interpolate`.

```tsx
import { spring, useCurrentFrame, useVideoConfig } from "remotion";

const scale = spring({
  frame,
  fps,
  config: { mass: 1, stiffness: 100, damping: 10 }, // higher stiffness = snappier,
});                                                   // higher damping = less bounce
```

Use `frame: frame - delay` to stagger multiple elements (e.g. `i * 8` per item in a
list). Add `config: { overshootClamping: true }` to kill bounce entirely.

## `<Sequence>`

Controls when children appear/disappear and re-zeroes their local frame count.

```tsx
<Sequence durationInFrames={30}><Title text="Act One" /></Sequence>
<Sequence from={30} durationInFrames={60}><MainContent /></Sequence>
<Sequence from={90}><Outro /></Sequence>
```

If a `Sequence` starts at global frame 30, its child's `useCurrentFrame()` returns 0
at that point — animations inside a scene don't need to know their absolute offset.

## `<AbsoluteFill>`

A `<div>` that fills the frame with absolute positioning — the standard way to
layer and center elements.

```tsx
<AbsoluteFill style={{ backgroundColor: "#000" }}>
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
    <h1>Centered Text</h1>
  </AbsoluteFill>
</AbsoluteFill>
```

## Rendering

```bash
npx remotion render MyVideo out/video.mp4      # or .webm / .gif
npx remotion still MyVideo out/thumbnail.png   # single frame
npx remotion compositions                      # list registered composition IDs
```

Rendering is CPU-bound; `--concurrency=<n>` parallelizes across cores.
