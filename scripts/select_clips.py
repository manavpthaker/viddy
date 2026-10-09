"""
Step 3: Select the best clip-worthy moments from the transcript.

For short videos (<10 min): sends full transcript to Claude.
For long videos (10+ min): windows the transcript into chunks,
picks candidates per window, then ranks globally.

Usage:
    python scripts/select_clips.py review/<name>/transcript.json --layout review/<name>/layout.json
    python scripts/select_clips.py review/<name>/transcript.json --context config/episode.json

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


# ── System prompt: teaches Claude what "Diary of a CEO style" means ──

SYSTEM_PROMPT = """You are an expert short-form video editor creating vertical social clips in the style of "Diary of a CEO".

You ONLY output valid JSON matching the schema described below. No markdown, no explanations, no commentary outside the JSON.

**Visual style:**
Clean, high-end, minimal. Large legible subtitles. No emojis, no TikTok meme energy. Documentary feel.

**Editing rules:**
- Clips are 30-90 seconds, centered on ONE clear emotional or tactical insight.
- Start with a line that hooks curiosity or emotion. The first sentence should make someone stop scrolling.
- The clip must be completely self-contained. A viewer with zero context should understand it.
- Do NOT cut mid-word or mid-sentence. Prefer cuts at natural pauses.
- Use existing transcript wording only. Do NOT invent new lines.

**Captioning rules:**
- Emphasize 2-4 key words/phrases per clip (the "punch" words viewers would screenshot).
- Caption emphasis should land on the insight, the data point, or the emotional peak.

**Selection priorities (in order):**
1. A story with clear setup and punchline/payoff
2. A vulnerable or honest moment (admission, regret, surprise)
3. A contrarian take that challenges assumptions
4. A quotable line with a specific data point
5. An emotional peak (conviction, frustration, realization)

**What to NEVER select:**
- Segments that reference "what I said earlier" or "as we discussed"
- Rambling without a clear payoff
- Inside jokes, name-drops that mean nothing to outsiders
- Pure tactical advice without an emotional or personal anchor
- Segments that start mid-thought with "and" or "but" referencing prior context"""


# ── Few-shot example ──

FEW_SHOT_EXAMPLE = """
**Example input (transcript window):**
[02:12.50] So I had asked for a informational interview and the guy didn't get back to me for almost a week.
  [PAUSE 0.8s @ 137.20]
[02:18.30] So I was like, oh my God, I gotta find him on LinkedIn and use the 300 character note on the request.
  [PAUSE 0.5s @ 143.80]
[02:24.50] He got back to me the same day when I did that.
  [PAUSE 0.7s @ 148.10]
[02:29.00] He's a burnt out manager. He's just not looking at email.

**Example output:**
{
  "clips": [
    {
      "rank": 1,
      "start_seconds": 132.5,
      "end_seconds": 153.0,
      "hook": "He ignored my email for a week. LinkedIn got a same-day response.",
      "why": "Clear before/after contrast that demonstrates a specific, actionable strategy",
      "highlight_words": ["almost a week", "same day", "burnt out manager", "not looking at email"],
      "speaker_timeline": [
        {"from": 132.5, "to": 153.0, "speaker": "speaker_a", "position": "left"}
      ],
      "zoom_moments": [
        {"at_seconds": 144.0, "target": "speaker_a", "hold_seconds": 5}
      ],
      "suggested_title": "Why LinkedIn beats email for reaching hiring managers",
      "mood": "tactical",
      "formats": ["vertical", "square"]
    }
  ]
}
"""


# ── Per-window prompt ──

WINDOW_PROMPT = """You are analyzing a section of a podcast/interview transcript to find the strongest short-form clip candidates.

{context_block}

**Layout info (speaker positions):**
{layout_info}

**Instructions:**
Find the {clips_per_window} strongest clip candidates in this transcript window ({min_dur}-{max_dur} seconds each, target ~{target_dur}s).

**CRITICAL — Clip boundary rules:**
- Start timestamps MUST align with the beginning of a sentence or a [PAUSE] marker.
- End timestamps MUST align with the end of a completed sentence or thought. NEVER cut mid-sentence.
- Each clip must begin with a complete sentence and end with a complete sentence.
- The first words should work as a cold open. The last words should feel like a conclusion or punchline.

