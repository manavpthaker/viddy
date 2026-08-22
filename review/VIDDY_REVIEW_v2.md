# Viddy repo review — v2 (diff against previous review)

You moved on several items. Overall direction is right. Two changes introduced **new sync-breaking bugs** that will cause visible issues — call those out first before patting yourself on the back.

## New P0 issues introduced

### N1. Silence trim desyncs captions from video

`trim_silence.py` runs *after* `cut_clips.py` and *before* `prepare_render.py` in `pipeline.py` (steps 4 → 5 → 6). But `prepare_render.py` still builds caption timestamps, speaker timeline, and zoom moments using `source_start` / `source_end` from the manifest — the **pre-trim** source-video coordinate system. It has no knowledge of the internal cuts `trim_silence.py` made to the MP4.

Consequence: if `trim_silence` removes 2.4s of silence in the middle of a clip, every caption after that silence fires 2.4s too late against the trimmed video. The longer the clip and the more silence trimmed, the worse it gets. Hook lands on the wrong line. Speaker zoom target flips to the wrong speaker.

Fix direction: either

- **(A)** Have `trim_silence.py` emit a `keep_segments.json` alongside each trimmed clip, then have `prepare_render.py` remap every `start`/`end` through the keep-segment mapping. This is the correct fix and is the same plumbing you'll want for b-roll timing later.
- **(B)** Simpler but worse: use Whisper word timestamps to build the keep segments (not FFmpeg silencedetect), so caption times come pre-mapped to the trimmed timeline. This couples trim to transcription and means you can't run trim standalone.

Go with (A). The mapping function is ~10 lines:

```python
def remap(t_source: float, keep_segments: list[tuple[float,float]]) -> float | None:
    offset = 0.0
    for s, e in keep_segments:
        if t_source < s: return None          # removed
        if t_source <= e: return (t_source - s) + offset
        offset += (e - s)
    return None
```

### N2. `total_frames` doesn't match trimmed video duration

`prepare_render.py` computes `total_frames = int(duration * fps)` where `duration = (source_end + padding_after) - (source_start - padding_before)`. That's the *pre-trim* window duration. `render.mjs` then sets `composition.durationInFrames = renderData.total_frames`.

After silence trim, the actual MP4 is shorter. Remotion will render for the longer duration and the video layer will freeze on the final frame for however many seconds were trimmed. User will see the host's face frozen with captions continuing (or ending silent).

Fix: after trim, `ffprobe` the clip's real duration and write that into render_data. Or more robustly, have `trim_silence.py` update `manifest.json` with a `final_duration_seconds` field that `prepare_render.py` reads.

### N3. CLAUDE.md and component code disagree

