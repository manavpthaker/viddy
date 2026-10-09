# Viddy

Raw video recordings to polished short-form clips with animated captions, speaker zoom, and motion graphics. Diary of a CEO style. Hands-off.

## How it works

```
Raw video → Whisper (transcribe) → Claude Vision (detect layout) → Claude (pick clips) → YOU (approve) → FFmpeg (cut) → A/V speaker tracking → Remotion (render)
```

**Phase 1 — The Brain (automated):**
1. Transcribes with word-level timestamps (OpenAI Whisper API)
2. Samples frames and detects speaker layout via Claude Vision (who's on which side, screen share segments)
3. Claude reads the full transcript and finds clip-worthy moments
4. **Scores every candidate against a virality rubric** (0–100, with a scorecard) and ranks them
5. Generates a review file with scores. You approve or reject.

**Phase 2 — Cut + Prep (automated):**
5. FFmpeg cuts approved clips with fade in/out, then trims dead air
6. **Audio-visual active-speaker tracking** — detects faces and who is actually
   talking, frame by frame, so clips reframe onto the live speaker (Riverside-style)
   instead of guessing left/right from the transcript
7. Builds render-ready data (caption timing, reframe keyframes, highlight words)

**Phase 3 — The Look (Remotion):**
8. Renders clips with animated captions, real speaker reframing, progress bar, branding
9. **Packages each clip for sharing** — hook variants, comment-bait, LinkedIn + YouTube
   Shorts copy with hashtags, an auto cover thumbnail (cropped to the speaker), and an
   on-brand quote card

## Virality rubric

Every clip candidate is scored 0–100 across weighted dimensions, and the scorecard
shows up in `review.md` so you can see *why* a clip ranks where it does:

| Dimension | Weight | Drives |
|---|---|---|
| Hook (first-line stop-scroll) | ×2.0 | watch-through |
| Emotional charge | ×1.5 | — |
| Self-contained (zero context) | ×1.5 | — |
| Payoff / arc | ×1.5 | — |
| Quotability | ×1.5 | shares |
| Specificity | ×1.0 | — |
| Contrarian | ×1.0 | comments |
| Practical value | ×1.0 | saves |
| Relatability | ×1.0 | shares |

Edit the weights in `scripts/select_clips.py` (`RUBRIC`). Scoring is **advisory** by
default — nothing is dropped. Set `clip_selection.min_score` in `config/default.json`
to auto-mark low scorers as not-approved.

## Shareability assets

Per approved clip, `clips/<name>/social/` gets:
- `clip_NN.md` — copy/paste-ready: hook variants, comment-bait, LinkedIn + YouTube Shorts captions + hashtags
- `cover_NN.jpg` — thumbnail cropped to the speaker (reuses the reframe track)
- `quote_NN.png` — on-brand quote card for carousels/reposts

## Quick start

```bash
# Prerequisites
pip install -r requirements.txt   # openai + anthropic (core), plus optional
                                  # mediapipe/opencv/numpy for real reframing
brew install ffmpeg  # if not already installed

# Set API keys
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Drop a video in input/
cp ~/Downloads/podcast-recording.mp4 input/

# Run Phase 1 (transcribe → detect layout → select clips)
python pipeline.py input/podcast-recording.mp4

# Review clips in review/podcast-recording/review.md
# Edit review/podcast-recording/clips.json to approve/reject

# Run Phase 2 (cut + prepare render data)
python pipeline.py input/podcast-recording.mp4 --render
```

## Usage

```bash
# Full pipeline (pauses after clip selection for review)
python pipeline.py input/video.mp4

# Render phase (after reviewing clips.json)
python pipeline.py input/video.mp4 --render

# Skip layout detection (faster, no zoom effects)
python pipeline.py input/video.mp4 --skip-layout

# Skip A/V active-speaker tracking (use legacy transcript-based reframing)
python pipeline.py input/video.mp4 --render --skip-tracking

# Run individual steps
python pipeline.py input/video.mp4 --step transcribe
python pipeline.py input/video.mp4 --step layout
python pipeline.py input/video.mp4 --step select
python pipeline.py input/video.mp4 --step cut
python pipeline.py input/video.mp4 --step track    # A/V active-speaker reframing
python pipeline.py input/video.mp4 --step prepare
```

## Real reframing (audio-visual active-speaker tracking)

What makes clips look professionally reframed is cropping onto whoever is
actually talking. Viddy does this for real:

1. **Face tracking** (MediaPipe FaceMesh) finds and follows faces frame by frame.
2. **Voice activity** comes from pyannote (if `HUGGINGFACE_TOKEN` is set) or an
   ffmpeg energy-based fallback.
3. **Active speaker** = the on-screen face whose lips move during speech.
4. A smoothed, debounced **reframe track** (`<clip>.reframe.json`) tells the
   renderer where to crop, so the camera follows the speaker with eased motion.

This step is **optional and degrades gracefully**. If `mediapipe`/`opencv`/`numpy`
aren't installed (or no faces are found), the renderer falls back to the legacy
transcript-based left/right reframing — nothing breaks, it just looks less precise.

### Screen + speaker composite

For screen-share recordings (a small webcam over shared slides), cropping to the
face would throw the slides away. Viddy detects this case — a small face in a
corner plus a detected screen-content box (`cropdetect`) — and switches to a
**stacked composite**: the shared screen on top (kept whole, fit to width) and the
speaker face-framed in a band below. The slides stay readable and the speaker
stays prominent.

Selection is automatic but overridable: set `render.default_layout` in
`config/default.json` to `auto` (default), `speaker`, or `composite`, or set
`"layout"` on an individual clip in `clips.json`.

For best quality, also install pyannote and set a token:

```bash
pip install pyannote.audio
export HUGGINGFACE_TOKEN=hf_...   # accept terms for pyannote/voice-activity-detection
```

## Folder structure

```
viddy/
├── pipeline.py              # Main orchestrator
├── scripts/
│   ├── transcribe.py        # Whisper API → word-level transcript
│   ├── detect_layout.py     # Claude Vision → speaker positions + screen share
│   ├── select_clips.py      # Claude → ranked clip candidates
│   ├── cut_clips.py         # FFmpeg → cut clip files
│   ├── trim_silence.py      # FFmpeg → remove dead air, remap timestamps
│   ├── track_speakers.py    # MediaPipe + VAD → A/V active-speaker reframe track
│   ├── prepare_render.py    # Merge captions + reframe + brand → Remotion input
│   └── package_clips.py     # Claude → social copy, covers, quote-card payloads
├── remotion/                # React video renderer (Phase 3)
│   └── src/
├── config/
│   ├── default.json         # Pipeline settings
│   └── brand.json           # Colors, fonts, caption style
├── input/                   # Drop raw videos here
├── review/                  # Transcripts, clips.json, review.md (per video)
├── clips/                   # Cut clips + render data (per video)
└── output/                  # Final rendered clips
```

## Config

**`config/default.json`** — Pipeline settings (clip duration, number of clips, models, render formats)

**`config/brand.json`** — Visual style (colors, fonts, caption positioning, progress bar)

## Cost per video

- Whisper API: ~$0.006/min (~$0.20 for a 30-min recording)
- Claude (clip selection): ~$0.10-0.30
- Claude Vision (layout): ~$0.10-0.20
- Total: ~$0.40-0.70 per video

## Roadmap

- [x] Phase 1: Transcription + clip selection
- [x] Phase 2: FFmpeg cutting + silence trim + render data prep
- [x] Phase 3: Remotion renderer (animated captions, speaker reframing, progress bar)
- [x] Real audio-visual active-speaker reframing (MediaPipe + VAD)
- [x] Per-clip virality rubric (0–100 scorecard, advisory ranking)
- [x] Shareability packs — hook variants, comment-bait, LinkedIn/YT copy, covers, quote cards
- [x] Screen + speaker composite layout (for screen-share recordings)
- [ ] Audio post: loudness normalization (-14 LUFS) + denoise
- [ ] Speaker identity locking via diarization (stop following incidental on-screen faces)
- [ ] Batch processing (multiple videos)