**For each clip, provide:**
- start_seconds, end_seconds (at sentence/pause boundaries)
- hook (text overlay for the first 3 seconds that makes people stop scrolling)
- why (1 sentence on why this clip works)
- highlight_words (2-4 key words/phrases for caption emphasis)
- speaker_timeline (who is speaking and their position, covering the ENTIRE clip)
- zoom_moments (timestamps for tighter crop during emphasis)
- suggested_title
- mood: one of "introspective", "tactical", "emotional", "provocative", "storytelling"

**Respond with ONLY a JSON object:**
{{
  "clips": [
    {{
      "rank": 1,
      "start_seconds": 0,
      "end_seconds": 0,
      "hook": "",
      "why": "",
      "highlight_words": [],
      "speaker_timeline": [
        {{"from": 0, "to": 0, "speaker": "speaker_a", "position": "left"}}
      ],
      "zoom_moments": [
        {{"at_seconds": 0, "target": "speaker_a", "hold_seconds": 5}}
      ],
      "suggested_title": "",
      "mood": "introspective",
      "formats": ["vertical", "square"]
    }}
  ]
}}

**Transcript window ({window_label}):**
{transcript}"""


# ── Virality rubric ──
# Each candidate is scored 0-10 per dimension; Python computes the weighted
# 0-100 total (we never trust the model's arithmetic). Tune weights here.

RUBRIC = [
    {"key": "hook", "label": "Hook", "weight": 2.0,
     "desc": "Does the FIRST line stop the scroll? Curiosity gap, bold claim, pattern interrupt, or emotional jolt in the opening seconds."},
    {"key": "emotion", "label": "Emotional charge", "weight": 1.5,
     "desc": "Vulnerability, conviction, tension, surprise, or raw honesty. Flat/neutral delivery scores low."},
    {"key": "self_contained", "label": "Self-contained", "weight": 1.5,
     "desc": "Understandable cold with ZERO context. References to 'what I said earlier' or unexplained names score near 0."},
    {"key": "payoff", "label": "Payoff / arc", "weight": 1.5,
     "desc": "A setup that resolves into a punchline or realization INSIDE the clip. Rambling with no landing scores low."},
    {"key": "quotability", "label": "Quotability", "weight": 1.5,
     "desc": "Is there one sentence someone would screenshot, repost, or put in a comment?"},
    {"key": "specificity", "label": "Specificity", "weight": 1.0,
     "desc": "Concrete numbers, names, vivid detail, a real story — vs vague generic advice."},
    {"key": "contrarian", "label": "Contrarian", "weight": 1.0,
     "desc": "Challenges conventional wisdom or says the quiet part out loud. Drives COMMENTS/debate."},
    {"key": "practical", "label": "Practical value", "weight": 1.0,
     "desc": "A takeaway the viewer can act on. Drives SAVES."},
    {"key": "relatability", "label": "Relatability", "weight": 1.0,
     "desc": "'This is so me' / identity or tribe signal. Drives SHARES."},
]

MAX_WEIGHTED = sum(d["weight"] for d in RUBRIC) * 10  # 120 with defaults

ENGAGEMENT_DRIVERS = ["share", "save", "comment", "watch_through"]


def _rubric_for_prompt() -> str:
    return "\n".join(
        f"- {d['key']} (weight {d['weight']}): {d['label']} — {d['desc']}"
        for d in RUBRIC
    )


SCORING_SYSTEM = """You are a short-form virality analyst. You grade clip candidates against a fixed rubric with cold, calibrated scores. You do NOT inflate — a 10 is rare and means best-in-class. Most real clips land 4-7 on most dimensions.

You ONLY output valid JSON. No markdown, no commentary outside the JSON."""


SCORING_PROMPT = """Score each clip candidate against this virality rubric. Each dimension is 0-10.

**Rubric:**
{rubric}

**Scoring discipline:**
- Be calibrated, not generous. Reserve 9-10 for genuinely exceptional. A forgettable-but-fine clip is ~5.
- Judge from the actual transcript excerpt, not just the hook line.
- predicted_driver: which ONE of {drivers} this clip is most likely to drive.
- disqualifiers: list any fatal flaws (starts mid-thought, needs prior context, no payoff, inside-baseball). Empty list if none.

{context_block}

**Candidates:**
{candidates_json}

Return ONLY this JSON:
{{
  "scores": [
    {{
      "id": 0,
      "subscores": {{ {subscore_keys} }},
      "predicted_driver": "share",
      "rationale": "one sentence on why it will or won't perform",
      "disqualifiers": []
    }}
  ]
}}"""


# ── Global ranking prompt (legacy fallback if scoring is unavailable) ──

RANKING_PROMPT = """You have {total_candidates} clip candidates from different sections of a podcast. Rank them and select the top {max_clips}.

