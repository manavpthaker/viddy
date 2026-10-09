"""
Step 5.5: Audio-visual active-speaker tracking for real auto-reframing.

This is what makes clips look professionally reframed (Riverside-style):
instead of guessing "left / right / center" from the transcript, we actually
look at the pixels and listen to the audio to decide WHO is on screen and
WHO is talking, frame by frame.

Pipeline:
  1. Probe real source dimensions (don't assume 1920x1080).
  2. Detect + track faces across the clip (MediaPipe FaceMesh).
  3. Measure lip motion per face (mouth openness over time).
  4. Find speech regions (pyannote VAD if available, else audio-energy VAD).
  5. Active speaker = the on-screen face whose lips move during speech.
  6. Emit a smoothed, debounced reframe track (normalized crop centers).

The whole step is OPTIONAL and degrades gracefully:
  - No MediaPipe  -> no reframe file written; renderer falls back to the
    legacy transcript-based speaker timeline.
  - No pyannote   -> energy-based voice-activity detection is used instead.
  - No faces found -> a centered fallback track is written.

Usage:
    python scripts/track_speakers.py clips/<name>/clip_01.mp4
    python scripts/track_speakers.py clips/<name>/            # all clips in dir

Output:
    Writes <clip>.reframe.json next to each clip. Consumed by prepare_render.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# ── Optional heavy dependencies, imported lazily so the step can no-op ──

def _try_import_cv2():
    try:
        import cv2  # noqa
        return cv2
    except Exception:
        return None


def _try_import_mediapipe():
    try:
        import mediapipe as mp  # noqa
        return mp
    except Exception:
        return None


def _try_import_numpy():
    try:
        import numpy as np  # noqa
        return np
    except Exception:
        return None


# ── Face-landmark backend (supports both mediapipe APIs) ──
#
# Older mediapipe wheels expose the legacy `mp.solutions.face_mesh`. Newer ones
# (0.10.30+ on some platforms) ship ONLY the Tasks API (`FaceLandmarker`), which
# needs a downloaded model file. We support whichever is present so the tracker
# works across environments. Both return the same 478-landmark layout, so the
# lip indices below are valid for either.

_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def _ensure_face_model() -> str | None:
    """Download the FaceLandmarker .task model (cached) for the Tasks API."""
    cache_dir = Path.home() / ".cache" / "viddy"
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "face_landmarker.task"
    if model_path.exists() and model_path.stat().st_size > 0:
        return str(model_path)
    try:
        import urllib.request
        print("  Downloading face landmark model (first run only)...")
        urllib.request.urlretrieve(_FACE_MODEL_URL, str(model_path))
        return str(model_path)
    except Exception as e:
        print(f"  (could not download face model: {e})")
        return None


class _LM:
    """Minimal landmark with normalized x/y (full-frame coordinates)."""
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class _FaceBackend:
    """Wraps a mediapipe face-landmark detector behind a uniform interface.

    detect(rgb) -> list of faces, each a list of _LM landmarks in full-frame
    normalized [0,1] coordinates. self.mode is None when no backend is available.

    MediaPipe's detector downscales its input, so small faces (e.g. a corner
    webcam over a screen share) are invisible at full frame. We therefore try
    the full frame first (cheap, handles talking-heads) and fall back to TILED
    detection — scanning overlapping crops and mapping coordinates back — which
    recovers small faces anywhere in the frame.
    """

    def __init__(self):
        self.mode = None
        self._legacy = None
        self._tasks = None
        self._mp = None

        mp = _try_import_mediapipe()
        if mp is None:
            return

        # Prefer the legacy solutions API when available (no model download).
        if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
            self._legacy = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=3,
                refine_landmarks=True,
                min_detection_confidence=0.3,
            )
            self.mode = "solutions"
            return

        # Fall back to the Tasks API (FaceLandmarker + model file), IMAGE mode
        # so we can run it freely on tiles without monotonic-timestamp rules.
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            model_path = _ensure_face_model()
            if not model_path:
                return
            options = vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=3,
                min_face_detection_confidence=0.3,
            )
            self._tasks = vision.FaceLandmarker.create_from_options(options)
            self._mp = mp
            self.mode = "tasks"
        except Exception as e:
            print(f"  (Tasks FaceLandmarker unavailable: {e})")

    def _detect_image(self, rgb) -> list[list[_LM]]:
        """Run the underlying detector once; coords normalized to this image."""
        faces: list[list[_LM]] = []
        if self.mode == "solutions":
            res = self._legacy.process(rgb)
            for lm in res.multi_face_landmarks or []:
                faces.append([_LM(p.x, p.y) for p in lm.landmark])
        elif self.mode == "tasks":
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            res = self._tasks.detect(image)
            for lm in res.face_landmarks or []:
                faces.append([_LM(p.x, p.y) for p in lm])
        return faces

    @staticmethod
    def _center(face: list[_LM]) -> tuple[float, float, float]:
        xs = [p.x for p in face]
        ys = [p.y for p in face]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(ys) - min(ys))

    def detect(self, rgb) -> list[list[_LM]]:
        # Pass 1: full frame (handles normally-sized / multiple faces cheaply).
        faces = self._detect_image(rgb)
        if faces:
            return faces

        # Pass 2: tiled scan to recover small faces (e.g. corner webcams).
        # MediaPipe needs the face to fill a good fraction of its input, so we
        # use a fine grid with overlap. Tiles MUST be contiguous arrays — a bare
        # numpy slice silently fails detection inside mp.Image.
        import numpy as np
        H, W = rgb.shape[:2]
        cols, rows, overlap = 5, 3, 0.2
        tw = W / cols
        th = H / rows
        found: list[list[_LM]] = []
        for r in range(rows):
            for c in range(cols):
                x0 = int(max(0, (c - overlap) * tw))
                x1 = int(min(W, (c + 1 + overlap) * tw))
                y0 = int(max(0, (r - overlap) * th))
                y1 = int(min(H, (r + 1 + overlap) * th))
                tile = np.ascontiguousarray(rgb[y0:y1, x0:x1])
                if tile.shape[0] < 32 or tile.shape[1] < 32:
                    continue
                cw = x1 - x0
                ch = y1 - y0
                for face in self._detect_image(tile):
                    # Map tile-normalized coords back to full-frame normalized.
                    mapped = [_LM((x0 + p.x * cw) / W, (y0 + p.y * ch) / H) for p in face]
                    found.append(mapped)

        # Dedupe faces detected in overlapping tiles (keep the largest).
        deduped: list[list[_LM]] = []
        for face in sorted(found, key=lambda f: self._center(f)[2], reverse=True):
            fx, fy, _ = self._center(face)
            if all(((fx - self._center(d)[0]) ** 2 + (fy - self._center(d)[1]) ** 2) ** 0.5 > 0.06
                   for d in deduped):
                deduped.append(face)
        return deduped

    def close(self):
        try:
            if self._legacy is not None:
                self._legacy.close()
            if self._tasks is not None:
                self._tasks.close()
        except Exception:
            pass


# ── ffprobe helpers ──

def probe_dimensions(video_path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-select_streams", "v:0", "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        return (1920, 1080)
    s = streams[0]
    return (int(s.get("width", 1920)), int(s.get("height", 1080)))


def probe_duration(video_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def _cropdetect(video_path: str, ss: float, limit: int) -> tuple | None:
    """Run cropdetect at one threshold; return the last (w,h,x,y) suggestion."""
    cmd = [
        "ffmpeg", "-ss", f"{ss:.1f}", "-i", video_path, "-t", "4",
        "-vf", f"cropdetect=limit={limit}:round=2:reset=0", "-f", "null", "-",
    ]
    stderr = subprocess.run(cmd, capture_output=True, text=True).stderr
    last = None
    for line in stderr.split("\n"):
        if "crop=" in line:
            try:
                spec = line.split("crop=")[1].strip().split()[0]
                cw, ch, cx, cy = (int(v) for v in spec.split(":"))
                last = (cw, ch, cx, cy)
            except (ValueError, IndexError):
                pass
    return last


def detect_screen_rect(video_path: str, W: int, H: int, duration: float) -> dict | None:
    """Find the non-letterbox content box via ffmpeg cropdetect.

    The default threshold (24) misses dark-but-not-black bars (common with
    compressed screen recordings), so we escalate the limit until a real,
    sanely-sized content box appears. Returns a normalized {x,y,w,h} or None.
    """
    ss = max(0.0, duration * 0.4)
    for limit in (24, 48, 80, 120):
        res = _cropdetect(video_path, ss, limit)
        if not res:
            continue
        cw, ch, cx, cy = res
        if cw < W * 0.3 or ch < H * 0.3:
            continue  # implausibly small — wrong threshold
        if cw >= W * 0.98 and ch >= H * 0.98:
            continue  # no trim at this threshold — escalate
        return {
            "x": round(cx / W, 4), "y": round(cy / H, 4),
            "w": round(cw / W, 4), "h": round(ch / H, 4),
        }
    return None


def face_position_stats(keyframes: list, np) -> dict:
    """Median face size/position over the clip — used to pick speaker vs composite."""
    if not keyframes:
        return {}
    cx = float(np.median([k["cx"] for k in keyframes]))
    cy = float(np.median([k["cy"] for k in keyframes]))
    fh = float(np.median([k["face_h"] for k in keyframes]))
    return {
        "median_cx": round(cx, 4),
        "median_cy": round(cy, 4),
        "median_face_h": round(fh, 4),
        "corner_offset": round(max(abs(cx - 0.5), abs(cy - 0.5)), 4),
    }


# ── Mouth-openness landmarks (MediaPipe FaceMesh, refine_landmarks=True) ──
# Inner-lip top/bottom and mouth corners; used to estimate "is the mouth moving".
_LIP_TOP = 13
_LIP_BOTTOM = 14
_MOUTH_LEFT = 78
_MOUTH_RIGHT = 308


def detect_face_tracks(video_path: str, sample_fps: float, max_faces: int = 3) -> list[dict]:
    """Detect and track faces across the clip.

    Returns a list of tracks. Each track is:
        {"id": int, "frames": [{"t", "cx", "cy", "h", "mouth": float}, ...]}
    where cx, cy, h are normalized [0,1] relative to source dimensions.

    Returns [] if MediaPipe / OpenCV are unavailable or no faces are found.
    """
    cv2 = _try_import_cv2()
    np = _try_import_numpy()
    if cv2 is None or np is None:
        print("  (face tracking unavailable: install opencv-python + numpy)")
        return []

    backend = _FaceBackend()
    if backend.mode is None:
        print("  (face tracking unavailable: install mediapipe)")
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("  (could not open video for face tracking)")
        backend.close()
        return []

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, int(round(src_fps / sample_fps)))
    print(f"  face backend: mediapipe ({backend.mode})")

    # A track is an open trajectory; we greedily match detections by center
    # distance frame-to-frame so a face keeps a stable id across the clip.
    tracks: list[dict] = []
    MATCH_DIST = 0.12  # normalized center distance to consider "same face"

    frame_idx = 0
    try:
        while True:
            ok = cap.grab()
            if not ok:
                break
            if frame_idx % frame_step != 0:
                frame_idx += 1
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break

            t = frame_idx / src_fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = backend.detect(rgb)

            detections = []
            for pts in faces:
                # Each face is a flat list of landmarks with .x/.y (full-frame).
                xs = [p.x for p in pts]
                ys = [p.y for p in pts]
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                cx = (x0 + x1) / 2.0
                cy = (y0 + y1) / 2.0
                h = max(1e-4, y1 - y0)

                top = pts[_LIP_TOP]
                bot = pts[_LIP_BOTTOM]
                left = pts[_MOUTH_LEFT]
                right = pts[_MOUTH_RIGHT]
                mouth_w = max(1e-4, abs(right.x - left.x))
                # Vertical lip gap normalized by mouth width -> openness ratio.
                mouth_open = abs(bot.y - top.y) / mouth_w

                detections.append({"cx": cx, "cy": cy, "h": h, "mouth": mouth_open})

            # Greedy match each detection to the nearest recently-seen track.
            used = set()
            for det in detections:
                best_track = None
                best_dist = MATCH_DIST
                for tr in tracks:
                    if tr["id"] in used:
                        continue
                    last = tr["frames"][-1]
                    dist = ((last["cx"] - det["cx"]) ** 2 + (last["cy"] - det["cy"]) ** 2) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_track = tr
                if best_track is None:
                    best_track = {"id": len(tracks), "frames": []}
                    tracks.append(best_track)
                used.add(best_track["id"])
                best_track["frames"].append({
                    "t": round(t, 3),
                    "cx": round(det["cx"], 4),
                    "cy": round(det["cy"], 4),
                    "h": round(det["h"], 4),
                    "mouth": round(det["mouth"], 4),
                })

            frame_idx += 1
    finally:
        cap.release()
        backend.close()

    # Drop blink-length tracks (spurious detections).
    min_frames = max(2, int(sample_fps * 0.5))
    tracks = [t for t in tracks if len(t["frames"]) >= min_frames]
    return tracks


def compute_lip_motion(track: dict, np) -> None:
    """Annotate each frame with a short-window lip-motion energy in-place."""
    mouths = np.array([f["mouth"] for f in track["frames"]], dtype=float)
    if len(mouths) < 2:
        for f in track["frames"]:
            f["motion"] = 0.0
        return
    # Local deviation of mouth openness = talking energy. Window ~5 samples.
    win = min(5, len(mouths))
    motion = np.zeros_like(mouths)
    for i in range(len(mouths)):
        lo = max(0, i - win // 2)
        hi = min(len(mouths), i + win // 2 + 1)
        motion[i] = float(np.std(mouths[lo:hi]))
    for f, m in zip(track["frames"], motion):
        f["motion"] = round(float(m), 5)


# ── Voice-activity detection ──

def speech_segments_pyannote(video_path: str) -> list[tuple[float, float]] | None:
    """Voice-activity detection via pyannote. Returns None if unavailable."""
    try:
        from pyannote.audio import Pipeline
    except Exception:
        return None

    token = os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        print("  (pyannote installed but HUGGINGFACE_TOKEN not set; using energy VAD)")
        return None

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/voice-activity-detection", use_auth_token=token
        )
    except Exception as e:
        print(f"  (pyannote pipeline load failed: {e}; using energy VAD)")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "audio.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", "16000", wav],
            capture_output=True,
        )
        try:
            vad = pipeline(wav)
        except Exception as e:
            print(f"  (pyannote inference failed: {e}; using energy VAD)")
            return None
        return [(seg.start, seg.end) for seg in vad.get_timeline().support()]


def speech_segments_energy(video_path: str, np) -> list[tuple[float, float]]:
    """Fallback VAD: treat non-silent regions as speech via ffmpeg silencedetect."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", "silencedetect=noise=-32dB:d=0.2",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = probe_duration(video_path)

    silences = []
    start = None
    for line in result.stderr.split("\n"):
        if "silence_start:" in line:
            try:
                start = float(line.split("silence_start:")[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif "silence_end:" in line and start is not None:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                silences.append((start, end))
                start = None
            except (ValueError, IndexError):
                pass

    # Invert silence ranges into speech ranges.
    speech = []
    prev = 0.0
    for s, e in silences:
        if s > prev:
            speech.append((prev, s))
        prev = e
    if prev < duration:
        speech.append((prev, duration))
    return speech


def is_speaking_at(t: float, speech: list[tuple[float, float]]) -> bool:
    for s, e in speech:
        if s <= t <= e:
            return True
    return False


# ── Active-speaker assignment + reframe track ──

def build_reframe_keyframes(
    tracks: list[dict],
    speech: list[tuple[float, float]],
    duration: float,
    sample_fps: float,
    np,
) -> tuple[list[dict], str]:
    """Decide the active face at each sample time and emit smoothed keyframes.

    Returns (keyframes, method). Keyframes carry normalized crop centers.
    """
    # Index each track's frames by sample time for quick lookup.
    for tr in tracks:
        compute_lip_motion(tr, np)

    n_samples = max(1, int(round(duration * sample_fps)))
    dt = 1.0 / sample_fps

    def face_at(tr: dict, t: float):
        """Nearest sampled face frame within half a sample step, else None."""
        best = None
        best_dt = dt * 0.75
        for f in tr["frames"]:
            d = abs(f["t"] - t)
            if d < best_dt:
                best_dt = d
                best = f
        return best

    # Raw per-sample choice of active track id.
    raw_active: list[int | None] = []
    for i in range(n_samples):
        t = i * dt
        present = [(tr, face_at(tr, t)) for tr in tracks]
        present = [(tr, f) for tr, f in present if f is not None]

        if not present:
            raw_active.append(None)
            continue

        speaking = is_speaking_at(t, speech)
        if speaking and len(present) > 1:
            # Whoever's lips are moving most is the speaker.
            tr, _ = max(present, key=lambda pf: pf[1]["motion"])
            raw_active.append(tr["id"])
        elif len(present) == 1:
            raw_active.append(present[0][0]["id"])
        else:
            # Silence with multiple faces: defer (hold previous) by marking -1.
            raw_active.append(-1)

    # Resolve holds (-1) to the previous decided speaker.
    last = None
    for i in range(n_samples):
        if raw_active[i] == -1:
            raw_active[i] = last
        elif raw_active[i] is not None:
            last = raw_active[i]
    # Back-fill leading holds with the first real decision.
    first_real = next((a for a in raw_active if a is not None), None)
    raw_active = [a if a is not None else first_real for a in raw_active]

    # Debounce: only commit a switch once a new id has held for min_hold.
    min_hold = max(1, int(round(0.4 * sample_fps)))
    committed: list[int | None] = []
    current = first_real
    run_id = first_real
    run_len = 0
    for a in raw_active:
        if a == run_id:
            run_len += 1
        else:
            run_id = a
            run_len = 1
        if run_id is not None and run_len >= min_hold:
            current = run_id
        committed.append(current)

    method = "av_active_speaker" if (len(tracks) > 1 and speech) else (
        "face_track" if tracks else "fallback_center"
    )

    # Build keyframes from committed active face, smoothing center with EMA.
    keyframes: list[dict] = []
    ema_cx = ema_cy = ema_h = None
    alpha = 0.35  # smoothing factor per sample
    for i in range(n_samples):
        t = i * dt
        active_id = committed[i]
        f = None
        if active_id is not None:
            tr = next((x for x in tracks if x["id"] == active_id), None)
            if tr is not None:
                f = face_at(tr, t)
        if f is None:
            # Hold previous target; if none yet, center.
            cx, cy, h = (ema_cx, ema_cy, ema_h) if ema_cx is not None else (0.5, 0.45, 0.4)
        else:
            cx, cy, h = f["cx"], f["cy"], f["h"]

        if ema_cx is None:
            ema_cx, ema_cy, ema_h = cx, cy, h
        else:
            ema_cx = alpha * cx + (1 - alpha) * ema_cx
            ema_cy = alpha * cy + (1 - alpha) * ema_cy
            ema_h = alpha * h + (1 - alpha) * ema_h

        keyframes.append({
            "t": round(t, 3),
            "cx": round(ema_cx, 4),
            "cy": round(ema_cy, 4),
            "face_h": round(ema_h, 4),
            "speaking": is_speaking_at(t, speech),
            "track": active_id if active_id is not None else -1,
        })

    return keyframes, method


def process_clip(video_path: str, sample_fps: float = 10.0) -> dict:
    np = _try_import_numpy()
    src_w, src_h = probe_dimensions(video_path)
    duration = probe_duration(video_path)

    out_path = str(Path(video_path).with_suffix(".reframe.json"))

    if np is None:
        print("  (numpy unavailable; skipping reframe, renderer will use legacy track)")
        return {"file": video_path, "written": False, "reason": "numpy unavailable"}

    # Shared-screen content box (only needs ffmpeg) — enables composite layout.
    screen_rect = detect_screen_rect(video_path, src_w, src_h, duration)

    tracks = detect_face_tracks(video_path, sample_fps)

    if not tracks:
        # No usable faces — write a centered track so the renderer still has
        # real source dimensions (fixes the hardcoded 1920x1080 assumption).
        payload = {
            "source_width": src_w,
            "source_height": src_h,
            "sampled_fps": sample_fps,
            "duration_seconds": round(duration, 3),
            "method": "fallback_center",
            "screen_rect": screen_rect,
            "keyframes": [{"t": 0.0, "cx": 0.5, "cy": 0.45, "face_h": 0.5, "speaking": False, "track": -1}],
        }
        with open(out_path, "w") as f:
            json.dump(payload, f, indent=2)
        return {"file": video_path, "written": True, "method": "fallback_center", "tracks": 0}

    speech = speech_segments_pyannote(video_path)
    vad_method = "pyannote"
    if speech is None:
        speech = speech_segments_energy(video_path, np)
        vad_method = "energy"

    keyframes, method = build_reframe_keyframes(tracks, speech, duration, sample_fps, np)

    payload = {
        "source_width": src_w,
        "source_height": src_h,
        "sampled_fps": sample_fps,
        "duration_seconds": round(duration, 3),
        "method": method,
        "vad": vad_method,
        "num_tracks": len(tracks),
        "screen_rect": screen_rect,
        "face_stats": face_position_stats(keyframes, np),
        "keyframes": keyframes,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    return {
        "file": video_path, "written": True, "method": method,
        "vad": vad_method, "tracks": len(tracks), "keyframes": len(keyframes),
        "screen_rect": bool(screen_rect),
    }


def main():
    parser = argparse.ArgumentParser(description="Audio-visual active-speaker tracking")
    parser.add_argument("path", help="Path to a clip or directory of clips")
    parser.add_argument("--sample-fps", type=float, default=10.0,
                        help="Face-sampling rate in fps (default: 10)")
    args = parser.parse_args()

    target = Path(args.path)
    if target.is_file():
        clips = [str(target)]
    elif target.is_dir():
        clips = sorted(
            str(p) for p in target.glob("clip_*.mp4")
            if ".original" not in p.name
        )
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    if not clips:
        print("No clips found.")
        sys.exit(0)

    print(f"Tracking active speakers in {len(clips)} clip(s) at {args.sample_fps}fps...")
    print()

    any_written = False
    for clip in clips:
        name = Path(clip).name
        try:
            result = process_clip(clip, args.sample_fps)
        except Exception as e:
            print(f"  {name}: tracking failed ({e}); renderer will use legacy track")
            continue
        if result.get("written"):
            any_written = True
            print(f"  {name}: {result.get('method')} "
                  f"({result.get('tracks', 0)} faces, "
                  f"vad={result.get('vad', 'n/a')}, "
                  f"{result.get('keyframes', 0)} keyframes)")
        else:
            print(f"  {name}: skipped ({result.get('reason', 'unknown')})")

    if not any_written:
        print("\n  No reframe data written. Renderer falls back to transcript-based tracking.")
        # Non-fatal: the pipeline still renders, just without real reframing.


if __name__ == "__main__":
    main()
