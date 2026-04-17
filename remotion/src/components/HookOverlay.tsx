import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import type {BrandConfig} from '../types';

interface HookOverlayProps {
  text: string;
  brand: BrandConfig;
  displayDuration?: number; // seconds to show the hook
}

export const HookOverlay: React.FC<HookOverlayProps> = ({
  text,
  brand,
  displayDuration = 3,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const endFrame = displayDuration * fps;

  // Don't render after display duration
  if (frame > endFrame) return null;

  const opacity = interpolate(
    frame,
    [0, fps * 0.3, endFrame - fps * 0.5, endFrame],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  // Slide up slightly
  const translateY = interpolate(
    frame,
    [0, fps * 0.4],
    [20, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  return (
    <div
      style={{
        position: 'absolute',
        top: '8%',
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity,
        transform: `translateY(${translateY}px)`,
        zIndex: 15,
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          padding: '16px 28px',
          borderRadius: 12,
          borderLeft: `4px solid ${brand.colors.caption_highlight}`,
          maxWidth: '85%',
        }}
      >
        <span
          style={{
            fontFamily: brand.fonts.caption,
            fontWeight: 800,
            fontSize: brand.fonts.caption_size_px * 0.55,
            color: brand.colors.caption_text,
            lineHeight: 1.3,
            textShadow: '0 1px 4px rgba(0,0,0,0.3)',
          }}
        >
          {text}
        </span>
      </div>
    </div>
  );
};
