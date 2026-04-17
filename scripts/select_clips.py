"""
Step 3: Select the best clip-worthy moments from the transcript.

Sends the full transcript + layout info to Claude, which identifies
the strongest moments for short-form clips.

Usage:
    python scripts/select_clips.py review/<name>/transcript.json --layout review/<name>/layout.json

Output:
    review/<video_name>/clips.json
    review/<video_name>/review.md (human-readable review file)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic


CLIP_SELECTION_PROMPT = """You are an expert video editor who creates viral short-form clips from long-form podcast/interview recordings. Your style reference is "Diary of a CEO" clips — punchy, emotional, insight-dense moments that work as standalone pieces.

You're given a transcript with word-level timestamps and layout information for a recorded conversation.

**Your job:** Identify the {max_clips} strongest moments for short-form clips ({min_dur}-{max_dur} seconds each, target ~{target_dur}s).

**What makes a great clip:**
1. A single complete thought or story that stands alone without context
2. An emotional peak — surprise, realization, conviction, vulnerability
3. A quotable line or data point people would screenshot
4. A contrarian or unexpected take that creates tension
5. A story with a clear setup → punchline/payoff arc

**What makes a bad clip:**
1. References to things said earlier that viewers won't have context for
2. Rambling or unfocused segments
3. Inside jokes or name-drops that mean nothing to outsiders
4. Segments that end mid-thought

**For each clip, provide:**
- Start and end timestamps (use the word-level timestamps for precision)
- A suggested hook (the text overlay that would appear in the first 3 seconds)
- Why this clip works (1 sentence)
- Which words/phrases should be visually highlighted in captions (the "punch" words)
- Speaker focus: who is the primary speaker during this clip (for zoom effect)
- Zoom moments: specific timestamps where the camera should zoom into the primary speaker (moments of emphasis)
- A suggested title/caption for the clip

**Layout info for zoom planning:**
{layout_info}

**Respond in this exact JSON format:**
{{
  "clips": [
    {{
      "rank": 1,
      "start_seconds": 272.5,
      "end_seconds": 348.2,
      "hook": "6,000 people applied. Only 1 was hireable.",
      "why": "Visceral data point with emotional payoff",
      "highlight_words": ["six thousand", "one", "hireable"],
      "primary_speaker": "speaker_a or speaker_b",
      "zoom_moments": [
        {{"at_seconds": 280.0, "target": "speaker_a", "hold_seconds": 6}}
      ],
      "suggested_title": "The hiring funnel is broken",
      "formats": ["vertical", "square"]
    }}
  ]
}}

**Transcript:**
{transcript}
"""


def format_transcript_for_prompt(data: dict) -> str:
    """Format transcript with timestamps for the prompt."""
    lines = []
    for seg in data.get("segments", []):
        start = seg["start"]
        minutes = int(start // 60)
        seconds = start % 60
        lines.append(f"[{minutes:02d}:{seconds:05.2f}] {seg['text'].strip()}")
    return "\n".join(lines)


def load_config() -> dict:
    root = Path(__file__).parent.parent
    config_path = root / "config" / "default.json"
    with open(config_path) as f:
        return json.load(f)


def select_clips(transcript_data: dict, layout_data: dict, config: dict) -> dict:
    """Send transcript to Claude for clip selection."""
    client = anthropic.Anthropic()

    clip_config = config["clip_selection"]
    transcript_text = format_transcript_for_prompt(transcript_data)
    layout_info = json.dumps(layout_data, indent=2) if layout_data else "No layout info available."

    prompt = CLIP_SELECTION_PROMPT.format(
        max_clips=clip_config["max_clips"],
        min_dur=clip_config["min_duration_seconds"],
        max_dur=clip_config["max_duration_seconds"],
        target_dur=clip_config["target_duration_seconds"],
        layout_info=layout_info,
        transcript=transcript_text
    )

    response = client.messages.create(
        model=clip_config["model"],
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text

    try:
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            json_str = response_text
        result = json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        print(f"Warning: Could not parse clip selection. Raw output saved.", file=sys.stderr)
        result = {"raw_response": response_text, "clips": []}

    # Add approval field to each clip
    for clip in result.get("clips", []):
        clip["approved"] = True

    return result


def generate_review_md(clips_data: dict, transcript_data: dict) -> str:
    """Generate a human-readable review file."""
    lines = [
        "# Clip Review",
        "",
        "Review the clips below. Edit `clips.json` to:",
        '- Set `"approved": false` on clips you don\'t want',
        "- Reorder by changing `rank` values",
        "- Adjust start/end timestamps",
        "",
        "Then run: `python pipeline.py <video> --render`",
        "",
        "---",
        ""
    ]

    for clip in clips_data.get("clips", []):
        rank = clip.get("rank", "?")
        start = clip.get("start_seconds", 0)
        end = clip.get("end_seconds", 0)
        duration = end - start

        start_min = int(start // 60)
        start_sec = start % 60
        end_min = int(end // 60)
        end_sec = end % 60

        lines.append(f"## Clip {rank}: {clip.get('suggested_title', 'Untitled')}")
        lines.append("")
        lines.append(f"**Time:** {start_min}:{start_sec:05.2f} - {end_min}:{end_sec:05.2f} ({duration:.0f}s)")
        lines.append(f"**Hook:** {clip.get('hook', '')}")
        lines.append(f"**Why:** {clip.get('why', '')}")
        lines.append(f"**Speaker focus:** {clip.get('primary_speaker', 'unknown')}")
        lines.append(f"**Highlight words:** {', '.join(clip.get('highlight_words', []))}")
        lines.append(f"**Approved:** {'yes' if clip.get('approved') else 'NO'}")
        lines.append("")

        # Pull transcript excerpt for this clip
        excerpt_lines = []
        for seg in transcript_data.get("segments", []):
            if seg["end"] >= start and seg["start"] <= end:
                excerpt_lines.append(f"> {seg['text'].strip()}")
        if excerpt_lines:
            lines.append("**Transcript excerpt:**")
            lines.extend(excerpt_lines)
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Select best clip moments from transcript")
    parser.add_argument("transcript", help="Path to transcript.json")
    parser.add_argument("--layout", help="Path to layout.json")
    parser.add_argument("--output-dir", help="Output directory")
    args = parser.parse_args()

    # Load transcript
    with open(args.transcript) as f:
        transcript_data = json.load(f)

    # Load layout if available
    layout_data = {}
    if args.layout and os.path.exists(args.layout):
        with open(args.layout) as f:
            layout_data = json.load(f)

    # Load config
    config = load_config()

    # Determine output dir
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = str(Path(args.transcript).parent)
    os.makedirs(output_dir, exist_ok=True)

    print("Selecting clips with Claude...")
    clips_data = select_clips(transcript_data, layout_data, config)

    num_clips = len(clips_data.get("clips", []))
    print(f"  {num_clips} clips identified")

    # Save clips.json
    clips_path = os.path.join(output_dir, "clips.json")
    with open(clips_path, "w") as f:
        json.dump(clips_data, f, indent=2)
    print(f"Clips saved: {clips_path}")

    # Generate review.md
    review_md = generate_review_md(clips_data, transcript_data)
    review_path = os.path.join(output_dir, "review.md")
    with open(review_path, "w") as f:
        f.write(review_md)
    print(f"Review file: {review_path}")

    print(f"\nReview the clips in {review_path}")
    print(f"Edit {clips_path} to approve/reject, then run: python pipeline.py <video> --render")


if __name__ == "__main__":
    main()
