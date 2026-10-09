"""
Step 7: Package approved clips for sharing.

For each cut clip, generate a platform-ready shareability pack and the assets
needed to post it:

  - 3 hook variants (on-screen / opening line A/B options)
  - a comment-bait question (drives replies = reach)
  - per-platform copy for LinkedIn and YouTube Shorts (caption + hashtags)
  - the single most repostable quote (verbatim) -> feeds the quote card
  - an auto-picked cover frame (cropped to the speaker, the actual thumbnail)

Runs in Phase 2 after prepare_render.py (so it only packages approved clips).

Usage:
    python scripts/package_clips.py review/<name>/transcript.json clips/<name>/manifest.json

Output:
    clips/<name>/social/clip_01.json   (structured pack + quote-card payload)
    clips/<name>/social/clip_01.md     (copy/paste-ready)
    clips/<name>/social/cover_01.jpg   (thumbnail, cropped to speaker)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic


PLATFORMS = ["linkedin", "youtube_shorts"]

# Must match the reframe math in remotion/src/components/SpeakerZoom.tsx so the
# cover thumbnail frames the speaker the same way the rendered clip does.
FACE_HEIGHT_FRACTION = 0.4
FACE_VERTICAL_ANCHOR = 0.45
MIN_SCALE = 1.0
MAX_SCALE = 2.4


PACK_SYSTEM = """You write short-form social copy that gets clips shared. You match the show's voice: clean, high-end, minimal, no hype, no emoji spam. You never invent facts or quotes — quotes must be verbatim from the transcript. You ONLY output valid JSON."""


PACK_PROMPT = """Create a shareability pack for one short clip.

{context_block}

**Clip**
Title: {title}
Current hook: {hook}
Predicted engagement driver: {driver}
Transcript (verbatim):
{excerpt}

**Produce JSON exactly in this shape:**
{{
  "best_quote": "the single most repostable sentence, VERBATIM from the transcript (<= 140 chars)",
  "hook_variants": ["3 punchy on-screen opener options, each <= 60 chars"],
  "comment_bait": "one question to pin in comments that invites replies",
  "platforms": {{
    "linkedin": {{
      "caption": "3-6 short lines: scroll-stopping first line, the insight, a soft takeaway. Line breaks as \\n. No hashtags inline.",
      "hashtags": ["3-5 professional tags, no # symbol"]
    }},
    "youtube_shorts": {{
      "title": "searchy, <= 90 chars, no clickbait",
      "description": "1-2 lines + a soft CTA",
      "hashtags": ["3-5 tags incl 'shorts', no # symbol"]
    }}
  }}
}}

Rules:
- best_quote and hook text must come from or faithfully compress the transcript.
- Keep the show's tone. No emojis except at most one tasteful accent if it fits.
- Output ONLY the JSON."""


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def build_context_block(ctx: dict) -> str:
    if not ctx:
        return ""
    parts = []
    for key, label in [("show_name", "Show"), ("host_name", "Host"),
                       ("guest_name", "Guest"), ("episode_topic", "Topic"),
                       ("audience", "Audience"), ("tone", "Tone")]:
        if ctx.get(key):
            parts.append(f"**{label}:** {ctx[key]}")
    return "\n".join(parts)


def excerpt_for_clip(transcript: dict, start: float, end: float, max_chars: int = 1200) -> str:
    words = transcript.get("words", [])
    if words:
        text = " ".join(w["word"] for w in words
                        if w["start"] >= start - 0.5 and w["end"] <= end + 0.5)
    else:
        text = " ".join(seg["text"].strip() for seg in transcript.get("segments", [])
                        if seg["end"] >= start and seg["start"] <= end)
    return " ".join(text.split())[:max_chars]


def parse_json(text: str) -> dict:
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return {}


def generate_pack(clip_data: dict, excerpt: str, episode_context: dict, model: str) -> dict:
    """Ask Claude for the shareability pack. Returns {} on failure."""
    driver = (clip_data.get("virality") or {}).get("predicted_driver") or "watch_through"
    prompt = PACK_PROMPT.format(
        context_block=build_context_block(episode_context),
        title=clip_data.get("suggested_title", ""),
        hook=clip_data.get("hook", ""),
        driver=driver,
        excerpt=excerpt,
    )
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=1500, system=PACK_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(resp.content[0].text)
    except Exception as e:
        print(f"    Warning: pack generation failed ({e})", file=sys.stderr)
        return {}


# ── Cover frame ──

def probe_dimensions(video_path: str) -> tuple[int, int]:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-select_streams", "v:0", "-show_streams", video_path]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    try:
        s = json.loads(out)["streams"][0]
        return int(s["width"]), int(s["height"])
    except (KeyError, IndexError, json.JSONDecodeError):
        return 1920, 1080


def pick_cover_keyframe(reframe: dict) -> dict | None:
    """Choose the most prominent speaking frame as the thumbnail."""
    kfs = (reframe or {}).get("keyframes", [])
    if not kfs:
        return None
    speaking = [k for k in kfs if k.get("speaking")] or kfs
    # Prefer the largest (closest) face; tiebreak toward the first third.
    return max(speaking, key=lambda k: (round(k.get("face_h", 0), 3), -k["t"]))


