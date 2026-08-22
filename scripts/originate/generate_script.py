"""
Originate Step 1: Generate a blueprint-format script from a topic + research.

Takes a topic (and optionally a research brief file) and produces a
structured script JSON plus a human review file. The pipeline STOPS
after this step — Gate 1 is where you inject your operator POV.

Usage:
    python scripts/originate/generate_script.py "AI receptionists for independent hotels" \
        --research originate/ai-receptionists/research.md

Output:
    originate/<slug>/script.json
    originate/<slug>/script_review.md
"""

import argparse
import json
import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent.parent


SYSTEM_PROMPT = """You are a senior writer for a YouTube channel about AI business blueprints. The channel's audience is senior professionals leaving a broken job market who want to build income outside employment.

You ONLY output valid JSON matching the schema described in the user message. No markdown fences, no commentary.

**Editorial rules:**
- Documentary rigor. Every revenue/cost claim must carry a source from the research brief, or be marked "estimate" with reasoning.
- NEVER promise income. Frame as "Company X did Y" and "realistic range is A-B because C".
- Operator voice: practical, specific, calm. No hype words ("insane", "crazy", "secret").
- The hook must contain the idea AND a real number within the first two sentences.
- Each beat's vo_text is 1-3 sentences of natural spoken prose (this goes to text-to-speech).
- Mark 2-4 highlight words per beat — the numbers and punch phrases.
- asset_hint describes what should be on screen: "chart: X over time", "broll: <search query>", "slide: <title + 3 bullets>", "screen_rec: <tool> doing <thing>", "logo: <company>".
- Where the writer's personal experience would strengthen a beat, insert the literal token [POV: <one-line suggestion of what the host could add from experience>] in vo_text. The human will replace these at review.
"""

SCHEMA_HINT = """Return JSON:
{
  "topic": str,
  "working_title": str,
  "title_options": [str, str, str],
  "thumbnail_concepts": [str, str],
  "description_draft": str,
  "sections": [
    {
      "id": str,            // one of the section ids provided
      "beats": [
        {
          "beat": int,
          "vo_text": str,
          "highlight_words": [str],
          "asset_hint": str,
          "source": str | null
        }
      ]
    }
  ],
  "sources": [{"claim": str, "source": str}],
  "blueprint_summary": {
    "idea": str,
    "who_its_for": str,
    "evidence_companies": [str],
    "tool_stack": [{"tool": str, "role": str, "monthly_cost": str}],
    "first_customer_plan": str,
    "realistic_economics": str
  }
}"""


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


def build_review_md(script: dict) -> str:
    lines = [
        f"# Script review: {script['working_title']}",
        "",
        "**GATE 1 — your POV pass.** Edit `script.json` directly:",
        "- Replace every `[POV: ...]` token with your own experience/take (required — this is the monetization moat).",
        "- Rewrite anything that doesn't sound like you.",
        "- Check every number against the source. Delete claims you can't stand behind.",
        "",
        f"**Title options:** {' | '.join(script.get('title_options', []))}",
        "",
    ]
    pov_count = 0
    for section in script.get("sections", []):
        lines.append(f"## {section['id']}")
        for beat in section.get("beats", []):
            marker = ""
            if "[POV:" in beat.get("vo_text", ""):
                pov_count += 1
                marker = "  ⚠️ POV NEEDED"
            lines.append(f"- ({beat['beat']}){marker} {beat['vo_text']}")
            if beat.get("source"):
                lines.append(f"  - source: {beat['source']}")
        lines.append("")
    lines.insert(4, f"**POV insertions required: {pov_count}**")
    lines += [
        "---",
        "When done, continue with:",
        "```",
        "python originate.py <slug> --continue",
        "```",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate blueprint script from topic")
    parser.add_argument("topic", help="The business idea / video topic")
    parser.add_argument("--research", help="Path to research brief (md/txt). Strongly recommended.")
    parser.add_argument("--config", default=str(ROOT / "config" / "blueprint.json"))
    parser.add_argument("--output-dir", help="Override output dir (default originate/<slug>)")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    research = ""
    if args.research:
        research = Path(args.research).read_text()
    else:
        print("WARNING: no --research brief. Script will be thin and sources weak.", file=sys.stderr)

    slug = slugify(args.topic)
    out_dir = Path(args.output_dir) if args.output_dir else ROOT / "originate" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    sections_spec = json.dumps(config["format"]["sections"], indent=2)
    user_prompt = f"""Channel positioning: {config['channel']['positioning']}
Audience: {config['channel']['audience']}
Tone: {config['channel']['tone']}
Target duration: {config['format']['target_duration_minutes']} minutes.

Section structure (write beats for each, hitting target_seconds of spoken audio at ~150 wpm):
{sections_spec}

Topic: {args.topic}

Research brief:
{research if research else '(none provided — be conservative, mark everything as estimate)'}

{SCHEMA_HINT}"""

    client = anthropic.Anthropic()
    print(f"Generating script for: {args.topic}")
    response = client.messages.create(
        model=config["models"]["script"],
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = response.content[0].text.strip()
    # Strip accidental fences
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    script = json.loads(text)
    script["slug"] = slug

    script_path = out_dir / "script.json"
    with open(script_path, "w") as f:
        json.dump(script, f, indent=2)

    review_path = out_dir / "script_review.md"
    review_path.write_text(build_review_md(script))

    print(f"\n✓ Script: {script_path}")
    print(f"✓ Review: {review_path}")
    print("\nGATE 1: Edit script.json (replace [POV: ...] tokens), then run --continue.")


if __name__ == "__main__":
    main()
