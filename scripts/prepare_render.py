"""
Step 5: Prepare render data for Remotion.

Combines cut clips, word-level caption data, layout info, and brand config
into a single JSON payload per clip that Remotion can consume.

Usage:
    python scripts/prepare_render.py review/<name>/transcript.json clips/<name>/manifest.json

Output:
    clips/<video_name>/render_data/clip_01.json, clip_02.json, etc.
"""

import argparse
import json
import os
from pathlib import Path


def load_brand_config() -> dict:
    root = Path(__file__).parent.parent
    with open(root / "config" / "brand.json") as f:
        return json.load(f)


def load_default_config() -> dict:
    root = Path(__file__).parent.parent
    with open(root / "config" / "default.json") as f:
        return json.load(f)


def get_words_for_range(words: list[dict], start: float, end: float, padding: float = 0.5) -> list[dict]:
    """Extract words that fall within a time range."""
    actual_start = max(0, start - padding)
    actual_end = end + padding
    return [
        {
            "word": w["word"],
            "start": round(w["start"] - actual_start, 3),  # relative to clip start
            "end": round(w["end"] - actual_start, 3)
        }
        for w in words
        if w["start"] >= actual_start and w["end"] <= actual_end
    ]


def build_caption_groups(words: list[dict], words_per_group: int = 3) -> list[dict]:
    """Group words into caption display groups (e.g., 3 words at a time)."""
    groups = []
    for i in range(0, len(words), words_per_group):
        group = words[i:i + words_per_group]
        if not group:
            continue
        groups.append({
            "text": " ".join(w["word"] for w in group),
            "words": group,
            "start": group[0]["start"],
            "end": group[-1]["end"]
        })
    return groups


def build_speaker_timeline(clip_data: dict, layout_data: dict, clip_start_offset: float, clip_duration: float) -> list[dict]:
    """Build a continuous speaker timeline for the entire clip.

    Uses the speaker_timeline from Claude's clip selection (who's talking when)
    combined with layout data (where each speaker is positioned) to produce
    a frame-by-frame speaker tracking guide for the renderer.
    """
    speaker_segments = clip_data.get("speaker_timeline", [])
    layout_segments = layout_data.get("segments", [])

    timeline = []

    if speaker_segments:
        # Use Claude's speaker timeline (preferred, most accurate)
        for seg in speaker_segments:
            from_s = seg.get("from", 0) - clip_start_offset
            to_s = seg.get("to", 0) - clip_start_offset
            speaker = seg.get("speaker", "unknown")
            position = seg.get("position", "center")

            # If position is missing, try to infer from layout
            if position == "center" or not position:
                for lseg in layout_segments:
                    abs_time = seg.get("from", 0)
                    if lseg.get("from_seconds", 0) <= abs_time <= lseg.get("to_seconds", 99999):
                        # Check speaker_positions
                        positions = lseg.get("speaker_positions", {})
                        for side, sid in positions.items():
                            if sid == speaker:
                                position = side
                                break
                        # Also check active_speaker for single_speaker layouts
                        if position == "center" and lseg.get("active_speaker") == speaker:
                            position = "center"  # single speaker, center is correct
                        break

            timeline.append({
                "from_seconds": round(max(0, from_s), 2),
                "to_seconds": round(min(clip_duration, to_s), 2),
                "speaker": speaker,
                "position": position
            })
    else:
        # Fallback: use layout segments to build a basic timeline
        for lseg in layout_segments:
            from_s = lseg.get("from_seconds", 0) - clip_start_offset
            to_s = lseg.get("to_seconds", 99999) - clip_start_offset

            # Skip segments outside clip range
            if to_s < 0 or from_s > clip_duration:
                continue

            speaker = lseg.get("active_speaker", "unknown")
            position = "center"
            positions = lseg.get("speaker_positions", {})
            for side, sid in positions.items():
                if sid == speaker:
                    position = side
                    break

            timeline.append({
                "from_seconds": round(max(0, from_s), 2),
                "to_seconds": round(min(clip_duration, to_s), 2),
                "speaker": speaker,
                "position": position
            })

    return timeline


