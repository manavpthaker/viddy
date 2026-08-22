"""
Step 3b: Fetch B-roll video clips from open-license sources.

Reads broll_suggestions from clips.json, searches Pexels API,
downloads candidates, and writes broll.json for human review.

Usage:
    python scripts/fetch_broll.py review/<name>/clips.json --output-dir review/<name>

Requires:
    PEXELS_API_KEY environment variable

Output:
    review/<name>/broll.json
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def load_config() -> dict:
    root = Path(__file__).parent.parent
    with open(root / "config" / "default.json") as f:
        return json.load(f)


def get_cache_dir(config: dict) -> Path:
    broll_config = config.get("broll", {})
    cache_dir = broll_config.get("cache_dir", "~/.viddy/broll_cache")
    cache_path = Path(os.path.expanduser(cache_dir))
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path


def load_cache_index(cache_dir: Path) -> dict:
    index_path = cache_dir / "cache_index.json"
    if index_path.exists():
        with open(index_path) as f:
            return json.load(f)
    return {}


def save_cache_index(cache_dir: Path, index: dict):
    index_path = cache_dir / "cache_index.json"
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)


def query_hash(query: str) -> str:
    return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:12]


def search_pexels(query: str, api_key: str, per_page: int = 5) -> list[dict]:
    """Search Pexels Videos API."""
    url = (
        f"https://api.pexels.com/videos/search"
        f"?query={urllib.parse.quote(query)}"
        f"&per_page={per_page}"
    )
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "User-Agent": "Viddy/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"    Pexels search failed for '{query}': {e}", file=sys.stderr)
        return []

    results = []
    for video in data.get("videos", []):
        # Find best resolution mp4 file
        mp4_files = [vf for vf in video.get("video_files", []) if vf.get("file_type") == "video/mp4"]
        if not mp4_files:
            continue
        # Sort by width descending, pick highest res (ideally 1080p+)
        mp4_files.sort(key=lambda vf: vf.get("width", 0), reverse=True)
        best_file = mp4_files[0]

        results.append({
            "source": "pexels",
            "source_id": str(video["id"]),
            "url": best_file["link"],
            "duration_seconds": video.get("duration", 0),
            "width": best_file.get("width", 0),
            "height": best_file.get("height", 0),
            "photographer": video.get("user", {}).get("name", "Unknown"),
        })

    return results


def score_result(result: dict) -> float:
    """Score a search result for quality and suitability."""
    score = 0.0
    w = result.get("width", 0)
    dur = result.get("duration_seconds", 0)

    # Resolution
    if w >= 1920:
        score += 3.0
    elif w >= 1280:
        score += 1.0

    # Duration sweet spot (5-30s)
    if 5 <= dur <= 30:
        score += 2.0
    elif dur > 30:
        score += 1.0
    elif dur < 3:
        score -= 1.0

    # Landscape orientation
    h = result.get("height", 0)
    if w > h:
        score += 2.0

    return score


def download_video(url: str, dest: Path, timeout: int = 60) -> bool:
    """Download a video file."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Viddy/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    Download failed: {e}", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        return False


