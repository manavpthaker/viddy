"""
Originate Step 3: Turn beat-level asset hints into a concrete asset plan.

Claude expands each beat's asset_hint into a render-ready spec:
slides (title/bullets), charts (type/series/labels), b-roll search
queries (Pexels, reuses fetch_broll conventions), screen recordings
(a shot list for you to capture), and logo cards.

Gate 2: review assets_review.md, edit assets.json, then render.

Usage:
    python scripts/originate/plan_assets.py originate/<slug>/script.json

Output:
    originate/<slug>/assets.json
    originate/<slug>/assets_review.md
"""

import argparse
import json
import re
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent.parent

SYSTEM_PROMPT = """You are the art director for a documentary-style business YouTube channel. Clean, minimal, high-end. You ONLY output valid JSON. No markdown fences.

For each beat you receive, expand its asset_hint into exactly one concrete asset spec:

- slide:      {"type":"slide","title":str,"bullets":[str] (max 3, <=8 words each)}
- chart:      {"type":"chart","chart_type":"bar"|"line"|"waterfall","title":str,"series":[{"label":str,"value":float}],"unit":str,"source":str}
- broll:      {"type":"broll","search_query":str (2-4 words, Pexels-friendly),"reason":str}
- screen_rec: {"type":"screen_rec","tool":str,"action":str,"est_seconds":int}   // human captures this
- logo:       {"type":"logo","company":str,"caption":str}

Rules:
- Charts must only use numbers present in the beat/source. Never invent data.
- Prefer slide/chart for economics and playbook sections; broll for narrative moments.
- screen_rec only where seeing the tool genuinely adds value (max 4 per video)."""


def build_review_md(assets: dict) -> str:
    lines = ["# Asset plan review", "",
             "**GATE 2.** Edit assets.json to swap/kill assets. screen_rec items are YOUR shot list:",
             ""]
    shot_list = []
    for section in assets["sections"]:
        lines.append(f"## {section['id']}")
        for a in section["assets"]:
            spec = a["spec"]
            lines.append(f"- beat {a['beat']}: **{spec['type']}** — "
                         + (spec.get("title") or spec.get("search_query")
                            or spec.get("company") or f"{spec.get('tool','')}: {spec.get('action','')}"))
            if spec["type"] == "screen_rec":
                shot_list.append(f"- [ ] {spec['tool']}: {spec['action']} (~{spec.get('est_seconds', 20)}s) → save to originate/<slug>/screen_recs/")
        lines.append("")
    if shot_list:
        lines += ["## Your shot list (record these)", ""] + shot_list + [""]
    lines += ["When done: `python originate.py <slug> --render`"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Plan render assets from script")
    parser.add_argument("script", help="Path to approved script.json")
    parser.add_argument("--config", default=str(ROOT / "config" / "blueprint.json"))
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)
    script_path = Path(args.script)
    with open(script_path) as f:
        script = json.load(f)

    beats_payload = [
        {"section": s["id"],
         "beats": [{"beat": b["beat"], "vo_text": b["vo_text"],
                    "asset_hint": b.get("asset_hint", ""), "source": b.get("source")}
                   for b in s.get("beats", [])]}
        for s in script["sections"]
    ]

    client = anthropic.Anthropic()
    print("Planning assets...")
    response = client.messages.create(
        model=config["models"]["assets"],
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content":
                   "Expand every beat into one asset spec. Return JSON: "
                   '{"sections":[{"id":str,"assets":[{"beat":int,"spec":{...}}]}]}\n\n'
                   + json.dumps(beats_payload, indent=2)}],
    )
    text = re.sub(r"^```(json)?|```$", "", response.content[0].text.strip(), flags=re.MULTILINE).strip()
    assets = json.loads(text)

    out = script_path.parent / "assets.json"
    with open(out, "w") as f:
        json.dump(assets, f, indent=2)
    (script_path.parent / "assets_review.md").write_text(build_review_md(assets))

    n = sum(len(s["assets"]) for s in assets["sections"])
    print(f"\n✓ {n} assets planned → {out}")
    print("GATE 2: review assets_review.md; record any screen_rec items.")


if __name__ == "__main__":
    main()
