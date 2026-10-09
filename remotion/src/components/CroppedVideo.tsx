import React from 'react';
import {OffthreadVideo} from 'remotion';

interface CroppedVideoProps {
  src: string;
  srcW: number;
  srcH: number;
  /** Output panel size in px. */
  panelW: number;
  panelH: number;
  /** Source rectangle to show, in normalized [0,1] coords. */
  srcRect: {x: number; y: number; w: number; h: number};
  /** Keep the panel fully covered (no edge bleed). Default true. */
  clamp?: boolean;
}

/**
 * Renders one cover-cropped view of a video: the given source rectangle is
 * scaled to fill the panel and centered. Used by ScreenSpeakerComposite to put
 * the shared screen and the speaker into separate panels of the same source.
 */
export const CroppedVideo: React.FC<CroppedVideoProps> = ({
  src,
  srcW,
  srcH,
  panelW,
  panelH,
  srcRect,
  clamp = true,
}) => {
  // Source rectangle in pixels.
  const rx = srcRect.x * srcW;
  const ry = srcRect.y * srcH;
  const rw = Math.max(1, srcRect.w * srcW);
  const rh = Math.max(1, srcRect.h * srcH);

  // Cover: scale so the rect fills the panel.
  const scale = Math.max(panelW / rw, panelH / rh);

  // Translate so the rect's center lands at the panel center.
  let tx = panelW / 2 - (rx + rw / 2) * scale;
  let ty = panelH / 2 - (ry + rh / 2) * scale;

  if (clamp) {
    tx = Math.min(0, Math.max(panelW - srcW * scale, tx));
    ty = Math.min(0, Math.max(panelH - srcH * scale, ty));
  }

  return (
    <div style={{position: 'absolute', width: panelW, height: panelH, overflow: 'hidden'}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: srcW,
          height: srcH,
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          transformOrigin: '0 0',
        }}
      >
        <OffthreadVideo src={src} style={{width: srcW, height: srcH}} />
      </div>
    </div>
  );
};
