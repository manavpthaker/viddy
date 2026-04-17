import React from 'react';
import {useCurrentFrame, useVideoConfig, spring, interpolate} from 'remotion';
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
  const {fps, height} = useVideoConfig();
  const currentTime = frame / fps;

  // Find the active caption group
  const activeGroup = groups.find(
    (g) => currentTime >= g.start && currentTime <= g.end
  );

  if (!activeGroup) return null;

  // Scale font size based on format
  const baseFontSize = brand.fonts.caption_size_px;
  const fontSize = format === 'square_1_1' ? baseFontSize * 0.8 : baseFontSize;

  // Caption safe zone: anchor at 60% of frame height
  // TikTok eats bottom 18%, top 12%. Never below 75%.
  const captionTop = format === 'square_1_1'
    ? Math.round(height * 0.70)
    : Math.round(height * 0.60);

  // Spring entrance for the group
  const groupStartFrame = Math.round(activeGroup.start * fps);
  const enterProgress = spring({
    frame: frame - groupStartFrame,
    fps,
    config: {damping: 14, stiffness: 200, mass: 0.8},
  });

  // Gentle fade out at end
  const groupEndFrame = Math.round(activeGroup.end * fps);
  const groupDuration = groupEndFrame - groupStartFrame;
  const fadeOutFrames = Math.min(4, groupDuration / 3);
  const fadeOut = groupDuration > fadeOutFrames
    ? interpolate(
        frame,
        [groupEndFrame - fadeOutFrames, groupEndFrame],
        [1, 0],
        {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
      )
    : 1;

  const opacity = Math.min(enterProgress, fadeOut);

  // Slide up entrance
  const translateY = interpolate(enterProgress, [0, 1], [12, 0]);

  return (
    <div
      style={{
        position: 'absolute',
        top: captionTop,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity,
        transform: `translateY(${translateY}px)`,
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: fontSize * 0.22,
          maxWidth: '88%',
          flexWrap: 'wrap',
          justifyContent: 'center',
        }}
      >
        {activeGroup.words.map((word, i) => {
          const isActive = currentTime >= word.start && currentTime <= word.end;
          const isPast = currentTime > word.end;

          // Spring entrance per word
          const wordStartFrame = Math.round(word.start * fps);
          const wordSpring = spring({
            frame: frame - wordStartFrame,
            fps,
            config: {damping: 12, stiffness: 200, mass: 0.6},
          });

          // Scale: subtle 1.08x on active, 1.15x on highlight
          const baseScale = word.highlight && isActive ? 1.15 : isActive ? 1.08 : 1;
          const scale = interpolate(wordSpring, [0, 1], [0.9, baseScale]);

          // Color
          const wordColor = word.highlight
            ? brand.colors.caption_highlight
            : isActive || isPast
              ? brand.colors.caption_text
              : 'rgba(255, 255, 255, 0.45)';

          const weight = word.highlight
            ? 900
            : isActive
              ? brand.fonts.caption_weight
              : 600;

          return (
            <span
              key={i}
              style={{
                fontFamily: brand.fonts.caption,
                fontWeight: weight,
                fontSize,
                letterSpacing: '-0.02em',
                color: wordColor,
                transform: `scale(${scale})`,
                display: 'inline-block',
                // Stroke + shadow instead of background box
                WebkitTextStroke: '1.5px rgba(0,0,0,0.8)',
                textShadow: '0 4px 0 rgba(0,0,0,0.4), 0 0 8px rgba(0,0,0,0.3)',
                paintOrder: 'stroke fill',
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