**Selection criteria (in order):**
1. Emotional resonance and self-containment (can a stranger understand this with zero context?)
2. Hook strength (would this first line stop a scroll?)
3. Story completeness (setup → payoff arc)
4. Quotability (would someone screenshot this?)
5. Diversity (don't pick 3 clips from the same 2-minute stretch)

{context_block}

**All candidates:**
{candidates_json}

Return ONLY a JSON object with the top {max_clips} clips, re-ranked 1 to {max_clips}:
{{"clips": [...]}}"""


def format_transcript_for_prompt(data: dict, start_time: float = 0, end_time: float = None) -> str:
    """Format transcript with timestamps and pause markers.

    If start_time/end_time are provided, only includes words in that range.
    """
    words = data.get("words", [])
    if not words:
        lines = []
        for seg in data.get("segments", []):
            if end_time and seg["start"] > end_time:
                break
            if seg["start"] < start_time:
                continue
            start = seg["start"]
            minutes = int(start // 60)
            seconds = start % 60
            lines.append(f"[{minutes:02d}:{seconds:05.2f}] {seg['text'].strip()}")
        return "\n".join(lines)

    # Filter words to range
    if end_time:
        words = [w for w in words if w["start"] >= start_time and w["end"] <= end_time]
    else:
        words = [w for w in words if w["start"] >= start_time]

    lines = []
    current_line_words = []
    current_line_start = None
    pause_threshold = 0.3

    for i, w in enumerate(words):
        if current_line_start is None:
            current_line_start = w["start"]

        current_line_words.append(w["word"])

        if i < len(words) - 1:
            gap = words[i + 1]["start"] - w["end"]
            if gap >= pause_threshold:
                minutes = int(current_line_start // 60)
                seconds = current_line_start % 60
                line_text = " ".join(current_line_words)
                lines.append(f"[{minutes:02d}:{seconds:05.2f}] {line_text}")
                if gap >= 0.5:
                    lines.append(f"  [PAUSE {gap:.1f}s @ {w['end']:.2f}]")
                current_line_words = []
                current_line_start = None

    if current_line_words and current_line_start is not None:
        minutes = int(current_line_start // 60)
        seconds = current_line_start % 60
        line_text = " ".join(current_line_words)
        lines.append(f"[{minutes:02d}:{seconds:05.2f}] {line_text}")

    return "\n".join(lines)


def build_context_block(episode_context: dict) -> str:
    """Build the episode context block for the prompt."""
    if not episode_context:
        return ""

    parts = []
    if episode_context.get("show_name"):
        parts.append(f"**Show:** {episode_context['show_name']}")
    if episode_context.get("host_name"):
        parts.append(f"**Host:** {episode_context['host_name']}")
    if episode_context.get("guest_name"):
        guest = episode_context["guest_name"]
        bio = episode_context.get("guest_bio", "")
        parts.append(f"**Guest:** {guest}" + (f" — {bio}" if bio else ""))
    if episode_context.get("episode_topic"):
        parts.append(f"**Topic:** {episode_context['episode_topic']}")
    if episode_context.get("platform"):
        parts.append(f"**Platform:** {episode_context['platform']}")
    if episode_context.get("audience"):
        parts.append(f"**Audience:** {episode_context['audience']}")
    if episode_context.get("tone"):
        parts.append(f"**Tone:** {episode_context['tone']}")

    themes = episode_context.get("themes_that_perform", [])
    if themes:
        parts.append(f"**Themes that perform well:** {', '.join(themes)}")

    avoid = episode_context.get("themes_to_avoid", [])
    if avoid:
        parts.append(f"**Avoid:** {', '.join(avoid)}")

    if episode_context.get("notes"):
        parts.append(f"**Notes:** {episode_context['notes']}")

    return "\n".join(parts) if parts else ""


def load_config() -> dict:
    root = Path(__file__).parent.parent
    with open(root / "config" / "default.json") as f:
        return json.load(f)


def chunk_transcript(transcript_data: dict, window_minutes: float = 5.0) -> list[tuple]:
    """Split transcript into overlapping windows for long videos.

    Returns list of (start_time, end_time, label) tuples.
    Windows overlap by 30 seconds to avoid missing clips at boundaries.
    """
    duration = transcript_data.get("metadata", {}).get("duration_seconds", 0)
    if duration == 0:
        words = transcript_data.get("words", [])
        if words:
            duration = words[-1]["end"]

    window_size = window_minutes * 60
    overlap = 30  # seconds

    windows = []
    start = 0
    window_num = 1
    while start < duration:
        end = min(start + window_size, duration)
        label = f"Window {window_num}: {int(start//60)}:{int(start%60):02d} - {int(end//60)}:{int(end%60):02d}"
        windows.append((start, end, label))
        start += window_size - overlap
        window_num += 1

    return windows


def select_clips_single(transcript_data: dict, layout_data: dict, config: dict,
                         episode_context: dict = None) -> dict:
    """Select clips from a short video (< 10 min) in a single pass."""
    client = anthropic.Anthropic()
    clip_config = config["clip_selection"]

    transcript_text = format_transcript_for_prompt(transcript_data)
    layout_info = json.dumps(layout_data, indent=2) if layout_data else "No layout info available."
    context_block = build_context_block(episode_context)

    prompt = WINDOW_PROMPT.format(
        context_block=context_block,
        layout_info=layout_info,
        clips_per_window=clip_config["max_clips"],
        min_dur=clip_config["min_duration_seconds"],
        max_dur=clip_config["max_duration_seconds"],
        target_dur=clip_config["target_duration_seconds"],
        window_label="full transcript",
        transcript=transcript_text
    )

    response = client.messages.create(
        model=clip_config["model"],
        max_tokens=4000,
        system=SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLE,
        messages=[{"role": "user", "content": prompt}]
    )

    return parse_claude_json(response.content[0].text)


def select_clips_windowed(transcript_data: dict, layout_data: dict, config: dict,
                           episode_context: dict = None) -> dict:
    """Select clips from a long video using windowed approach.

    1. Split transcript into ~5 min windows with 30s overlap
    2. Pick 2-3 candidates per window
    3. Rank all candidates globally, keep top N
    """
    client = anthropic.Anthropic()
    clip_config = config["clip_selection"]

    layout_info = json.dumps(layout_data, indent=2) if layout_data else "No layout info available."
    context_block = build_context_block(episode_context)

    windows = chunk_transcript(transcript_data)
    print(f"  Splitting into {len(windows)} windows (~5 min each, 30s overlap)")

    all_candidates = []

    for start_time, end_time, label in windows:
        transcript_text = format_transcript_for_prompt(transcript_data, start_time, end_time)

        if not transcript_text.strip():
            continue

        # Ask for 2-3 clips per window
        clips_per_window = min(3, clip_config["max_clips"])

        prompt = WINDOW_PROMPT.format(
            context_block=context_block,
            layout_info=layout_info,
            clips_per_window=clips_per_window,
            min_dur=clip_config["min_duration_seconds"],
            max_dur=clip_config["max_duration_seconds"],
            target_dur=clip_config["target_duration_seconds"],
            window_label=label,
            transcript=transcript_text
        )

        print(f"    {label}...")

        response = client.messages.create(
            model=clip_config["model"],
            max_tokens=3000,
            system=SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLE,
            messages=[{"role": "user", "content": prompt}]
        )

        result = parse_claude_json(response.content[0].text)
        window_clips = result.get("clips", [])
        print(f"      {len(window_clips)} candidates found")

        # Tag each candidate with its source window
        for clip in window_clips:
            clip["_source_window"] = label

        all_candidates.extend(window_clips)

    print(f"  Total candidates: {len(all_candidates)}")

    if len(all_candidates) <= clip_config["max_clips"]:
        # Few enough candidates, no need to re-rank
        for i, clip in enumerate(all_candidates, 1):
            clip["rank"] = i
            clip.pop("_source_window", None)
        return {"clips": all_candidates}

    # Global ranking pass
    print(f"  Ranking top {clip_config['max_clips']} from {len(all_candidates)} candidates...")

    # Strip source window tags for the ranking prompt
    candidates_for_ranking = []
    for c in all_candidates:
        clean = {k: v for k, v in c.items() if not k.startswith("_")}
        candidates_for_ranking.append(clean)

    ranking_prompt = RANKING_PROMPT.format(
        total_candidates=len(candidates_for_ranking),
        max_clips=clip_config["max_clips"],
        context_block=context_block,
        candidates_json=json.dumps(candidates_for_ranking, indent=2)
    )

    response = client.messages.create(
        model=clip_config["model"],
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": ranking_prompt}]
    )

    return parse_claude_json(response.content[0].text)


def parse_claude_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    try:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0]
        else:
            json_str = text
        result = json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        print(f"Warning: Could not parse Claude response. Raw output saved.", file=sys.stderr)
        result = {"raw_response": text, "clips": []}

    # Validate and add approval field
    for clip in result.get("clips", []):
        clip["approved"] = True

        # Validate required fields exist
        required = ["start_seconds", "end_seconds", "hook", "suggested_title"]
        for field in required:
            if field not in clip:
                print(f"  Warning: clip missing '{field}', may cause issues", file=sys.stderr)

        # Validate timestamps are sane
        start = clip.get("start_seconds", 0)
        end = clip.get("end_seconds", 0)
        if end <= start:
            print(f"  Warning: clip has end ({end}) <= start ({start})", file=sys.stderr)
        elif end - start > 120:
            print(f"  Warning: clip is {end-start:.0f}s (>120s), may be too long", file=sys.stderr)

    return result


def get_excerpt(transcript_data: dict, start: float, end: float, max_chars: int = 900) -> str:
    """Plain-text transcript between start and end, for scoring."""
    words = transcript_data.get("words", [])
    if words:
        text = " ".join(
            w["word"] for w in words
            if w["start"] >= start - 0.5 and w["end"] <= end + 0.5
        )
    else:
        text = " ".join(
            seg["text"].strip() for seg in transcript_data.get("segments", [])
            if seg["end"] >= start and seg["start"] <= end
        )
    text = " ".join(text.split())
    return text[:max_chars]


def compute_weighted_score(subscores: dict) -> int:
    """Weighted 0-100 from per-dimension 0-10 subscores (computed in Python)."""
    total = 0.0
    for d in RUBRIC:
        v = subscores.get(d["key"], 0)
        try:
            v = max(0.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            v = 0.0
        total += v * d["weight"]
    return round(total / MAX_WEIGHTED * 100)


def score_clips(candidates: list[dict], transcript_data: dict, config: dict,
                episode_context: dict = None) -> list[dict]:
    """Score every candidate against the rubric and return them ranked by score.

    Advisory by default (nothing dropped). If config.clip_selection.min_score is
    set, candidates below it are marked approved=false (kept, not removed).
    On any failure, returns candidates unchanged so the pipeline still works.
    """
    if not candidates:
        return candidates

    clip_config = config["clip_selection"]
    min_score = clip_config.get("min_score")  # None = advisory

    # Build a compact, id-tagged payload for the scorer.
    payload = []
    for i, c in enumerate(candidates):
        start = c.get("start_seconds", 0)
        end = c.get("end_seconds", 0)
        payload.append({
            "id": i,
            "hook": c.get("hook", ""),
            "suggested_title": c.get("suggested_title", ""),
            "excerpt": get_excerpt(transcript_data, start, end),
        })

    subscore_keys = ", ".join(f'"{d["key"]}": 0' for d in RUBRIC)
    prompt = SCORING_PROMPT.format(
        rubric=_rubric_for_prompt(),
        drivers=", ".join(ENGAGEMENT_DRIVERS),
        context_block=build_context_block(episode_context),
        candidates_json=json.dumps(payload, indent=2),
        subscore_keys=subscore_keys,
    )

    print(f"  Scoring {len(candidates)} candidates against the virality rubric...")
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=clip_config["model"],
            max_tokens=4000,
            system=SCORING_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        result = parse_claude_json(response.content[0].text)
        scores_by_id = {s["id"]: s for s in result.get("scores", []) if "id" in s}
    except Exception as e:
        print(f"  Warning: scoring failed ({e}); keeping unscored order.", file=sys.stderr)
        return candidates

    for i, c in enumerate(candidates):
        s = scores_by_id.get(i)
        if not s:
            c["virality"] = {"score": 0, "subscores": {}, "predicted_driver": None,
                             "rationale": "not scored", "disqualifiers": []}
            continue
        subscores = s.get("subscores", {})
        score = compute_weighted_score(subscores)
        c["virality"] = {
            "score": score,
            "subscores": subscores,
            "predicted_driver": s.get("predicted_driver"),
            "rationale": s.get("rationale", ""),
            "disqualifiers": s.get("disqualifiers", []),
        }

    # Rank by score (advisory — keep everything, sorted strongest-first).
    candidates.sort(key=lambda c: c.get("virality", {}).get("score", 0), reverse=True)
    for rank, c in enumerate(candidates, 1):
        c["rank"] = rank
        score = c.get("virality", {}).get("score", 0)
        if min_score is not None and score < min_score:
            c["approved"] = False

    top = candidates[0]["virality"]["score"] if candidates else 0
    print(f"  Scored. Top clip: {top}/100" +
          (f" (gate: <{min_score} marked not-approved)" if min_score is not None else " (advisory)"))
    return candidates


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

        mood = clip.get("mood", "")
        mood_str = f" [{mood}]" if mood else ""

        vir = clip.get("virality", {})
        score = vir.get("score")
        score_str = f" — 🔥 {score}/100" if score is not None else ""

        lines.append(f"## Clip {rank}: {clip.get('suggested_title', 'Untitled')}{mood_str}{score_str}")
        lines.append("")
        lines.append(f"**Time:** {start_min}:{start_sec:05.2f} - {end_min}:{end_sec:05.2f} ({duration:.0f}s)")
        lines.append(f"**Hook:** {clip.get('hook', '')}")
        lines.append(f"**Why:** {clip.get('why', '')}")

        # Virality scorecard
        if vir and vir.get("subscores"):
            driver = vir.get("predicted_driver")
            if driver:
                lines.append(f"**Predicted driver:** {driver.replace('_', '-')}")
            if vir.get("rationale"):
                lines.append(f"**Read:** {vir['rationale']}")
            sub = vir["subscores"]
            cells = []
            for d in RUBRIC:
                v = sub.get(d["key"])
                if v is not None:
                    cells.append(f"{d['label']} {v}/10")
            if cells:
                lines.append(f"**Scorecard:** {' · '.join(cells)}")
            dq = vir.get("disqualifiers") or []
            if dq:
                lines.append(f"**⚠️ Disqualifiers:** {', '.join(dq)}")

        # Speaker info
        speaker_tl = clip.get("speaker_timeline", [])
        if speaker_tl:
            speakers = set(s.get("speaker", "?") for s in speaker_tl)
            lines.append(f"**Speakers:** {', '.join(speakers)}")

        lines.append(f"**Highlight words:** {', '.join(clip.get('highlight_words', []))}")
        lines.append(f"**Approved:** {'yes' if clip.get('approved') else 'NO'}")
        lines.append("")

        # Pull transcript excerpt
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
    parser.add_argument("--context", help="Path to episode context JSON (config/episode.json)")
    parser.add_argument("--output-dir", help="Output directory")
    args = parser.parse_args()

    with open(args.transcript) as f:
        transcript_data = json.load(f)

    layout_data = {}
    if args.layout and os.path.exists(args.layout):
        with open(args.layout) as f:
            layout_data = json.load(f)

    # Load episode context
    episode_context = {}
    if args.context and os.path.exists(args.context):
        with open(args.context) as f:
            episode_context = json.load(f)
    else:
        # Try default location
        root = Path(__file__).parent.parent
        default_ctx = root / "config" / "episode.json"
        if default_ctx.exists():
            with open(default_ctx) as f:
                episode_context = json.load(f)

    config = load_config()

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = str(Path(args.transcript).parent)
    os.makedirs(output_dir, exist_ok=True)

    # Decide: single pass or windowed
    duration = transcript_data.get("metadata", {}).get("duration_seconds", 0)
    if duration == 0:
        words = transcript_data.get("words", [])
        if words:
            duration = words[-1]["end"]

    print(f"Selecting clips with Claude...")
    print(f"  Video duration: {duration:.0f}s ({duration/60:.1f} min)")

    if duration > 600:  # > 10 minutes
        clips_data = select_clips_windowed(transcript_data, layout_data, config, episode_context)
    else:
        clips_data = select_clips_single(transcript_data, layout_data, config, episode_context)

    # Score every candidate against the virality rubric and rank by score.
    scored = score_clips(clips_data.get("clips", []), transcript_data, config, episode_context)
    clips_data = {"clips": scored}

    num_clips = len(clips_data.get("clips", []))
    print(f"  {num_clips} clips selected")

    clips_path = os.path.join(output_dir, "clips.json")
    with open(clips_path, "w") as f:
        json.dump(clips_data, f, indent=2)
    print(f"Clips saved: {clips_path}")

    review_md = generate_review_md(clips_data, transcript_data)
    review_path = os.path.join(output_dir, "review.md")
    with open(review_path, "w") as f:
        f.write(review_md)
    print(f"Review file: {review_path}")

    print(f"\nReview the clips in {review_path}")
    print(f"Edit {clips_path} to approve/reject, then run: python pipeline.py <video> --render")


if __name__ == "__main__":
    main()
