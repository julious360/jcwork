# Troubleshooting

**Animations look choppy, flicker, or don't move at all.**
Cause: something is driving the animation other than `useCurrentFrame()` — CSS
`transition`/`animation`, `setTimeout`/`setInterval`, or `requestAnimationFrame`.
Remotion renders each frame as an independent, stateless render; there is no
continuous wall-clock time between frames, so those APIs silently do nothing (or
only partially apply) during render. Fix: drive every animated value from
`useCurrentFrame()` via `interpolate()` or `spring()`, never from real time.

**Claude/the agent "doesn't know" Remotion, or acts like the skill isn't there.**
Cause: the skill/dependencies weren't installed in *this* project, or the agent
session started before they were added. Fix: confirm `remotion` is a dependency
(`npm install remotion @remotion/cli` if missing) and that `src/Root.tsx` /
`remotion.config.ts` exist; restart the coding session after adding either.

**Preview doesn't update in Remotion Studio.**
Cause: hot-module-replacement occasionally fails after a large edit. Fix: save the
file again; if still stuck, stop and restart `npm run dev` and check the terminal
for a compile error.

**Render fails with "Composition not found".**
Cause: the ID passed to `render` doesn't match the `id` prop registered in
`src/Root.tsx`. Fix: `npx remotion compositions` to list valid IDs, then use the
exact string.

**Elements overlap or land in the wrong place.**
Cause: too many animated elements in one component makes manual layout math brittle.
Fix: use `<AbsoluteFill>` + flexbox for centering instead of manual
top/left math; ask for a specific nudge ("move the subtitle 40px lower") rather
than a full relayout; split an overloaded scene into separate `<Sequence>` scenes.

**Render is slow.**
Cause: rendering is CPU-bound; complex scenes with many elements render slower.
Fix: `npx remotion render <id> out.mp4 --concurrency=8` (tune to core count);
render a 720p draft first, full resolution once the animation is approved.

**Custom fonts don't show up in the rendered video (even though they show in the
browser).**
Cause: fonts load asynchronously and may not be ready when a frame is captured.
Fix: use `@remotion/google-fonts` (`npm install @remotion/google-fonts`), then
`import { loadFont } from "@remotion/google-fonts/Inter"` and use the returned
`fontFamily` — Remotion waits for the font before rendering each frame.

**Images don't appear in the render.**
Cause: using a plain `<img>` tag — Remotion doesn't know when it's finished
loading. Fix: use Remotion's `<Img src={...} />` component instead; for local
files, put them in `public/` and reference with `staticFile("name.png")`.