def trim_video(src: Path, dest: Path, max_duration: float = 15.0) -> bool:
    """Trim a video to max_duration seconds using FFmpeg."""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-t", str(max_duration),
            "-c", "copy",
            str(dest)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def fetch_broll_for_suggestion(
    suggestion: dict,
    clip_rank: int,
    suggestion_idx: int,
    api_key: str,
    cache_dir: Path,
    cache_index: dict,
    max_candidates: int = 3,
) -> dict:
    """Fetch B-roll candidates for a single suggestion."""
    query = suggestion["search_query"]
    qhash = query_hash(query)

    # Check cache
    cached = cache_index.get(qhash)
    if cached and all(Path(c["local_path"]).exists() for c in cached.get("results", [])):
        print(f"    Cache hit: '{query}'")
        results = cached["results"]
    else:
        print(f"    Searching: '{query}'")
        search_results = search_pexels(query, api_key, per_page=5)

        if not search_results:
            return {
                "id": f"broll_c{clip_rank}_s{suggestion_idx}",
                "search_query": query,
                "from_seconds": suggestion["from_seconds"],
                "to_seconds": suggestion["to_seconds"],
                "reason": suggestion.get("reason", ""),
                "approved": True,
                "selected_video": None,
                "alternatives": [],
            }

        # Score and sort
        search_results.sort(key=score_result, reverse=True)
        top_results = search_results[:max_candidates]

        # Download
        results = []
        for r in top_results:
            filename = f"{qhash}_{r['source_id']}.mp4"
            local_path = cache_dir / filename

            if not local_path.exists():
                print(f"      Downloading {r['source']}:{r['source_id']}...")
                if not download_video(r["url"], local_path):
                    continue

                # Trim to reasonable length
                trimmed = cache_dir / f"{qhash}_{r['source_id']}_trimmed.mp4"
                if trim_video(local_path, trimmed, max_duration=15.0):
                    local_path.unlink()
                    trimmed.rename(local_path)

            r["local_path"] = str(local_path)
            results.append(r)

        # Update cache
        cache_index[qhash] = {
            "query": query,
            "results": results,
            "fetched_at": time.time(),
        }

    if not results:
        return {
            "id": f"broll_c{clip_rank}_s{suggestion_idx}",
            "search_query": query,
            "from_seconds": suggestion["from_seconds"],
            "to_seconds": suggestion["to_seconds"],
            "reason": suggestion.get("reason", ""),
            "approved": False,
            "selected_video": None,
            "alternatives": [],
        }

    selected = results[0]
    alternatives = results[1:]

    return {
        "id": f"broll_c{clip_rank}_s{suggestion_idx}",
        "search_query": query,
        "from_seconds": suggestion["from_seconds"],
        "to_seconds": suggestion["to_seconds"],
        "reason": suggestion.get("reason", ""),
        "approved": True,
        "selected_video": {
            "source": selected["source"],
            "source_id": selected["source_id"],
            "url": selected["url"],
            "local_path": selected["local_path"],
            "duration_seconds": selected["duration_seconds"],
            "resolution": f"{selected['width']}x{selected['height']}",
            "attribution": f"Video by {selected.get('photographer', 'Unknown')} from Pexels",
        },
        "alternatives": [
            {
                "source": alt["source"],
                "source_id": alt["source_id"],
                "url": alt["url"],
                "local_path": alt["local_path"],
                "resolution": f"{alt['width']}x{alt['height']}",
            }
            for alt in alternatives
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch B-roll from Pexels for clip suggestions")
    parser.add_argument("clips_json", help="Path to clips.json")
    parser.add_argument("--output-dir", help="Output directory (default: same as clips.json)")
    args = parser.parse_args()

    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        print("Warning: PEXELS_API_KEY not set. Skipping B-roll fetch.", file=sys.stderr)
        print("  Get a free key at https://www.pexels.com/api/", file=sys.stderr)
        sys.exit(0)  # Soft fail — don't block the pipeline

    with open(args.clips_json) as f:
        clips_data = json.load(f)

    config = load_config()
    cache_dir = get_cache_dir(config)
    cache_index = load_cache_index(cache_dir)

    output_dir = args.output_dir or str(Path(args.clips_json).parent)
    os.makedirs(output_dir, exist_ok=True)

    broll_data = {"clips": []}
    total_suggestions = 0
    total_fetched = 0

    for clip in clips_data.get("clips", []):
        if not clip.get("approved", True):
            continue

        clip_rank = clip.get("rank", 0)
        suggestions = clip.get("broll_suggestions", [])

        if not suggestions:
            continue

        print(f"  Clip {clip_rank}: {len(suggestions)} B-roll suggestions")

        clip_broll = {
            "clip_rank": clip_rank,
            "suggestions": [],
        }

        for idx, suggestion in enumerate(suggestions, 1):
            total_suggestions += 1
            result = fetch_broll_for_suggestion(
                suggestion, clip_rank, idx, api_key, cache_dir, cache_index,
            )
            clip_broll["suggestions"].append(result)
            if result.get("selected_video"):
                total_fetched += 1

            # Rate limit: be polite to Pexels
            time.sleep(0.5)

        broll_data["clips"].append(clip_broll)

    save_cache_index(cache_dir, cache_index)

    broll_path = os.path.join(output_dir, "broll.json")
    with open(broll_path, "w") as f:
        json.dump(broll_data, f, indent=2)

    print(f"\n  B-roll fetched: {total_fetched}/{total_suggestions} suggestions")
    print(f"  B-roll data:   {broll_path}")
    print(f"  Cache dir:     {cache_dir}")
    print(f"\n  Review broll.json to approve/reject/swap B-roll clips.")


if __name__ == "__main__":
    main()
