"""
Originate Step 2: Generate voiceover audio with word-level timestamps.

Reads the approved script.json and produces one MP3 per section via the
ElevenLabs with-timestamps API, plus a words.json compatible with the
caption pipeline (same word/start/end shape as Whisper output).

Refuses to run if any [POV: ...] tokens remain in the script (Gate 1
was skipped).

Usage:
    python scripts/originate/generate_vo.py originate/<slug>/script.json

Output:
    originate/<slug>/vo/<section_id>.mp3
    originate/<slug>/vo/words.json     # [{section, word, start, end}] global timeline
    originate/<slug>/vo/timeline.json  # per-section start/duration
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.parent
API_BASE = "https://api.elevenlabs.io/v1"


def section_text(section: dict) -> str:
    return " ".join(beat["vo_text"].strip() for beat in section.get("beats", []))


def chars_to_words(alignment: dict, offset: float) -> list[dict]:
    """Convert ElevenLabs character alignment to word-level timestamps."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words, current, w_start = [], "", None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if current:
                words.append({"word": current, "start": w_start + offset, "end": prev_end + offset})
                current, w_start = "", None
        else:
            if not current:
                w_start = s
            current += ch
            prev_end = e
    if current:
        words.append({"word": current, "start": w_start + offset, "end": prev_end + offset})
    return words


def main():
    parser = argparse.ArgumentParser(description="Generate section voiceovers via ElevenLabs")
    parser.add_argument("script", help="Path to approved script.json")
    parser.add_argument("--config", default=str(ROOT / "config" / "blueprint.json"))
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    with open(args.config) as f:
        vo_cfg = json.load(f)["voiceover"]
    if vo_cfg["voice_id"] == "SET_ME":
        print("Error: set voiceover.voice_id in config/blueprint.json", file=sys.stderr)
        sys.exit(1)

    script_path = Path(args.script)
    with open(script_path) as f:
        script = json.load(f)

    raw = json.dumps(script)
    if "[POV:" in raw:
        print("Error: script still contains [POV: ...] tokens — Gate 1 not complete.", file=sys.stderr)
        sys.exit(1)

    vo_dir = script_path.parent / "vo"
    vo_dir.mkdir(exist_ok=True)

    all_words, timeline, offset = [], [], 0.0
    for section in script["sections"]:
        text = section_text(section)
        if not text:
            continue
        print(f"  VO: {section['id']} ({len(text)} chars)")
        resp = requests.post(
            f"{API_BASE}/text-to-speech/{vo_cfg['voice_id']}/with-timestamps",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": vo_cfg["model_id"],
                "voice_settings": {
                    "stability": vo_cfg["stability"],
                    "similarity_boost": vo_cfg["similarity_boost"],
                },
                "output_format": vo_cfg.get("output_format", "mp3_44100_128"),
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()

        audio_path = vo_dir / f"{section['id']}.mp3"
        audio_path.write_bytes(base64.b64decode(data["audio_base64"]))

        words = chars_to_words(data["alignment"], offset)
        for w in words:
            w["section"] = section["id"]
        all_words.extend(words)

        duration = data["alignment"]["character_end_times_seconds"][-1]
        timeline.append({"section": section["id"], "start": offset, "duration": duration,
                         "audio": str(audio_path.name)})
        offset += duration

    with open(vo_dir / "words.json", "w") as f:
        json.dump(all_words, f, indent=2)
    with open(vo_dir / "timeline.json", "w") as f:
        json.dump({"total_seconds": offset, "sections": timeline}, f, indent=2)

    print(f"\n✓ {len(timeline)} sections, {offset:.1f}s total → {vo_dir}")


if __name__ == "__main__":
    main()
