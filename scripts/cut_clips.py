"""
Step 4: Cut approved clips from source video using FFmpeg.

Reads clips.json (after user review), cuts each approved clip
with configurable padding and fade effects.

Usage:
    python scripts/cut_clips.py input/video.mp4 review/<name>/clips.json

Output:
    clips/<video_name>/clip_01.mp4, clip_02.mp4, etc.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_config() -> dict:
    root = Path(__file__).parent.parent
    with open(root / "config" / "default.json") as f:
        return json.load(f)


def cut_clip(
    video_path: str,
    output_path: str,
    start: float,
    end: float,
    padding_before: float = 0.5,
    padding_after: float = 0.3,
    fade_in_ms: int = 200,
    fade_out_ms: int = 300
) -> bool:
    """Cut a single clip from the source video."""
    actual_start = max(0, start - padding_before)
    duration = (end + padding_after) - actual_start

    fade_in_s = fade_in_ms / 1000
    fade_out_s = fade_out_ms / 1000
    fade_out_start = duration - fade_out_s

    # Video filter: fade in/out
    vf = f"fade=in:st=0:d={fade_in_s},fade=out:st={fade_out_start}:d={fade_out_s}"
    # Audio filter: fade in/out
    af = f"afade=in:st=0:d={fade_in_s},afade=out:st={fade_out_start}:d={fade_out_s}"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(actual_start),
        "-i", video_path,
        "-t", str(duration),
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FFmpeg error: {result.stderr[:200]}", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Cut approved clips from source video")
    parser.add_argument("video", help="Path to source video")
    parser.add_argument("clips_json", help="Path to clips.json")
    parser.add_argument("--output-dir", help="Output directory for cut clips")
    args = parser.parse_args()

    video_path = os.path.abspath(args.video)
    video_name = Path(video_path).stem
    root = Path(__file__).parent.parent

    # Load clips
    with open(args.clips_json) as f:
        clips_data = json.load(f)

    # Load config
    config = load_config()
    cut_config = config["cutting"]

    # Filter to approved clips
    approved = [c for c in clips_data.get("clips", []) if c.get("approved", True)]
    if not approved:
        print("No approved clips found. Edit clips.json and set 'approved': true.")
        sys.exit(1)

    # Sort by rank
    approved.sort(key=lambda c: c.get("rank", 99))

    # Output directory
    output_dir = args.output_dir or str(root / "clips" / video_name)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Cutting {len(approved)} approved clips...")

    manifest = []
    for i, clip in enumerate(approved, 1):
        output_path = os.path.join(output_dir, f"clip_{i:02d}.mp4")

        start = clip["start_seconds"]
        end = clip["end_seconds"]
        duration = end - start

        print(f"  Clip {i}: {start:.1f}s - {end:.1f}s ({duration:.0f}s) — {clip.get('suggested_title', '')}")

        success = cut_clip(
            video_path,
            output_path,
            start,
            end,
            padding_before=cut_config["padding_before_seconds"],
            padding_after=cut_config["padding_after_seconds"],
            fade_in_ms=cut_config["fade_in_ms"],
            fade_out_ms=cut_config["fade_out_ms"]
        )

        if success:
            manifest.append({
                "clip_number": i,
                "file": output_path,
                "source_start": start,
                "source_end": end,
                "clip_data": clip
            })
            print(f"    Saved: {output_path}")
        else:
            print(f"    FAILED: clip {i}")

    # Save manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{len(manifest)} clips cut successfully.")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
