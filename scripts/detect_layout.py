"""
Step 2: Detect speaker layout and screen share segments.

Samples frames from the video at key moments, sends them to Claude Vision
to determine:
- How many people are visible
- Which side each person is on
- When the layout changes (e.g., screen share)

Usage:
    python scripts/detect_layout.py input/video.mp4 --transcript review/<name>/transcript.json

Output:
    review/<video_name>/layout.json
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic


def sample_frames(video_path: str, timestamps: list[float], output_dir: str) -> list[str]:
    """Extract frames at specific timestamps."""
    frame_paths = []
    for i, ts in enumerate(timestamps):
        frame_path = os.path.join(output_dir, f"frame_{i:03d}_{ts:.1f}s.jpg")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(ts),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            frame_path
        ]
        subprocess.run(cmd, capture_output=True)
        if os.path.exists(frame_path):
            frame_paths.append((ts, frame_path))
    return frame_paths


def get_video_duration(video_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def frame_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def detect_layouts(frame_data: list[tuple], transcript_context: str) -> dict:
    """Send frames to Claude Vision for layout analysis."""
    client = anthropic.Anthropic()

    # Build the content with all frames
    content = []
    content.append({
        "type": "text",
        "text": (
            "I'm building an automated video clip pipeline. These frames are sampled from a "
            "video recording (podcast/interview style, possibly with screen sharing).\n\n"
            "For each frame, tell me:\n"
            "1. Layout type: 'split_screen', 'single_speaker', 'screen_share', 'gallery', or 'other'\n"
            "2. If split_screen: who is on the left vs right (describe them briefly, e.g., 'man with beard', 'woman with glasses')\n"
            "3. If screen_share: is there still a speaker visible (e.g., small webcam overlay)?\n"
            "4. Any notable changes between frames\n\n"
            f"Transcript excerpt for context (first 500 chars):\n{transcript_context[:500]}\n\n"
            "Respond in JSON format:\n"
            "{\n"
            '  "speakers": [\n'
            '    {"id": "speaker_a", "description": "brief description"},\n'
            '    {"id": "speaker_b", "description": "brief description"}\n'
            "  ],\n"
            '  "segments": [\n'
            "    {\n"
            '      "from_seconds": 0,\n'
            '      "to_seconds": 120,\n'
            '      "layout": "split_screen",\n'
            '      "speaker_positions": {"left": "speaker_a", "right": "speaker_b"}\n'
            "    }\n"
            "  ]\n"
            "}"
        )
    })

    for ts, path in frame_data:
        content.append({
            "type": "text",
            "text": f"\n--- Frame at {ts:.1f}s ---"
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": frame_to_base64(path)
            }
        })

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}]
    )

    # Extract JSON from response
    response_text = response.content[0].text
    # Try to parse JSON from the response
    try:
        # Handle case where response has markdown code blocks
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text
        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        print(f"Warning: Could not parse layout detection response. Raw output saved.", file=sys.stderr)
        return {"raw_response": response_text, "speakers": [], "segments": []}


def main():
    parser = argparse.ArgumentParser(description="Detect speaker layout in video")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--transcript", help="Path to transcript.json")
    parser.add_argument("--num-samples", type=int, default=8, help="Number of frames to sample")
    parser.add_argument("--output-dir", help="Output directory")
    args = parser.parse_args()

    video_path = os.path.abspath(args.video)
    video_name = Path(video_path).stem
    root = Path(__file__).parent.parent

    output_dir = args.output_dir or str(root / "review" / video_name)
    os.makedirs(output_dir, exist_ok=True)

    duration = get_video_duration(video_path)

    # Load transcript for context
    transcript_text = ""
    if args.transcript and os.path.exists(args.transcript):
        with open(args.transcript) as f:
            data = json.load(f)
            transcript_text = data.get("text", "")

    # Sample frames evenly across the video, avoiding the very start/end
    margin = min(10, duration * 0.05)
    sample_points = [
        margin + (duration - 2 * margin) * i / (args.num_samples - 1)
        for i in range(args.num_samples)
    ]

    print(f"Sampling {args.num_samples} frames across {duration:.0f}s video...")

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_data = sample_frames(video_path, sample_points, tmpdir)
        print(f"  Extracted {len(frame_data)} frames")

        print("Analyzing layout with Claude Vision...")
        layout = detect_layouts(frame_data, transcript_text)

    # Save
    output_path = os.path.join(output_dir, "layout.json")
    with open(output_path, "w") as f:
        json.dump(layout, f, indent=2)

    print(f"Layout saved: {output_path}")

    speakers = layout.get("speakers", [])
    segments = layout.get("segments", [])
    print(f"  {len(speakers)} speakers detected, {len(segments)} layout segments")

    return output_path


if __name__ == "__main__":
    main()
