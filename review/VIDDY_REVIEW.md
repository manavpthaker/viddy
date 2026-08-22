# Viddy repo review — against DOAC-style best practices

Reviewed: `pipeline.py`, `scripts/*.py`, `remotion/src/**`, `remotion/render.mjs`, `config/*.json`, sample `render_data/clip_01.json`.

Your foundation is solid: word-level Whisper timestamps, a separate "pick clips" brain, a manifest-driven FFmpeg cut, a Remotion renderer with speaker zoom + captions + progress + hook, and a bundle-once/render-many script. The architecture is right. The gap is mostly in the *finish* — the things that make a DOAC short feel like a DOAC short rather than a competent subtitle overlay.

Findings are ordered by impact on perceived polish.

## P0 — Blocking polish issues

### 1. Captions are in the TikTok UI dead zone

`brand.json` has `caption_margin_bottom_px: 180`, which at 1920h puts captions roughly 91% down the frame. TikTok and Reels eat the bottom ~18% (like, comment, share, caption text, progress). DOAC captions sit roughly at 60–65% vertical — above the UI, right under the speaker's face.

Fix: change the contract from "margin_bottom" to "vertical_anchor_pct" and default to `0.62`. Scale the vertical offset with format so the square version isn't a different position entirely.

### 2. Caption typography doesn't read like DOAC

Current: DM Sans 800 / 64px, semi-transparent black rounded pill background, subtle text-shadow. That's "clean podcast captions." DOAC is heavier and more sculpted: very large display weight, tight letter-spacing, thick black stroke, hard drop shadow, and no background pill — the stroke/shadow replaces the pill.

Concrete targets to put in `brand.json`:

