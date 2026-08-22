"""
Originate Step 5: Derive LinkedIn/Grapevines content + the blueprint doc.

One research run feeds five surfaces. From the approved script this
generates:
  - blueprint.md        — the downloadable lead magnet (email capture asset)
  - newsletter.md       — Monday newsletter draft (Grapevines voice)
  - linkedin_posts.md   — N standalone posts mapped to content themes
  - shorts_briefs.json  — moments for the EXISTING viddy pipeline to cut
                          once the long-form is rendered

Usage:
    python scripts/originate/derive_content.py originate/<slug>/script.json

Output:
    originate/<slug>/content/
"""

import argparse
import json
import re
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent.parent

SYSTEM_PROMPT = """You are the content lead for Grapevines (AI career strategy) deriving multi-surface content from a finished YouTube script. The author is Manav Thaker: founder, ex-Head of Product, operator voice — practical, specific, no hype, no emojis, no engagement-bait.

Rules:
- Every piece must stand alone (no "as I said in my video" framing; the video is linked, not required).
- LinkedIn posts: 120-220 words, one idea each, line breaks for scannability, no hashtag spam (max 2). Each post maps to one theme from the provided list.
- Newsletter: 400-700 words, has a named takeaway section and links the video + blueprint.
- Blueprint doc: the actual deliverable promised in the video — idea, evidence table, tool stack with costs, week-by-week playbook, honest economics, sources. Someone should be able to act on it without watching.
- Shorts briefs: pick moments that are self-contained with a hook in the first line, 30-75s of VO.
- Never promise income. Sourced numbers only."""


def main():
    parser = argparse.ArgumentParser(description="Derive LI/newsletter/blueprint content")
    parser.add_argument("script", help="Path to approved script.json")
    parser.add_argument("--config", default=str(ROOT / "config" / "blueprint.json"))
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)
    d_cfg = config["derivation"]
    script_path = Path(args.script)
    with open(script_path) as f:
        script = json.load(f)

    content_dir = script_path.parent / "content"
    content_dir.mkdir(exist_ok=True)

    user_prompt = f"""Themes for LinkedIn posts: {d_cfg['linkedin_themes']}
Number of LinkedIn posts: {d_cfg['linkedin_posts']}
Number of shorts briefs: {d_cfg['shorts_briefs']}
CTA assets: blueprint download (lead magnet), grapevines.ai/intel (secondary).

Script JSON:
{json.dumps(script, indent=2)}

Return JSON:
{{
  "blueprint_md": str,      // full markdown doc
  "newsletter_md": str,     // full markdown draft
  "linkedin_posts": [{{"theme": str, "post": str}}],
  "shorts_briefs": [{{"title": str, "section": str, "first_beat": int, "last_beat": int, "hook_line": str, "why": str}}]
}}"""

    client = anthropic.Anthropic()
    print("Deriving content...")
    response = client.messages.create(
        model=config["models"]["derive"],
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = re.sub(r"^```(json)?|```$", "", response.content[0].text.strip(), flags=re.MULTILINE).strip()
    out = json.loads(text)

    (content_dir / "blueprint.md").write_text(out["blueprint_md"])
    (content_dir / "newsletter.md").write_text(out["newsletter_md"])

    posts_md = "\n\n---\n\n".join(f"**Theme: {p['theme']}**\n\n{p['post']}" for p in out["linkedin_posts"])
    (content_dir / "linkedin_posts.md").write_text(f"# LinkedIn posts: {script['working_title']}\n\n{posts_md}\n")

    with open(content_dir / "shorts_briefs.json", "w") as f:
        json.dump(out["shorts_briefs"], f, indent=2)

    print(f"\n✓ blueprint.md, newsletter.md, {len(out['linkedin_posts'])} LI posts, "
          f"{len(out['shorts_briefs'])} shorts briefs → {content_dir}")
    print("\nShorts: after rendering the long-form, run the standard viddy pipeline on it —")
    print("  python pipeline.py output/<slug>/blueprint_final.mp4")
    print("shorts_briefs.json tells the clip selector where to look (pass via --context).")


if __name__ == "__main__":
    main()
