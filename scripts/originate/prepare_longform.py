"""
Originate Step 4: Merge script + VO timing + assets + brand into
render data for the Remotion Blueprint composition (16:9 long-form).

Beat→time mapping: each section's beats are assigned time ranges by
matching beat vo_text word counts against the section's word timeline
(same word shape as the shorts pipeline).

Usage:
    python scripts/originate/prepare_longform.py originate/<slug>/script.json

Output:
    originate/<slug>/render_data/blueprint.json
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def load_json(path):
    with open(path) as f:
        return json.load(f)


def group_words(words: list[dict], per_group: int, highlights: set[str]) -> list[dict]:
    """Group words into caption groups (same shape the shorts renderer uses)."""
    groups = []
    for i in range(0, len(words), per_group):
        chunk = words[i:i + per_group]
        groups.append({
            "text": " ".join(w["word"] for w in chunk),
            "words": [{
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
                "highlight": w["word"].strip(".,!?").lower() in highlights,
            } for w in chunk],
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
        })
    return groups


def main():
    parser = argparse.ArgumentParser(description="Prepare long-form render data")
    parser.add_argument("script", help="Path to script.json")
    parser.add_argument("--config", default=str(ROOT / "config" / "blueprint.json"))
    args = parser.parse_args()

    script_path = Path(args.script)
    base = script_path.parent
    script = load_json(script_path)
    config = load_json(args.config)
    brand = load_json(ROOT / "config" / "brand.json")
    words = load_json(base / "vo" / "words.json")
    timeline = load_json(base / "vo" / "timeline.json")
    assets = load_json(base / "assets.json")

    r_cfg = config["render"]
    fps = r_cfg["fps"]

    # Highlight vocabulary from all beats
    highlights = set()
    for s in script["sections"]:
        for b in s.get("beats", []):
            for h in b.get("highlight_words", []):
                for token in h.lower().split():
                    highlights.add(token.strip(".,!?"))

    # Map beats to time ranges by walking each section's words
    asset_index = {(s["id"], a["beat"]): a["spec"]
                   for s in assets["sections"] for a in s["assets"]}
    sections_out = []
    for s in script["sections"]:
        sec_words = [w for w in words if w["section"] == s["id"]]
        sec_meta = next((t for t in timeline["sections"] if t["section"] == s["id"]), None)
        if not sec_words or not sec_meta:
            continue
        total_beat_words = sum(len(b["vo_text"].split()) for b in s["beats"]) or 1
        beats_out, cursor = [], 0
        for b in s["beats"]:
            n = round(len(b["vo_text"].split()) / total_beat_words * len(sec_words))
            n = max(1, n)
            chunk = sec_words[cursor:cursor + n] or sec_words[-1:]
            cursor += n
            beats_out.append({
                "beat": b["beat"],
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "asset": asset_index.get((s["id"], b["beat"]),
                                         {"type": "slide", "title": "", "bullets": []}),
            })
        sections_out.append({
            "id": s["id"],
            "start": sec_meta["start"],
            "duration": sec_meta["duration"],
            "audio": f"vo/{sec_meta['audio']}",
            "beats": beats_out,
        })

    total = timeline["total_seconds"]
    render_data = {
        "slug": script["slug"],
        "title": script["working_title"],
        "duration_seconds": total,
        "fps": fps,
        "total_frames": int(total * fps) + 1,
        "resolution": r_cfg["resolution"],
        "sections": sections_out,
        "captions": {
            "groups": group_words(words, r_cfg["words_per_group"], highlights),
            "style": r_cfg["caption_style"],
            "words_per_group": r_cfg["words_per_group"],
        },
        "brand": brand,
    }

    out_dir = base / "render_data"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "blueprint.json"
    with open(out, "w") as f:
        json.dump(render_data, f, indent=2)
    print(f"✓ Render data → {out} ({total:.0f}s, {len(sections_out)} sections)")


if __name__ == "__main__":
    main()