- `caption_size_px: 96` (vertical) / `80` (square). 64px is too small — it reads as a subtitle, not a headline.
- `letter_spacing_em: -0.02`
- `line_height: 1.05`
- `stroke_px: 10`, `stroke_color: "#000000"`
- `drop_shadow: "0 6px 0 rgba(0,0,0,0.35)"`
- `caption_background: "none"` (remove the pill entirely)
- `caption_highlight: "#FFD84D"` — that sage green (#7B9E87) is on-brand for "clean/documentary" but doesn't pop in feed. DOAC uses amber; you can keep sage for the progress bar.

Then in `AnimatedCaptions.tsx` drop the `backgroundColor: rgba(0,0,0,0.6)` container, apply `WebkitTextStroke: '{stroke_px}px {stroke_color}'` plus `paintOrder: 'stroke fill'` so the stroke renders behind the fill, and read the drop-shadow tokens from brand.

### 3. Fonts aren't preloaded — headless renders may fall back to a system font

You're using `fontFamily: 'DM Sans'` as a raw CSS string in `AnimatedCaptions.tsx` and `HookOverlay.tsx`. In Remotion Studio that works because Chrome has network. In `renderMedia`, fonts must be loaded into the page before rendering or the renderer will race and sometimes rasterize a fallback. Install `@remotion/google-fonts`, load the font at the top of `Root.tsx` with `loadFont` + `delayRender`, and only then register the compositions. This is the most common cause of "looks great in studio, looks wrong in output" bugs.

### 4. `ClipSquare` composition is 1080×1920 — not square

`Root.tsx` line 111: `<Composition id="ClipSquare" … width={1080} height={1920}>`. Should be `1080×1080`. The `resolution` map from `render_data` is never read at Composition-registration time — you hardcode dimensions. Since `calculateMetadata` lets you derive composition dimensions from inputProps, move dimensions into a `calculateMetadata` callback that reads `renderData.resolutions[formatKey]`.

Bonus: the same fix lets the dimensions be correct for 1:1 vs 9:16 without two separate Composition entries — you can have one composition and pass `format` via inputProps.

### 5. Highlight-word matcher has a severe substring bug

`prepare_render.py` line 209: `any(hw in word["word"].lower() for hw in highlight_words)`. A highlight like `"ai"` matches `said`, `main`, `fair`, `wait`. Even `"go"` matches `good`, `ago`, `gone`. Likely half your clips have words lit up that shouldn't be.

Fix: compare on `word.strip(".,!?…\"'").lower() == hw.lower()` (exact match on normalized token), or split each highlight into tokens and require a tokenized match. If you want to keep substring-style matching for stems ("wonder" → "wondering"), use `startswith` with a minimum length and a word-boundary check.

### 6. Progress bar position conflicts with TikTok UI

`progress_bar.position: "top"` overlaps TikTok's top bar (following / for you, search icon). Put it at bottom, or render it just above the caption safe zone (pixel ~70–72% down) as a thin inline element, not a full-width bar. DOAC doesn't use a progress bar at all — they rely on tight pacing. If you keep one, make it subtle (2px, desaturated), at the very bottom over black margin.

## P1 — Missing DOAC ingredients

### 7. No internal silence trimming

`cut_clips.py` adds padding around the selected clip window but doesn't trim the *inside* of the clip. DOAC cuts are aggressive — pauses >250ms get chopped. This single change does more for perceived "punchiness" than any visual effect.

Approach: after `select_clips` produces an approved window, run a Whisper-word-aware pass that stitches only the speaking intervals back together. Keep 80ms air on either side of each word-cluster. Produce a "cuts" array of `{source_start, source_end}` segments and have `cut_clips.py` emit a single concat-demuxer output. The caption timestamps in `prepare_render.py` then need to be remapped against the new timeline, not against the original source time. Right now `get_words_for_range` assumes linear mapping — that assumption breaks the moment you cut internal silence.

This is the biggest structural refactor on the list, but it's the biggest single quality lever. Without it, the clips will always feel slightly flat relative to DOAC.

### 8. No hook-frame thumb-stop — just a lower-third

`HookOverlay.tsx` renders at `top: 8%` with a black rounded box, a 4px accent bar on the left, and text at 55% of caption size (≈35px). That's a "chyron". A DOAC hook is a full-screen thumb-stop: big bold 2–4 word pull quote, either centered over a slightly-blurred first frame or stamped over the speaker at 80–100% of caption size with stroke. It holds for 1–1.5s, not 3s.

Two easy wins:

- Increase font size to `caption_size_px * 1.1`, drop the background pill, add the same stroke/shadow as captions.
- Add a scale-in from 0.92 → 1 with a spring(`{damping: 14, stiffness: 220}`), not a `translateY` slide.

### 9. No sound design or music bed

`ClipComposition.tsx` has no `<Audio>` layer. DOAC shorts have a quiet instrumental bed at ≈ -22 LUFS, occasional whoosh on cuts, and a subtle impact on punch-ins. Without this, even a perfectly-captioned short feels "dry" relative to what users see on feed.

Minimum viable version: a single music bed per episode defined in `config/episode.json`, passed through render_data as `music: { src, volume }`, rendered with `<Audio src={staticFile(music.src)} volume={0.12} />`. Ducking-on-voice can come later.

### 10. No b-roll insertion points

You have `highlight_words`, but no data model for "insert b-roll image/video for this phrase window." Diary's editors drop b-roll on concrete nouns ("Boeing", "the plane crash", "my resume") for 1.2–1.8s. Even static stock images with a slow Ken-Burns zoom, cross-dissolved 4 frames, dramatically increase retention.

Add to render_data: `broll: [{ start_seconds, end_seconds, src, fit: "cover", ken_burns?: { from: [x,y,scale], to: [x,y,scale] } }]`. A new `<BRollOverlay />` component renders over the SpeakerZoom layer with opacity interpolated at the edges.

### 11. No end card / CTA

Final frame of a DOAC short usually holds briefly with the guest's name, title, and "Full episode on The Diary of a CEO." Short hold, but it drives channel search. Right now Viddy clips end on a fade-out of the last caption over the speaker. Add a 0.8s `<Sequence from={totalFrames - fps*0.8}>` end card with guest name and episode link.

## P2 — Structural / engineering

### 12. No `CLAUDE.md`, no `references/`, no `fixtures/`

This is the biggest reason future Claude Code sessions will reinvent your choices. Add:

- `CLAUDE.md` at repo root that encodes the style tokens (font, stroke, colors, safe zones, timing conventions), the data contract (render_data shape), and the "do/don't" of the aesthetic ("never use background pills on captions; use stroke + shadow instead"). I can draft this — it's a 10-minute add and pays for itself the next time Claude Code touches the repo.
- `references/` with 3–5 DOAC screenshots annotated with pixel measurements (active word color, stroke width, caption vertical position). Claude Code will use these as ground truth when you say "match the reference."
- `fixtures/sample-clip.json` — a hand-written render_data that exercises every feature (highlight words, speaker change, zoom emphasis, hook). Lets anyone (or Claude Code) iterate the renderer without running the full pipeline.

### 13. No `renderStill` preview harness

Right now the fastest way to see a change is `renderMedia --preview` at 540p. That's still many seconds per iteration. Add `scripts/preview_stills.mjs` that loads a fixture and emits `.jpg` stills at frames [0, 15, 45, 90, 180, -30] into `renders/previews/{git-sha}/`. Iteration time drops from 30s to ~3s, and you (or Claude Code) can eyeball changes side-by-side.

### 14. No runtime schema validation on `render_data`

`types.ts` defines TS interfaces but nothing validates the Python output matches at load time. If `prepare_render.py` silently drops a field, you'll debug it in a render log 20 minutes later. Install `zod`, define a schema in `remotion/src/schema.ts`, and `schema.parse(inputProps.renderData)` in `Root.tsx` / `calculateMetadata`. Failures will be loud and point to the exact field.

Bonus: derive the TS types from the Zod schema (`z.infer<typeof RenderDataSchema>`) — one source of truth.

### 15. CSS transitions won't work in headless renders

`AnimatedCaptions.tsx` line 115: `transition: 'color 0.1s'`. CSS transitions require wall-clock time, which doesn't exist frame-by-frame in Remotion's headless renderer. This works in Studio (live preview) and silently does nothing in production renders. Remove it. If you want the color shift to feel smooth rather than stepped, interpolate the color via `interpolate` on a 3–4 frame window when the word becomes active.

### 16. Active-word scale has no ease-out

`scale` ramps from 1→1.1 over frames `[word.start*fps, word.start*fps+3]` and then snaps back to 1 when the word becomes inactive. Add a ramp-out using the word's `end` time. Easier: use `spring()` from Remotion with a short `durationInFrames` and a shared "activeness" signal (0→1→0 over the word's lifetime). Reads much more organic.

