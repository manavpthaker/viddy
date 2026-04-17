import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import type {CaptionGroup, BrandConfig} from '../types';

interface AnimatedCaptionsProps {
  groups: CaptionGroup[];
  brand: BrandConfig;
  format: 'vertical_9_16' | 'square_1_1';
}

export const AnimatedCaptions: React.FC<AnimatedCaptionsProps> = ({
  groups,
  brand,
  format,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const currentTime = frame / fps;

  // Find the active caption group
  const activeGroup = groups.find(
    (g) => currentTime >= g.start && currentTime <= g.end
  );

  if (!activeGroup) return null;

  // Scale font size based on format
  const baseFontSize = brand.fonts.caption_size_px;
  const fontSize = format === 'square_1_1' ? baseFontSize * 0.85 : baseFontSize;

  // Fade in the group
  const groupStartFrame = activeGroup.start * fps;
  const groupEndFrame = activeGroup.end * fps;
  const opacity = interpolate(
    frame,
    [groupStartFrame, groupStartFrame + 4, groupEndFrame - 3, groupEndFrame],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  // Bottom margin adjusts by format
  const marginBottom =
    format === 'square_1_1'
      ? brand.caption_margin_bottom_px * 0.6
      : brand.caption_margin_bottom_px;

  return (
    <div
      style={{
        position: 'absolute',
        bottom: marginBottom,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity,
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: fontSize * 0.25,
          padding: `${fontSize * 0.3}px ${fontSize * 0.5}px`,
          borderRadius: 8,
          backgroundColor: 'rgba(0, 0, 0, 0.6)',
        }}
      >
        {activeGroup.words.map((word, i) => {
          // Is this word currently being spoken?
          const isActive =
            currentTime >= word.start && currentTime <= word.end;
          // Has this word been spoken?
          const isPast = currentTime > word.end;

          const wordColor = word.highlight
            ? brand.colors.caption_highlight
            : isActive
              ? brand.colors.caption_text
              : isPast
                ? brand.colors.caption_text
                : 'rgba(255, 255, 255, 0.5)';

          // Scale up slightly when active
          const scale = isActive
            ? interpolate(
                frame,
                [word.start * fps, word.start * fps + 3],
                [1, 1.1],
                {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
              )
            : 1;

          return (
            <span
              key={i}
              style={{
                fontFamily: brand.fonts.caption,
                fontWeight: word.highlight
                  ? 900
                  : isActive
                    ? brand.fonts.caption_weight
                    : 600,
                fontSize,
                color: wordColor,
                transform: `scale(${scale})`,
                display: 'inline-block',
                textShadow: '0 2px 8px rgba(0,0,0,0.5)',
                transition: 'color 0.1s',
              }}
            >
              {word.word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
