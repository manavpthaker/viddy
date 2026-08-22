# Viddy Originate — blueprint video pipeline

Topic → researched script → your POV pass → VO → assets → 16:9 long-form render → LinkedIn/Grapevines derivatives → shorts (via the existing pipeline).

One research run feeds five surfaces: YouTube long-form, Shorts, LinkedIn posts, Monday newsletter, and the downloadable blueprint doc (email capture).

## Flow

```
originate.py new "topic" --research brief.md
        │  scripts/originate/generate_script.py → script.json + script_review.md
        ▼
   GATE 1 (you): replace every [POV: ...] token, edit voice, verify numbers
        │
originate.py continue <slug>
        │  generate_vo.py    → vo/*.mp3 + word timestamps (ElevenLabs)
        │  plan_assets.py    → assets.json + assets_review.md
        ▼
   GATE 2 (you): approve asset plan, record screen_rec shot list
        │
originate.py render <slug>
        │  prepare_longform.py → render_data/blueprint.json
        │  derive_content.py   → content/{blueprint,newsletter,linkedin_posts}.md + shorts_briefs.json
        ▼
   GATE 3 (you): preview in Remotion Studio, then render:
        cd remotion && npx remotion render src/index.ts Blueprint ../output/<slug>.mp4 \
            --props=../originate/<slug>/render_data/blueprint.json
        │
        ▼
Shorts: python pipeline.py output/<slug>.mp4   (existing viddy pipeline)
```

## Setup

```bash
pip install anthropic requests
export ANTHROPIC_API_KEY=sk-ant-...
export ELEVENLABS_API_KEY=...
# Set voiceover.voice_id in config/blueprint.json (clone your own voice in ElevenLabs)
# Set channel.name in config/blueprint.json
```

## Config

`config/blueprint.json` — channel positioning, section structure (hook/idea/evidence/stack/playbook/economics/cta), models, VO settings, derivation counts. `config/brand.json` is shared with the shorts pipeline.

## Compliance notes

- Gate 1 is mandatory. The VO step refuses to run if `[POV: ...]` tokens remain — an unedited AI script is exactly what YouTube's inauthentic-content policy demonetizes.
- Check the AI-content disclosure box on upload (Jan 2026 policy).
- Charts only use numbers with sources; the script generator marks unsourced claims as estimates.

## Not built yet (Phase C)

- `upload_youtube.py` (YouTube Data API v3: metadata, scheduling, A/B titles)
- Analytics readback → topic scoring loop
- fetch_broll.py integration for originate asset plans (currently b-roll specs are emitted but not auto-fetched)
- Audio files need to be reachable by Remotion `staticFile` — copy `vo/` into `remotion/public/` or symlink before rendering (add to render step later)
