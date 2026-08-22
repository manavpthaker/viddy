#!/usr/bin/env python3
"""
Process video clips through NVIDIA Maxine Eye Contact via NVCF cloud.

Usage:
  python scripts/eye_contact.py <input.mp4> <output.mp4>
  python scripts/eye_contact.py --batch clips/productize-me-apr17/

Requires NGC_API_KEY environment variable.
"""

import os
import sys
import time
import glob
import argparse
from typing import Iterator

import grpc
from tqdm import tqdm

# Add the nim-clients paths
NIM_CLIENTS = "/tmp/nim-clients"
sys.path.append(os.path.join(NIM_CLIENTS, "eye-contact/interfaces"))
sys.path.append(os.path.join(NIM_CLIENTS, "eye-contact/scripts"))
sys.path.append(os.path.join(NIM_CLIENTS, "utils"))

import eyecontact_pb2
import eyecontact_pb2_grpc

# NVCF cloud config
NVCF_TARGET = "grpc.nvcf.nvidia.com:443"
FUNCTION_ID = "15c6f1a0-3843-4cde-b5bc-803a4966fbb6"
CHUNK_SIZE = 64 * 1024  # 64KB


def make_config():
    """Create default eye contact config."""
    return {
        "temporal": 0xFFFFFFFF,
        "detect_closure": 0,
        "eye_size_sensitivity": 3,
        "enable_lookaway": 1,          # Natural look-away to avoid staring
        "lookaway_max_offset": 3,      # Subtle offset
        "lookaway_interval_min": 90,   # ~3s at 30fps
        "lookaway_interval_range": 60, # ~2s range
        "gaze_pitch_threshold_low": 20.0,
        "gaze_pitch_threshold_high": 30.0,
        "gaze_yaw_threshold_low": 20.0,
        "gaze_yaw_threshold_high": 30.0,
        "head_pitch_threshold_low": 15.0,
        "head_pitch_threshold_high": 25.0,
        "head_yaw_threshold_low": 25.0,
        "head_yaw_threshold_high": 30.0,
        "output_video_encoding": eyecontact_pb2.OutputVideoEncoding(
            lossy=eyecontact_pb2.LossyEncoding(
                bitrate=20000000,
                idr_interval=8,
            )
        ),
    }


def generate_requests(input_path, config_params):
    """Stream config + video chunks to the service."""
    # Send config first
    yield eyecontact_pb2.RedirectGazeRequest(
        config=eyecontact_pb2.RedirectGazeConfig(**config_params)
    )

    # Stream video data
    file_size = os.path.getsize(input_path)
    with open(input_path, "rb") as f:
        with tqdm(total=file_size, unit="B", unit_scale=True, desc="  Uploading", leave=False) as pbar:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                pbar.update(len(chunk))
                yield eyecontact_pb2.RedirectGazeRequest(video_file_data=chunk)


def process_video(input_path, output_path, api_key):
    """Process a single video through NVCF Eye Contact."""
    print(f"\n{'='*50}")
    print(f"  Eye Contact: {os.path.basename(input_path)}")
    print(f"{'='*50}")

    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    print(f"  Input: {input_path} ({file_size_mb:.1f} MB)")
    print(f"  Output: {output_path}")

    # Metadata for NVCF auth
    metadata = (
        ("authorization", f"Bearer {api_key}"),
        ("function-id", FUNCTION_ID),
    )

    config = make_config()

    start = time.time()

    # Connect via secure gRPC to NVCF
    channel = grpc.secure_channel(NVCF_TARGET, grpc.ssl_channel_credentials())
    try:
        stub = eyecontact_pb2_grpc.MaxineEyeContactServiceStub(channel)

        responses = stub.RedirectGaze(
            generate_requests(input_path, config),
            metadata=metadata,
        )

        # Skip config echo
        next(responses)

        # Write output
        chunk_count = 0
        total_bytes = 0
        with open(output_path, "wb") as f:
            pbar = tqdm(desc="  Receiving", unit="chunks", leave=False,
                       bar_format="{desc}: {n} chunks | {postfix}")
            for response in responses:
                if response.HasField("video_file_data"):
                    data = response.video_file_data
                    f.write(data)
                    chunk_count += 1
                    total_bytes += len(data)
                    pbar.update(1)
                    pbar.set_postfix_str(f"{total_bytes / (1024*1024):.1f} MB")
            pbar.close()

        elapsed = time.time() - start
        print(f"  Done in {elapsed:.1f}s ({total_bytes / (1024*1024):.1f} MB output)")
        return True

    except grpc.RpcError as e:
        print(f"  FAILED: {e.code()} - {e.details()}")
        return False
    finally:
        channel.close()


def main():
    parser = argparse.ArgumentParser(description="NVIDIA Maxine Eye Contact via NVCF cloud")
    parser.add_argument("input", help="Input MP4 file or directory for batch mode")
    parser.add_argument("output", nargs="?", help="Output MP4 file (auto-generated for batch)")
    parser.add_argument("--batch", action="store_true", help="Process all clip_*.mp4 in directory")
    args = parser.parse_args()

    api_key = os.environ.get("NGC_API_KEY")
    if not api_key:
        print("Error: Set NGC_API_KEY environment variable")
        print("  export NGC_API_KEY=nvapi-...")
        sys.exit(1)

    if args.batch or os.path.isdir(args.input):
        # Batch mode: process all clip_*.mp4 files
        clip_dir = args.input
        clips = sorted(glob.glob(os.path.join(clip_dir, "clip_*.mp4")))
        # Skip .original.mp4 files
        clips = [c for c in clips if ".original." not in c]

        if not clips:
            print(f"No clip_*.mp4 files found in {clip_dir}")
            sys.exit(1)

        print(f"\nBatch processing {len(clips)} clips from {clip_dir}")
        results = []
        for clip in clips:
            name = os.path.basename(clip)
            out = clip.replace(".mp4", ".eyecontact.mp4")
            ok = process_video(clip, out, api_key)
            results.append((name, ok))

        print(f"\n{'='*50}")
        print(f"  Results: {sum(1 for _, ok in results if ok)}/{len(results)} succeeded")
        for name, ok in results:
            print(f"  {'OK' if ok else 'FAIL'}: {name}")
        print(f"{'='*50}")
    else:
        # Single file mode
        output = args.output or args.input.replace(".mp4", ".eyecontact.mp4")
        ok = process_video(args.input, output, api_key)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
