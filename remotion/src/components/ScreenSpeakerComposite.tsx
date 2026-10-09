import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {CroppedVideo} from './CroppedVideo';
import type {ReframeTrack, ReframeKeyframe, BrandConfig} from '../types';

interface ScreenSpeakerCompositeProps {
  src: string;
  reframe: ReframeTrack;
  brand: BrandConfig;
}

// Layout tuning (fractions of canvas height).
const TOP_MARGIN_FRAC = 0.03;
const BOTTOM_MARGIN_FRAC = 0.03;
const GAP_FRAC = 0.015;
const SCREEN_MAX_FRAC = 0.42; // screen panel never takes more than this of usable height
// Speaker band framing.
const FACE_HEIGHT_FRACTION = 0.34; // face fills this much of the (now taller) speaker band
const FACE_VERTICAL_ANCHOR = 0.42; // face above band center → headroom + torso below

/** Linear-interpolate the speaker target at time t. */
function sampleReframe(keyframes: ReframeKeyframe[], t: number) {
  if (!keyframes.length) return {cx: 0.5, cy: 0.5, faceH: 0.4};
  if (t <= keyframes[0].t) {
    const k = keyframes[0];
    return {cx: k.cx, cy: k.cy, faceH: k.face_h};
  }
  const last = keyframes[keyframes.length - 1];
  if (t >= last.t) return {cx: last.cx, cy: last.cy, faceH: last.face_h};
  let lo = 0;
  for (let i = 0; i < keyframes.length - 1; i++) {
    if (keyframes[i].t <= t && t <= keyframes[i + 1].t) {
      lo = i;
      break;
    }
  }
  const a = keyframes[lo];
  const b = keyframes[lo + 1];
  const f = (t - a.t) / (b.t - a.t || 1);
  return {
    cx: a.cx + (b.cx - a.cx) * f,
    cy: a.cy + (b.cy - a.cy) * f,
    faceH: a.face_h + (b.face_h - a.face_h) * f,
  };
}

/**
 * Screen + speaker stacked layout for screen-share recordings: the shared
 * screen content on top (kept whole, fit to width), the speaker face-framed in
 * a band below. Both are crops of the same source. Keeps the slides readable
 * instead of throwing them away to chase a corner webcam.
 */
export const ScreenSpeakerComposite: React.FC<ScreenSpeakerCompositeProps> = ({
  src,
  reframe,
  brand,
}) => {
  const frame = useCurrentFrame();
  const {fps, width: W, height: H} = useVideoConfig();
  const t = frame / fps;

  const srcW = reframe.source_width || 1920;
  const srcH = reframe.source_height || 1080;
  const accent = brand.colors.caption_highlight;

  // Screen region (defaults to the full frame if no content box was detected).
  const sr = reframe.screen_rect || {x: 0, y: 0, w: 1, h: 1};
  const screenAspect = (sr.w * srcW) / (sr.h * srcH);

  // ── Layout geometry: screen pinned near the top, speaker fills the rest ──
  // (so a short/wide screen panel doesn't leave big black bands).
  const topMargin = Math.round(H * TOP_MARGIN_FRAC);
  const bottomMargin = Math.round(H * BOTTOM_MARGIN_FRAC);
  const gap = Math.round(H * GAP_FRAC);
  const usable = H - topMargin - bottomMargin - gap;

  let screenPanelW = W;
  let screenPanelH = Math.round(W / screenAspect);

  // Cap the screen so the speaker always gets the majority of the frame.
  const maxScreenH = Math.round(usable * SCREEN_MAX_FRAC);
  if (screenPanelH > maxScreenH) {
    screenPanelH = maxScreenH;
    screenPanelW = Math.round(screenPanelH * screenAspect);
  }

  const screenX = Math.round((W - screenPanelW) / 2);
  const screenY = topMargin;
  const speakerY = screenY + screenPanelH + gap;
  const speakerPanelH = H - bottomMargin - speakerY; // fills remaining height

  // ── Speaker crop rect (face-framed, panel-aspect) ──
  const {cx, cy, faceH} = sampleReframe(reframe.keyframes, t);
  const effFaceH = Math.min(0.9, Math.max(0.08, faceH));
  const visHpx = (effFaceH * srcH) / FACE_HEIGHT_FRACTION;
  const visWpx = visHpx * (W / speakerPanelH);
  const speakerRect = {
    x: cx - visWpx / srcW / 2,
    y: cy - FACE_VERTICAL_ANCHOR * (visHpx / srcH),
    w: visWpx / srcW,
    h: visHpx / srcH,
  };

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        backgroundColor: brand.colors.background,
        overflow: 'hidden',
      }}
    >
      {/* Screen panel */}
      <div style={{position: 'absolute', left: screenX, top: screenY, width: screenPanelW, height: screenPanelH, borderRadius: 12, overflow: 'hidden'}}>
        <CroppedVideo
          src={src}
          srcW={srcW}
          srcH={srcH}
          panelW={screenPanelW}
          panelH={screenPanelH}
          srcRect={sr}
        />
      </div>

      {/* Accent divider */}
      <div style={{position: 'absolute', left: W / 2 - 36, top: speakerY - gap / 2 - 3, width: 72, height: 6, backgroundColor: accent, borderRadius: 3}} />

      {/* Speaker band */}
      <div style={{position: 'absolute', left: 0, top: speakerY, width: W, height: speakerPanelH, borderRadius: 12, overflow: 'hidden'}}>
        <CroppedVideo
          src={src}
          srcW={srcW}
          srcH={srcH}
          panelW={W}
          panelH={speakerPanelH}
          srcRect={speakerRect}
        />
      </div>
    </div>
  );
};
