import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, Easing, OffthreadVideo} from 'remotion';
import type {SpeakerSegment, ZoomMoment, ReframeTrack, ReframeKeyframe} from '../types';

interface SpeakerZoomProps {
  src: string;
  speakerTimeline: SpeakerSegment[];
  zoomMoments: ZoomMoment[];
  baseScale: number;
  zoomScale: number;
  transitionSeconds: number;
  format: 'vertical_9_16' | 'square_1_1';
  sourceWidth: number;
  sourceHeight: number;
  reframe?: ReframeTrack | null;
}

// How much of the output height the active face should occupy. Lower = tighter.
const FACE_HEIGHT_FRACTION = 0.4;
// Vertical anchor for the face center (0.45 = slightly above middle, leaves headroom).
const FACE_VERTICAL_ANCHOR = 0.45;
const MIN_SCALE = 1.0;
const MAX_SCALE = 2.4;

/** Linearly interpolate the reframe target (cx, cy, face_h) at a given time. */
function sampleReframe(keyframes: ReframeKeyframe[], t: number): {cx: number; cy: number; faceH: number} {
  if (keyframes.length === 0) return {cx: 0.5, cy: 0.45, faceH: 0.5};
  if (t <= keyframes[0].t) {
    const k = keyframes[0];
    return {cx: k.cx, cy: k.cy, faceH: k.face_h};
  }
  const last = keyframes[keyframes.length - 1];
  if (t >= last.t) return {cx: last.cx, cy: last.cy, faceH: last.face_h};

  // Find the bracketing keyframes.
  let lo = 0;
  let hi = keyframes.length - 1;
  for (let i = 0; i < keyframes.length - 1; i++) {
    if (keyframes[i].t <= t && t <= keyframes[i + 1].t) {
      lo = i;
      hi = i + 1;
      break;
    }
  }
  const a = keyframes[lo];
  const b = keyframes[hi];
  const span = b.t - a.t || 1;
  const f = (t - a.t) / span;
  return {
    cx: a.cx + (b.cx - a.cx) * f,
    cy: a.cy + (b.cy - a.cy) * f,
    faceH: a.face_h + (b.face_h - a.face_h) * f,
  };
}

export const SpeakerZoom: React.FC<SpeakerZoomProps> = ({
  src,
  speakerTimeline,
  zoomMoments,
  baseScale,
  zoomScale,
  transitionSeconds,
  format,
  sourceWidth,
  sourceHeight,
  reframe,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const currentTime = frame / fps;

  // Source dimensions: prefer the real values measured during tracking.
  const srcW = reframe?.source_width || sourceWidth;
  const srcH = reframe?.source_height || sourceHeight;
  const sourceAspect = srcW / srcH;
  const targetAspect = width / height;

  // Fit source so it COVERS the target (we always crop into it).
  let videoWidth: number;
  let videoHeight: number;
  if (sourceAspect > targetAspect) {
    videoHeight = height;
    videoWidth = height * sourceAspect;
  } else {
    videoWidth = width;
    videoHeight = width / sourceAspect;
  }

  // Emphasis zoom boost (shared by both paths): a subtle punch during key moments.
  const getZoomBoost = (): number => {
    for (const zm of zoomMoments) {
      const start = zm.at_seconds;
      const end = start + zm.hold_seconds;
      if (currentTime >= start && currentTime <= end) {
        const transIn = 0.3;
        const transOut = 0.3;
        if (currentTime < start + transIn) {
          return Easing.inOut(Easing.cubic)((currentTime - start) / transIn);
        }
        if (currentTime > end - transOut) {
          return Easing.inOut(Easing.cubic)((end - currentTime) / transOut);
        }
        return 1;
      }
    }
    return 0;
  };
  const zoomBoost = getZoomBoost();

  // ─────────────────────────────────────────────────────────────────────
  // Path A: REAL audio-visual reframing (crop to the active face).
  // ─────────────────────────────────────────────────────────────────────
  if (reframe && reframe.keyframes && reframe.keyframes.length > 0) {
    const {cx, cy, faceH} = sampleReframe(reframe.keyframes, currentTime);
    const clampedFaceH = Math.min(0.9, Math.max(0.1, faceH));

    // Scale so the face fills FACE_HEIGHT_FRACTION of the output height.
    const faceRenderedH = clampedFaceH * videoHeight;
    let scale = (FACE_HEIGHT_FRACTION * height) / faceRenderedH;
    // Apply emphasis punch, then clamp to a sane range.
    scale = scale * (1 + (zoomScale - 1) * zoomBoost);
    scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

    // Place the face center at (width/2, height * FACE_VERTICAL_ANCHOR).
    // Local face point in the (unscaled) video: (cx*videoWidth, cy*videoHeight).
    const faceX = cx * videoWidth;
    const faceY = cy * videoHeight;
    let tx = width * 0.5 - faceX * scale;
    let ty = height * FACE_VERTICAL_ANCHOR - faceY * scale;

    // Clamp translation so the scaled video always covers the frame (no black bars).
    const scaledW = videoWidth * scale;
    const scaledH = videoHeight * scale;
    tx = Math.min(0, Math.max(width - scaledW, tx));
    ty = Math.min(0, Math.max(height - scaledH, ty));

    return (
      <div
        style={{
          position: 'absolute',
          inset: 0,
          overflow: 'hidden',
          backgroundColor: '#000',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: videoWidth,
            height: videoHeight,
            transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
            transformOrigin: '0 0',
          }}
        >
          <OffthreadVideo src={src} style={{width: videoWidth, height: videoHeight}} />
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────
  // Path B: LEGACY transcript-based reframing (fixed left/right/center shift).
  // Used when no reframe track is available (deps missing, no faces, etc.).
  // ─────────────────────────────────────────────────────────────────────
  const getActiveSpeakerPosition = (): string => {
    for (const seg of speakerTimeline) {
      if (currentTime >= seg.from_seconds && currentTime <= seg.to_seconds) {
        return seg.position;
      }
    }
    return 'center';
  };

  const getTargetTranslateX = (position: string, renderedWidth: number): number => {
    if (position === 'left') return renderedWidth * 0.2;
    if (position === 'right') return -renderedWidth * 0.2;
    return 0;
  };

  const activePosition = getActiveSpeakerPosition();
  const targetX = getTargetTranslateX(activePosition, videoWidth);

  let smoothX = targetX;
  for (let i = 0; i < speakerTimeline.length; i++) {
    const seg = speakerTimeline[i];
    if (currentTime >= seg.from_seconds && currentTime <= seg.to_seconds) {
      const transStart = seg.from_seconds;
      const transEnd = transStart + transitionSeconds;
      if (currentTime < transEnd && i > 0) {
        const prevPosition = speakerTimeline[i - 1].position;
        const prevX = getTargetTranslateX(prevPosition, videoWidth);
        const progress = Easing.inOut(Easing.cubic)(
          (currentTime - transStart) / transitionSeconds
        );
        smoothX = interpolate(progress, [0, 1], [prevX, targetX]);
      }
      break;
    }
  }

  const scale = baseScale + (zoomScale - baseScale) * zoomBoost;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        backgroundColor: '#000',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: `translate(-50%, -50%) scale(${scale}) translateX(${smoothX}px)`,
          transformOrigin: 'center center',
        }}
      >
        <OffthreadVideo src={src} style={{width: videoWidth, height: videoHeight}} />
      </div>
    </div>
  );
};