def build_zoom_moments(clip_data: dict, clip_start_offset: float) -> list[dict]:
    """Build zoom keyframes for emphasis moments (tighter crop during key points)."""
    zoom_moments = clip_data.get("zoom_moments", [])

    timeline = []
    for zm in zoom_moments:
        at = zm.get("at_seconds", 0) - clip_start_offset
        target = zm.get("target", "unknown")
        hold = zm.get("hold_seconds", 5)

        timeline.append({
            "at_seconds": round(at, 2),
            "target_speaker": target,
            "hold_seconds": hold,
            "transition": "ease_in_out"
        })

    return timeline


def main():
    parser = argparse.ArgumentParser(description="Prepare render data for Remotion")
    parser.add_argument("transcript", help="Path to transcript.json")
    parser.add_argument("manifest", help="Path to clips manifest.json")
    parser.add_argument("--layout", help="Path to layout.json")
    parser.add_argument("--output-dir", help="Output directory for render data")
    args = parser.parse_args()

    # Load inputs
    with open(args.transcript) as f:
        transcript = json.load(f)

    with open(args.manifest) as f:
        manifest = json.load(f)

    layout_data = {}
    if args.layout and os.path.exists(args.layout):
        with open(args.layout) as f:
            layout_data = json.load(f)

    brand = load_brand_config()
    config = load_default_config()
    render_config = config["render"]

    # Output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = str(Path(args.manifest).parent / "render_data")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Preparing render data for {len(manifest)} clips...")

    for entry in manifest:
        clip_num = entry["clip_number"]
        clip_data = entry["clip_data"]
        clip_file = entry["file"]
        source_start = entry["source_start"]
        source_end = entry["source_end"]

        # Get words for this clip's time range
        padding = config["cutting"]["padding_before_seconds"]
        words = get_words_for_range(transcript["words"], source_start, source_end, padding)

        # Build caption groups
        caption_groups = build_caption_groups(words, render_config["words_per_group"])

        # Build continuous speaker timeline + zoom emphasis moments
        duration = (source_end + config["cutting"]["padding_after_seconds"]) - (source_start - padding)
        speaker_timeline = build_speaker_timeline(clip_data, layout_data, source_start - padding, duration)
        zoom_emphasis = build_zoom_moments(clip_data, source_start - padding)

        # Mark highlight words
        highlight_words = set(w.lower() for w in clip_data.get("highlight_words", []))
        for group in caption_groups:
            for word in group["words"]:
                word["highlight"] = any(
                    hw in word["word"].lower()
                    for hw in highlight_words
                )

        render_data = {
            "clip_number": clip_num,
            "source_video": os.path.abspath(clip_file),
            "duration_seconds": round(duration, 2),
            "fps": render_config["fps"],
            "total_frames": int(duration * render_config["fps"]),
            "formats": render_config["formats"],
            "resolutions": render_config["resolution"],

            "hook": clip_data.get("hook", ""),
            "title": clip_data.get("suggested_title", ""),

            "captions": {
                "groups": caption_groups,
                "style": render_config["caption_style"],
                "words_per_group": render_config["words_per_group"]
            },

            "speaker_tracking": {
                "timeline": speaker_timeline,
                "base_scale": 1.6,
                "transition_seconds": 0.4
            },

            "zoom_emphasis": {
                "moments": zoom_emphasis,
                "zoom_scale": 2.2
            },

            "brand": brand,

            "progress_bar": {
                "enabled": True,
                "position": "top",
                "height_px": brand["progress_bar_height_px"],
                "color": brand["colors"]["progress_bar"],
                "bg_color": brand["colors"]["progress_bar_bg"]
            }
        }

        output_path = os.path.join(output_dir, f"clip_{clip_num:02d}.json")
        with open(output_path, "w") as f:
            json.dump(render_data, f, indent=2)

        print(f"  Clip {clip_num}: {len(caption_groups)} caption groups, {len(speaker_timeline)} speaker segments, {len(zoom_emphasis)} zoom points")

    print(f"\nRender data saved to {output_dir}/")
    print("Next: Run Remotion to render final clips.")


if __name__ == "__main__":
    main()
