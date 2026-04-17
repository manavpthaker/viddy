#!/usr/bin/env python3
"""
Viddy — Automated video clip pipeline.

Takes a raw video recording and produces polished short-form clips
with animated captions, speaker zoom, and branding.

Usage:
    # Full pipeline (stops for review after clip selection)
    python pipeline.py input/video.mp4

    # Render after reviewing clips
    python pipeline.py input/video.mp4 --render

    # Skip layout detection (faster, no zoom effects)
    python pipeline.py input/video.mp4 --skip-layout

    # Only transcribe
    python pipeline.py input/video.mp4 --step transcribe
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent


def run_step(script: str, args: list[str], step_name: str) -> int:
    """Run a pipeline step as a subprocess."""
    cmd = [sys.executable, str(ROOT / "scripts" / script)] + args
    print(f"\n{'='*60}")
    print(f"  STEP: {step_name}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Viddy — raw video to polished clips",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py input/my-podcast.mp4          # Run brain (transcribe → detect → select)
  python pipeline.py input/my-podcast.mp4 --render  # Render after review
  python pipeline.py input/my-podcast.mp4 --step transcribe  # Only transcribe
        """
    )
    parser.add_argument("video", help="Path to source video file")
    parser.add_argument("--render", action="store_true", help="Run render phase (after review)")
    parser.add_argument("--skip-layout", action="store_true", help="Skip layout detection")
    parser.add_argument("--step", choices=["transcribe", "layout", "select", "cut", "prepare"],
                        help="Run a single step only")
    parser.add_argument("--output-name", help="Override the output folder name")
    args = parser.parse_args()

    video_path = os.path.abspath(args.video)
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    video_name = args.output_name or Path(video_path).stem
    review_dir = str(ROOT / "review" / video_name)
    clips_dir = str(ROOT / "clips" / video_name)

    transcript_path = os.path.join(review_dir, "transcript.json")
    layout_path = os.path.join(review_dir, "layout.json")
    clips_json_path = os.path.join(review_dir, "clips.json")
    manifest_path = os.path.join(clips_dir, "manifest.json")

    # Single step mode
    if args.step:
        if args.step == "transcribe":
            sys.exit(run_step("transcribe.py", [video_path, "--output-dir", review_dir], "Transcribe"))
        elif args.step == "layout":
            step_args = [video_path, "--transcript", transcript_path, "--output-dir", review_dir]
            sys.exit(run_step("detect_layout.py", step_args, "Detect Layout"))
        elif args.step == "select":
            step_args = [transcript_path]
            if os.path.exists(layout_path):
                step_args += ["--layout", layout_path]
            sys.exit(run_step("select_clips.py", step_args, "Select Clips"))
        elif args.step == "cut":
            sys.exit(run_step("cut_clips.py", [video_path, clips_json_path], "Cut Clips"))
        elif args.step == "prepare":
            step_args = [transcript_path, manifest_path]
            if os.path.exists(layout_path):
                step_args += ["--layout", layout_path]
            sys.exit(run_step("prepare_render.py", step_args, "Prepare Render Data"))

    if not args.render:
        # ==========================================
        # PHASE 1: THE BRAIN
        # ==========================================

        print("\n" + "=" * 60)
        print("  VIDDY — Phase 1: The Brain")
        print("=" * 60)

        # Step 1: Transcribe
        rc = run_step("transcribe.py", [video_path, "--output-dir", review_dir], "Transcribe")
        if rc != 0:
            print("Transcription failed.", file=sys.stderr)
            sys.exit(1)

        # Step 2: Layout detection
        if not args.skip_layout:
            step_args = [video_path, "--transcript", transcript_path, "--output-dir", review_dir]
            rc = run_step("detect_layout.py", step_args, "Detect Layout")
            if rc != 0:
                print("Layout detection failed. Continuing without layout data.", file=sys.stderr)
        else:
            print("\nSkipping layout detection (--skip-layout)")

        # Step 3: Clip selection
        step_args = [transcript_path]
        if os.path.exists(layout_path):
            step_args += ["--layout", layout_path]
        step_args += ["--output-dir", review_dir]
        rc = run_step("select_clips.py", step_args, "Select Clips")
        if rc != 0:
            print("Clip selection failed.", file=sys.stderr)
            sys.exit(1)

        # Pause for review
        print("\n" + "=" * 60)
        print("  REVIEW YOUR CLIPS")
        print("=" * 60)
        print(f"\n  Review file:  {review_dir}/review.md")
        print(f"  Clips data:   {review_dir}/clips.json")
        print()
        print("  To approve/reject clips, edit clips.json:")
        print('    Set "approved": false on clips you don\'t want.')
        print()
        print("  When ready, run:")
        print(f"    python pipeline.py {args.video} --render")
        print()

    else:
        # ==========================================
        # PHASE 2: CUT + PREPARE
        # ==========================================

        print("\n" + "=" * 60)
        print("  VIDDY — Phase 2: Cut + Render Prep")
        print("=" * 60)

        if not os.path.exists(clips_json_path):
            print(f"Error: No clips.json found at {clips_json_path}", file=sys.stderr)
            print("Run Phase 1 first: python pipeline.py <video>")
            sys.exit(1)

        # Check for approved clips
        with open(clips_json_path) as f:
            clips_data = json.load(f)
        approved = [c for c in clips_data.get("clips", []) if c.get("approved", True)]
        print(f"\n  {len(approved)} approved clips ready to cut.\n")

        if not approved:
            print("No clips approved. Edit clips.json and try again.")
            sys.exit(1)

        # Step 4: Cut clips
        rc = run_step("cut_clips.py", [video_path, clips_json_path, "--output-dir", clips_dir], "Cut Clips")
        if rc != 0:
            print("Clip cutting failed.", file=sys.stderr)
            sys.exit(1)

        # Step 5: Prepare render data
        step_args = [transcript_path, manifest_path]
        if os.path.exists(layout_path):
            step_args += ["--layout", layout_path]
        step_args += ["--output-dir", os.path.join(clips_dir, "render_data")]
        rc = run_step("prepare_render.py", step_args, "Prepare Render Data")
        if rc != 0:
            print("Render data preparation failed.", file=sys.stderr)
            sys.exit(1)

        # Summary
        print("\n" + "=" * 60)
        print("  DONE")
        print("=" * 60)
        print(f"\n  Cut clips:    {clips_dir}/")
        print(f"  Render data:  {clips_dir}/render_data/")
        print()
        print("  Phase 3 (Remotion rendering) coming soon.")
        print("  For now, cut clips are ready for manual use or Remotion dev.")
        print()


if __name__ == "__main__":
    main()
