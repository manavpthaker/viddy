"""
Step 1: Transcribe video with word-level timestamps.

Uses OpenAI Whisper API to get word-level timestamps.
Extracts audio via FFmpeg first, then sends to API.

Usage:
    python scripts/transcribe.py input/video.mp4

Output:
    review/<video_name>/transcript.json
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from openai import OpenAI


def extract_audio(video_path: str, audio_path: str) -> None:
    """Extract audio from video as WAV for Whisper API."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # WAV format
        "-ar", "16000",           # 16kHz sample rate (Whisper optimal)
        "-ac", "1",               # mono
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def transcribe_openai(audio_path: str) -> dict:
    """Transcribe audio using OpenAI Whisper API with word timestamps."""
    client = OpenAI()

    # Whisper API has a 25MB limit. Split if needed.
    file_size = os.path.getsize(audio_path)
    max_size = 24 * 1024 * 1024  # 24MB to be safe

    if file_size > max_size:
        return transcribe_openai_chunked(audio_path, max_size)

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            language="en"
        )

    return {
        "text": response.text,
        "segments": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text
            }
            for s in (response.segments or [])
        ],
        "words": [
            {
                "word": w.word.strip(),
                "start": w.start,
                "end": w.end
            }
            for w in (response.words or [])
        ]
    }


def transcribe_openai_chunked(audio_path: str, max_size: int) -> dict:
    """Handle files larger than 25MB by splitting audio."""
    client = OpenAI()

    # Get duration for splitting
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = float(json.loads(result.stdout)["format"]["duration"])

    # Calculate chunk duration based on file size ratio
    file_size = os.path.getsize(audio_path)
    num_chunks = (file_size // max_size) + 1
    chunk_duration = duration / num_chunks

    all_segments = []
    all_words = []
    all_text = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(num_chunks):
            start_time = i * chunk_duration
            chunk_path = os.path.join(tmpdir, f"chunk_{i}.wav")

            cmd = [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-ss", str(start_time),
                "-t", str(chunk_duration),
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                chunk_path
            ]
            subprocess.run(cmd, capture_output=True)

            with open(chunk_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"],
                    language="en"
                )

            # Offset timestamps by chunk start
            for s in (response.segments or []):
                all_segments.append({
                    "start": s.start + start_time,
                    "end": s.end + start_time,
                    "text": s.text
                })

            for w in (response.words or []):
                all_words.append({
                    "word": w.word.strip(),
                    "start": w.start + start_time,
                    "end": w.end + start_time
                })

            all_text.append(response.text)

            print(f"  Chunk {i + 1}/{num_chunks} transcribed")

    return {
        "text": " ".join(all_text),
        "segments": all_segments,
        "words": all_words
    }


def main():
    parser = argparse.ArgumentParser(description="Transcribe video with word-level timestamps")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--output-dir", help="Output directory (default: review/<video_name>/)")
    args = parser.parse_args()

    video_path = os.path.abspath(args.video)
    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    video_name = Path(video_path).stem
    root = Path(__file__).parent.parent

    output_dir = args.output_dir or str(root / "review" / video_name)
    os.makedirs(output_dir, exist_ok=True)

    duration = get_video_duration(video_path)
    print(f"Video: {video_path}")
    print(f"Duration: {duration:.1f}s ({duration / 60:.1f} min)")

    # Step 1: Extract audio
    print("Extracting audio...")
    audio_path = os.path.join(output_dir, "audio.wav")
    extract_audio(video_path, audio_path)

    # Step 2: Transcribe
    print("Transcribing (this may take a few minutes)...")
    transcript = transcribe_openai(audio_path)

    # Add metadata
    transcript["metadata"] = {
        "source": video_path,
        "duration_seconds": duration,
        "word_count": len(transcript["words"]),
        "segment_count": len(transcript["segments"])
    }

    # Save
    output_path = os.path.join(output_dir, "transcript.json")
    with open(output_path, "w") as f:
        json.dump(transcript, f, indent=2)

    print(f"Transcript saved: {output_path}")
    print(f"  {transcript['metadata']['word_count']} words, {transcript['metadata']['segment_count']} segments")

    # Clean up audio file (large)
    os.remove(audio_path)
    print("Audio file cleaned up.")

    return output_path


if __name__ == "__main__":
    main()
