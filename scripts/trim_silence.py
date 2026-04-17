"""
Preprocessing step: trim silence from cut clips.

DOAC-style clips are tight — no dead air, no long pauses.
This script detects silence and generates an FFmpeg filter
to remove gaps while keeping 80ms of air on either side
for natural breathing room.

Usage:
    python scripts/trim_silence.py clips/<name>/clip_01.mp4
    python scripts/trim_silence.py clips/<name>/  (all clips in dir)

Output:
    Overwrites the clip with the trimmed version.
    Original saved as clip_XX.original.mp4 (first time only).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def detect_silence(video_path: str, threshold_db: float = -40, min_duration: float = 0.3) -> list[dict]:
    """Detect silent segments using FFmpeg silencedetect filter."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    silences = []
    current_start = None

    for line in stderr.split("\n"):
        if "silence_start:" in line:
            try:
                current_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif "silence_end:" in line and current_start is not None:
            try:
                parts = line.split("silence_end:")[1].strip().split()
                end = float(parts[0])
                silences.append({"start": current_start, "end": end, "duration": end - current_start})
                current_start = None
            except (ValueError, IndexError):
                pass

    return silences


def get_duration(video_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def build_trim_filter(silences: list[dict], total_duration: float, air_buffer: float = 0.08) -> list[tuple]:
    """Build list of (start, end) segments to KEEP, with air buffer around silences.

    Keeps `air_buffer` seconds of silence on either side of speech
    for natural breathing room (hysteresis).
    """
    if not silences:
        return [(0, total_duration)]

    keep_segments = []
    prev_end = 0

    for silence in silences:
        # Keep from previous silence end to this silence start + buffer
        seg_start = prev_end
        seg_end = silence["start"] + air_buffer

        if seg_end > seg_start + 0.05:  # only keep segments > 50ms
            keep_segments.append((seg_start, seg_end))

        prev_end = silence["end"] - air_buffer

    # Keep from last silence to end of clip
    if prev_end < total_duration:
        keep_segments.append((max(0, prev_end), total_duration))

    return keep_segments


def trim_clip(video_path: str, keep_segments: list[tuple], output_path: str) -> bool:
    """Use FFmpeg to concatenate only the kept segments."""
    if not keep_segments:
        return False

    # Build complex filter for segment selection and concatenation
    filter_parts = []
    for i, (start, end) in enumerate(keep_segments):
        filter_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )

    n = len(keep_segments)
    concat_input = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{concat_input}concat=n={n}:v=1:a=1[outv][outa]")

    filter_complex = "".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def save_keep_segments(video_path: str, keep_segments: list[tuple]) -> None:
    """Save keep_segments alongside the clip so downstream steps can remap timestamps."""
    segments_path = Path(video_path).with_suffix(".keep_segments.json")
    data = [{"start": round(s, 4), "end": round(e, 4)} for s, e in keep_segments]
    with open(segments_path, "w") as f:
        json.dump(data, f, indent=2)


def process_clip(video_path: str, threshold_db: float = -40,
                  min_silence: float = 0.3, air_buffer: float = 0.08) -> dict:
    """Process a single clip: detect silence, trim, save."""
    path = Path(video_path)

    # Save original (first time only)
    original_path = path.with_suffix(".original.mp4")
    if not original_path.exists():
        os.rename(video_path, str(original_path))
        # Copy back so we always have both files
        shutil.copy2(str(original_path), video_path)

    # Always detect silence from the original (idempotent)
    source = str(original_path)
    duration_before = get_duration(source)
    silences = detect_silence(source, threshold_db, min_silence)

    if not silences:
        # No trim needed — remove any stale keep_segments
        segments_path = path.with_suffix(".keep_segments.json")
        if segments_path.exists():
            segments_path.unlink()
        return {"file": str(path), "silences": 0, "trimmed": False, "reason": "no silence detected"}

    keep_segments = build_trim_filter(silences, duration_before, air_buffer)

    # Calculate how much we'd remove
    kept_duration = sum(end - start for start, end in keep_segments)
    removed = duration_before - kept_duration

    # Don't bother if we'd remove less than 0.5s
    if removed < 0.5:
        segments_path = path.with_suffix(".keep_segments.json")
        if segments_path.exists():
            segments_path.unlink()
        return {"file": str(path), "silences": len(silences), "trimmed": False,
                "reason": f"only {removed:.1f}s silence (below threshold)"}

    # Always trim from original into the working file
    success = trim_clip(source, keep_segments, video_path)
    if success:
        save_keep_segments(video_path, keep_segments)
        duration_after = get_duration(video_path)
        return {"file": str(path), "silences": len(silences), "trimmed": True,
                "before": round(duration_before, 1), "after": round(duration_after, 1),
                "removed": round(duration_before - duration_after, 1)}

    # Failed — restore original
    import shutil
    shutil.copy2(str(original_path), video_path)
    return {"file": str(path), "silences": len(silences), "trimmed": False, "reason": "ffmpeg failed"}


def main():
    parser = argparse.ArgumentParser(description="Trim silence from video clips")
    parser.add_argument("path", help="Path to a clip or directory of clips")
    parser.add_argument("--threshold", type=float, default=-40, help="Silence threshold in dB (default: -40)")
    parser.add_argument("--min-silence", type=float, default=0.3, help="Min silence duration in seconds (default: 0.3)")
    parser.add_argument("--air-buffer", type=float, default=0.08, help="Air to keep around speech in seconds (default: 0.08)")
    args = parser.parse_args()

    target = Path(args.path)

    if target.is_file():
        clips = [str(target)]
    elif target.is_dir():
        clips = sorted(str(p) for p in target.glob("clip_*.mp4") if ".original" not in p.name)
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    if not clips:
        print("No clips found.")
        sys.exit(0)

    print(f"Trimming silence from {len(clips)} clips...")
    print(f"  Threshold: {args.threshold}dB, min silence: {args.min_silence}s, air buffer: {args.air_buffer}s")
    print()

    results = []
    for clip in clips:
        name = Path(clip).name
        result = process_clip(clip, args.threshold, args.min_silence, args.air_buffer)
        results.append(result)

        if result["trimmed"]:
            print(f"  {name}: {result['before']}s → {result['after']}s (removed {result['removed']}s)")
        else:
            print(f"  {name}: skipped ({result.get('reason', 'unknown')})")

    trimmed = [r for r in results if r["trimmed"]]
    if trimmed:
        total_removed = sum(r["removed"] for r in trimmed)
        print(f"\n  {len(trimmed)} clips trimmed, {total_removed:.1f}s total silence removed")
    else:
        print("\n  No clips needed trimming.")


if __name__ == "__main__":
    main()
