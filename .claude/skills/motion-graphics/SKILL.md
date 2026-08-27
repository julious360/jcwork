---
name: motion-graphics
description: Create programmatic motion graphics and animated videos — title cards, kinetic typography, animated data charts, logo reveals, lower thirds, social media reels/stories — from a plain-language description, using Remotion (a React-to-MP4 video framework). Use whenever the user asks to animate text or a logo, build an intro/outro, turn a static graphic into a moving one, make a social video/reel, visualize data with motion, or otherwise wants a short rendered video rather than a static image. Also use when the user mentions Remotion directly.
---

# Motion graphics with Remotion

Remotion turns React/TypeScript components into rendered MP4/WebM/GIF video. There
is no timeline, no keyframe panel, and no drag-and-drop — every frame is just the
output of your component evaluated at a given frame number. That property is what
makes it a good fit for an agent: describe the video in words, and the code you
write *is* the animation.

Read the reference files under `reference/` only when you need them — don't load
everything up front:

- `reference/core-concepts.md` — the five Remotion primitives you need for almost
  everything (Composition, `useCurrentFrame`, `interpolate`, `spring`, `Sequence`,
  `AbsoluteFill`). Read this before writing your first component in a project.
- `reference/prompt-templates.md` — fill-in-the-blank structures for the common
  video types (text intro, counter, bullet reveal, social reel, progress bar, logo
  reveal). Use these to turn a vague user request into a fully-specified one before
  writing code, and to ask the user for missing details.
- `reference/code-examples.md` — four complete, working components (kinetic
  typography, animated bar chart, multi-scene video with `Sequence`, looping pulse
  loop) to adapt rather than write from scratch.
- `reference/troubleshooting.md` — fixes for the failure modes that actually occur
  (choppy animation, wrong composition ID, fonts not rendering, images not loading,
  slow renders).

## Workflow

1. **Check for an existing Remotion project.** Look for `remotion.config.ts` and
   `src/Root.tsx` in the working directory. If absent, set one up:
   ```bash
   npx create-video@latest my-video   # template: Blank, TailwindCSS: yes
   cd my-video && npm install
   ```
2. **Ensure the dev preview is running** (`npm run dev` in the project, opens
   Remotion Studio at `localhost:3000`) so the user can watch changes hot-reload
   as you iterate. Start it in the background if it isn't already running.
3. **Turn the request into a full spec before writing code.** A vague ask ("make
   a cool intro") produces a vague result. Pin down: resolution/aspect ratio (ask
   the platform — YouTube 1920x1080, Reels/TikTok 1080x1920, square 1080x1080),
   duration, fps (default 30), exact colors (hex, not "blue"), exact copy, and the
   animation sequence as a timeline ("0.0–0.8s: X fades in and scales up",
   "0.8–3s: holds", ...). Use `reference/prompt-templates.md` as the checklist;
   ask the user only for what a template needs and they haven't given you.
4. **Write the component** using only frame-driven animation — `useCurrentFrame()`,
   `interpolate()`, `spring()`, and `<Sequence>` for timing. Never use CSS
   `transition`/`animation`, `setTimeout`, or `requestAnimationFrame`: Remotion
   renders every frame independently and stateless, so wall-clock-based animation
   silently does nothing. See `reference/core-concepts.md` for the mechanics and
   `reference/code-examples.md` for patterns to copy.
5. **Register the composition** in `src/Root.tsx` with a unique `id`, matching
   `durationInFrames`/`fps`/`width`/`height` to the spec.
6. **Let the preview confirm it**, then iterate on small, specific follow-ups
   ("fade in 0.5s faster", "shift the line 0.3s later") rather than full rewrites —
   Claude (and Remotion Studio's hot reload) handles incremental changes far more
   reliably than wholesale regeneration.
7. **Render when approved:**
   ```bash
   npx remotion render <CompositionId> out/video.mp4
   ```
   Use `--concurrency=<n>` to speed up long/complex renders; render a 720p draft
   first for fast iteration if the scene is heavy, then the final resolution.
8. Long videos: build one composition per scene, then compose them with
   `<Sequence from={...} durationInFrames={...}>` in a top-level composition,
   rather than one giant component (see the multi-scene example in
   `reference/code-examples.md`).

If something breaks — flicker, wrong composition rendered, missing fonts/images,
slow renders — check `reference/troubleshooting.md` before improvising a fix.
