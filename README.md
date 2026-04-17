# Viddy

Raw video recordings to polished short-form clips with animated captions, speaker zoom, and motion graphics. Diary of a CEO style. Hands-off.

## How it works

```
Raw video → Whisper (transcribe) → Claude Vision (detect layout) → Claude (pick clips) → YOU (approve) → FFmpeg (cut) → Remotion (render)
```

**Phase 1 — The Brain (automated):**
1. Transcribes with word-level timestamps (OpenAI Whisper API)
2. Samples frames and detects speaker layout via Claude Vision (who's on which side, screen share segments)
3. Claude reads the full transcript, picks the best 5-7 clip-worthy moments
4. Generates a review file. You approve or reject.

**Phase 2 — Cut + Prep (automated):**
5. FFmpeg cuts approved clips with fade in/out
6. Builds render-ready data (caption timing, zoom keyframes, highlight words)

**Phase 3 — The Look (Remotion, coming soon):**
7. Renders clips with animated captions, speaker zoom, progress bar, branding

## Quick start

```bash
# Prerequisites
pip install openai anthropic
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

# Run individual steps
python pipeline.py input/video.mp4 --step transcribe
python pipeline.py input/video.mp4 --step layout
python pipeline.py input/video.mp4 --step select
python pipeline.py input/video.mp4 --step cut
python pipeline.py input/video.mp4 --step prepare
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
│   └── prepare_render.py    # Merge captions + zoom + brand → Remotion input
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
- [x] Phase 2: FFmpeg cutting + render data prep
- [ ] Phase 3: Remotion renderer (animated captions, speaker zoom, progress bar)
- [ ] Speaker diarization (who said what) via WhisperX or API
- [ ] Auto-hook generation (text overlay for first 3 seconds)
- [ ] Batch processing (multiple videos)
- [ ] Social platform export presets (Reels, TikTok, Shorts, LinkedIn)