### 17. Hard-coded source dimensions

`ClipComposition.tsx` lines 20–21: `sourceWidth = 1280; sourceHeight = 720`. If you ever ingest a 1920×1080 source (and you will), the SpeakerZoom translateX math breaks silently. Either write dimensions into `manifest.json` when `cut_clips.py` runs (ffprobe), or read them at `calculateMetadata` time with `parseMedia` from `@remotion/media-parser`.

### 18. Clip length target is too long for 9:16 feeds

`default.json`: `target_duration_seconds: 75`, `max: 120`. For Reels/Shorts/TikTok, the sweet spot is 25–55s. 75s clips underperform even with great hooks. Consider `target: 45, max: 60`. If the brain picks a strong ≥75s moment, either (a) drop it, or (b) split it and run two hooks back-to-back. LinkedIn is more forgiving of longer — keep the long cut but export a shorter edit for the other platforms.

### 19. `source_video` path in render_data is absolute-local

`render_data/clip_01.json` stores `/Users/manavthaker/…`. `render.mjs` compensates by copying to `public/` and overwriting the field, but the contract is fragile — if you ever render from a different machine or use cloud Lambda, absolute paths break. Store the relative path (`clip_01.mp4`) in render_data and resolve via `staticFile()` at render time. The "copy to public" step is fine, just stop leaking the absolute path into the JSON.

### 20. `prepare_render.py` doesn't pre-split captions into comfortable line widths

`words_per_group: 3` is fixed. A group of "I eventually get" (14 chars) sits next to "soon as I" (9 chars) sits next to something that could be 20 chars. Pixel width varies 3x. Use `@remotion/layout-utils` `measureText` to split on visual width (e.g., max 14 chars per line, max 2 lines per group) rather than word count. Orphan words ("a", "the") should bond to the next word. This is what makes captions feel "designed" rather than "generated."

## Nice-to-haves (P3)

- **Telemetry**: log bundle time, per-clip render time, per-clip frame count into a `renders/manifest.json` so you can track regressions when you change the pipeline.
- **Deterministic color variants**: a tiny palette of 3 highlight colors cycled per clip — makes a series of 7 clips feel like a set rather than identical copies.
- **Subtle film grain / chromatic aberration** at very low opacity — DOAC sometimes layers this at 3–5% to give output a "produced" feel. Render it as an overlay PNG or a cheap SVG pattern.
- **Accessibility**: emit `.srt` or `.vtt` alongside the render using the same word groups. Good for LinkedIn (auto-captions are bad there) and for re-uploads to YouTube Shorts.

## Suggested order to attack

1. Font preload + caption typography + safe zone (items 1, 2, 3) — 1 afternoon, huge visual delta.
2. Highlight-word bug + ClipSquare dimensions (items 4, 5) — 30 min, correctness wins.
3. CLAUDE.md + references/ + fixtures/ + preview_stills (items 12, 13) — 1 evening, compounds every future session.
4. Silence trimming (item 7) — 1–2 days; biggest pacing lever.
5. Hook frame upgrade + music bed + end card (items 8, 9, 11) — 1 day together.
6. Zod schema + runtime validation (item 14) — 2 hours.
7. B-roll layer (item 10) — 1–2 days for first version.

If you want, I can do (1), (2), (4), (6) and the CLAUDE.md in a single pass now — those are the items that don't require product decisions.