def extract_cover(video_path: str, reframe: dict, out_path: str) -> bool:
    """Extract a vertical (1080x1920) cover cropped to the speaker, matching the
    renderer's framing. Falls back to a centered crop when there is no face."""
    W, H = probe_dimensions(video_path)
    out_w, out_h = 1080, 1920

    kf = pick_cover_keyframe(reframe)
    if kf:
        cx, cy = kf.get("cx", 0.5), kf.get("cy", 0.45)
        face_h = min(0.9, max(0.1, kf.get("face_h", 0.5)))
        t = kf["t"]
    else:
        cx, cy, face_h, t = 0.5, 0.45, 0.5, 1.0

    scale = min(MAX_SCALE, max(MIN_SCALE, FACE_HEIGHT_FRACTION / face_h))
    # Source->output pixel factor (cover-fit makes source height map to out_h).
    f = (out_h / H) * scale
    crop_w = min(W, out_w / f)
    crop_h = min(H, out_h / f)
    left = cx * W - crop_w / 2
    top = cy * H - FACE_VERTICAL_ANCHOR * crop_h
    left = max(0, min(W - crop_w, left))
    top = max(0, min(H - crop_h, top))

    vf = (f"crop={crop_w:.0f}:{crop_h:.0f}:{left:.0f}:{top:.0f},"
          f"scale={out_w}:{out_h}")
    cmd = ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video_path,
           "-frames:v", "1", "-vf", vf, "-q:v", "2", out_path]
    return subprocess.run(cmd, capture_output=True).returncode == 0


# ── Markdown rendering ──

def pack_to_markdown(clip_num: int, clip_data: dict, pack: dict) -> str:
    vir = clip_data.get("virality") or {}
    lines = [f"# Clip {clip_num}: {clip_data.get('suggested_title', '')}", ""]
    if vir.get("score") is not None:
        lines.append(f"**Virality:** 🔥 {vir['score']}/100 · drives {(vir.get('predicted_driver') or '—').replace('_','-')}")
        lines.append("")
    if pack.get("best_quote"):
        lines += [f"> {pack['best_quote']}", ""]
    if pack.get("hook_variants"):
        lines.append("**Hook variants:**")
        lines += [f"{i}. {h}" for i, h in enumerate(pack["hook_variants"], 1)]
        lines.append("")
    if pack.get("comment_bait"):
        lines += [f"**Comment bait:** {pack['comment_bait']}", ""]

    plats = pack.get("platforms", {})
    li = plats.get("linkedin")
    if li:
        lines += ["## LinkedIn", "", li.get("caption", ""), ""]
        if li.get("hashtags"):
            lines += [" ".join(f"#{h.lstrip('#')}" for h in li["hashtags"]), ""]
    yt = plats.get("youtube_shorts")
    if yt:
        lines += ["## YouTube Shorts", "", f"**Title:** {yt.get('title','')}",
                  "", yt.get("description", ""), ""]
        if yt.get("hashtags"):
            lines += [" ".join(f"#{h.lstrip('#')}" for h in yt["hashtags"]), ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Package approved clips for sharing")
    parser.add_argument("transcript", help="Path to transcript.json")
    parser.add_argument("manifest", help="Path to clips manifest.json")
    parser.add_argument("--context", help="Path to episode context JSON")
    parser.add_argument("--output-dir", help="Output dir (default: <clips>/social)")
    args = parser.parse_args()

    transcript = load_json(args.transcript)
    manifest = load_json(args.manifest)

    root = Path(__file__).parent.parent
    config = load_json(str(root / "config" / "default.json"))
    model = config["clip_selection"]["model"]

    episode_context = {}
    ctx_path = args.context or str(root / "config" / "episode.json")
    if os.path.exists(ctx_path):
        episode_context = load_json(ctx_path)

    output_dir = args.output_dir or str(Path(args.manifest).parent / "social")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Packaging {len(manifest)} clips for {', '.join(PLATFORMS)}...")

    for entry in manifest:
        clip_num = entry["clip_number"]
        clip_data = entry["clip_data"]
        clip_file = entry["file"]
        excerpt = excerpt_for_clip(transcript, entry["source_start"], entry["source_end"])

        print(f"  Clip {clip_num}: generating copy...")
        pack = generate_pack(clip_data, excerpt, episode_context, model)

        # Cover frame (uses the reframe track if tracking ran).
        reframe = {}
        reframe_path = Path(clip_file).with_suffix(".reframe.json")
        if reframe_path.exists():
            reframe = load_json(str(reframe_path))
        cover_path = os.path.join(output_dir, f"cover_{clip_num:02d}.jpg")
        cover_ok = extract_cover(clip_file, reframe, cover_path)

        # Structured output (includes the quote-card payload).
        out = {
            "clip_number": clip_num,
            "title": clip_data.get("suggested_title", ""),
            "virality": clip_data.get("virality"),
            "pack": pack,
            "cover_image": cover_path if cover_ok else None,
            "quote_card": {
                "clip_number": clip_num,
                "quote": pack.get("best_quote", clip_data.get("hook", "")),
                "attribution": episode_context.get("guest_name")
                               or episode_context.get("host_name") or "",
            },
        }
        with open(os.path.join(output_dir, f"clip_{clip_num:02d}.json"), "w") as f:
            json.dump(out, f, indent=2)
        with open(os.path.join(output_dir, f"clip_{clip_num:02d}.md"), "w") as f:
            f.write(pack_to_markdown(clip_num, clip_data, pack))

        flags = []
        if pack:
            flags.append("copy")
        if cover_ok:
            flags.append("cover")
        print(f"    -> {', '.join(flags) or 'no assets'}")

    print(f"\nShareability packs saved to {output_dir}/")
    print("Next: render quote cards with remotion/render_stills.mjs")


if __name__ == "__main__":
    main()