Style doc says "2px black stroke, 48–52px hook font, no zoom greater than 1.1x, base scale 1.0." Code says `WebkitTextStroke: '1.5px rgba(0,0,0,0.8)'` (also too thin for DOAC — should be 6–10px for 58px type), hook font at 58 × 0.55 ≈ 32px (~40% below the doc), `base_scale: 1.35` and `zoom_scale: 1.06` (stacked that's 1.43 — violates "no zoom > 1.1x").

This matters because the doc is what future Claude Code sessions (and you, in two weeks) will read as source of truth. When it drifts, you silently compound styling debt. Pick one answer and update both sides.

Quick reconciliation I'd make:
- Stroke: 6px stroke, full black (DOAC is heavy).
- Hook font: 64–72px stand-alone, not a fraction of caption size.
- Decide: "base_scale is total scale (including speaker crop)" or "base_scale is on top of fit-to-frame." Currently the doc says base 1.0 + crop 1.3–1.4x but data says base_scale: 1.35 and the SpeakerZoom component uses it as-is. Pick one.

## Scorecard against the previous review

### P0 items

| # | Item | Status |
|---|------|--------|
| 1 | Caption safe zone (60% vertical) | **Fixed** — `captionTop = height * 0.60` |
| 2 | Caption typography (stroke, shadow, no pill, tight letter spacing) | **Partial** — pill removed, stroke + shadow + letter-spacing added. But stroke is 1.5px @ 80% alpha (too thin for DOAC), font is 58px (still undersize for 9:16 — aim ~88–96px), highlight still sage, not amber |
| 3 | Font preloading via `@remotion/google-fonts` | **Not fixed** — still raw `fontFamily: 'DM Sans'`. Headless renderer will race |
| 4 | `ClipSquare` is 1080×1920 (should be 1080×1080) | **Not fixed** — `Root.tsx` line 111 still wrong |
| 5 | Highlight-word substring bug | **Not fixed** — `prepare_render.py:209` still `hw in word["word"].lower()` |
| 6 | Progress bar in TikTok UI zone | **Partial** — `top_offset_px` added to config, ProgressBar reads it with a 12% fallback, `brand.json` now has `progress_bar_top_offset_px: 230`. But `prepare_render.py`'s `progress_bar` block doesn't plumb `top_offset_px` through to render_data, so the component falls back to the 12% default — the config value is dead weight. One-line fix in `prepare_render.py` |

### P1 items

| # | Item | Status |
|---|------|--------|
| 7 | Internal silence trimming | **Added, but broken downstream** — see N1/N2. Script itself is clean (FFmpeg `silencedetect` at -40dB, 300ms min, 80ms air buffer) |
| 8 | Hook = thumb-stop not lower-third | **Not fixed** — CLAUDE.md actually *codifies* the lower-third pattern now. Both need updating together |
| 9 | Music bed / sound design | **Not fixed** |
| 10 | B-roll insertion | **Not fixed** |
| 11 | End card / CTA | **Not fixed** |

### P2 items

| # | Item | Status |
|---|------|--------|
| 12 | CLAUDE.md, references/, fixtures/ | **Partial** — `remotion/CLAUDE.md` added (✓), plus a `remotion-best-practices` skill. No `references/` with DOAC stills, no `fixtures/` with sample render_data. Without fixtures, `preview-stills.mjs` still requires a full pipeline run |
| 13 | `renderStill` preview harness | **Fixed** — `preview-stills.mjs` looks good: bundles once, renders 5 frames by default at jpeg q=85, sensible defaults |
| 14 | Zod runtime validation | **Not fixed** — still TS-only |
| 15 | CSS `transition` in headless render | **Fixed** — removed |
| 16 | Active word has no ease-out | **Not fixed** — `wordSpring` ramps in from frame `word.start`, but when `isActive` flips false at `word.end`, `baseScale` drops from 1.08 → 1 in a single frame. Same snap, different expression. Needs a symmetric "exit" spring or an `interpolate` blended across a 4–6 frame window at `word.end` |
| 17 | Hardcoded 1280×720 source dimensions | **Not fixed** |
| 18 | Target duration too long (75s / max 120s) | **Not fixed** |
| 19 | Absolute source_video path in render_data | **Not fixed** |
| 20 | Fixed `words_per_group: 3` (no measureText) | **Not fixed** |

## Small new bugs worth noting

**Double Step 6 in `pipeline.py`.** Lines 187 and 197 are both labeled "Step 6" in comments. The `trim_silence` insert at step 5 shifted numbering but wasn't propagated. Cosmetic, but reads as if the pipeline was edited mid-thought — and future Claude Code sessions key off comment numbering to orient.

**Dead `original_path_to_use` variable in `trim_silence.py`.** Line 153, unused. Leftover from a refactor. Readers will assume it's used and be confused.

**Second-run behavior of `trim_silence.py`.** On re-run, because `.original.mp4` exists, the `else` branch trims from the *already-trimmed* `video_path` to a temp file and replaces. `silencedetect` will find little to trim so the `removed < 0.5s` guard usually saves you — but if threshold is loose, you could shrink the clip further. Safer pattern: always re-trim from `.original.mp4` into the working file. That makes the trim idempotent.

**`remotion/.agents/`, `.claude/`, `.goose/`, `skills-lock.json`** all got added at the same time. If those were intentional from a plugin install, fine — but they're in the git working tree. Confirm they're supposed to be checked in (most skills tooling wants them gitignored per user).

## What's genuinely good about the v2 changes

- `preview-stills.mjs` is well-designed and will pay for itself the first time you iterate the caption component.
- Spring-based word entrance with per-word scale from 0.9 → active-scale feels much more "produced" than the previous linear 1 → 1.1.
- `CLAUDE.md` at `remotion/` is the right location (scoped to the TS side, not the Python pipeline). The anti-patterns section at the bottom is exactly right — "no bouncy animations, no emoji overlays" are the right negative prompts.
- Silence trim approach is clean (the script itself is fine; the integration is the problem).
- Progress bar gained a configurable top offset, and `top_offset_px: 230` in brand.json is the right value.

## Suggested next 90-minute pass

1. Fix N1 (trim mapping through to caption/speaker times) — the visible sync drift is the single most damaging thing for perceived quality right now.
2. Fix N2 (`total_frames` from actual clip duration after trim).
3. Fix item 5 (substring highlight bug) — 2 lines.
4. Fix item 6 plumbing (pass `top_offset_px` through `prepare_render.py`).
5. Fix item 4 (`ClipSquare` dimensions + switch to `calculateMetadata`).
6. Align CLAUDE.md to reality (or vice versa) on stroke width, hook font size, and the base-scale-vs-zoom constraint.

That's roughly 1.5h of mechanical work and unblocks every further polish pass. Want me to do it?
