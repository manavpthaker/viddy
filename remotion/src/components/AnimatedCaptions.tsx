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

  const activeGroup = groups.find(
    (g) => currentTime >= g.start && currentTime <= g.end
  );

  if (!activeGroup) return null;

  const baseFontSize = brand.fonts.caption_size_px;
  const fontSize = format === 'square_1_1' ? baseFontSize * 0.75 : baseFontSize * 0.85;

  const captionTop = format === 'square_1_1'
    ? Math.round(height * 0.70)
    : Math.round(height * 0.60);

  const groupStartFrame = Math.round(activeGroup.start * fps);
  const groupEndFrame = Math.round(activeGroup.end * fps);
  const groupDuration = groupEndFrame - groupStartFrame;

  // Quick fade out
  const fadeOutFrames = Math.min(3, groupDuration / 4);
  const fadeOut = groupDuration > fadeOutFrames
    ? interpolate(
        frame,
        [groupEndFrame - fadeOutFrames, groupEndFrame],
        [1, 0],
        {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
      )
    : 1;

  return (
    <div
      style={{
        position: 'absolute',
        top: captionTop,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity: fadeOut,
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: fontSize * 0.2,
          maxWidth: '85%',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'baseline',
        }}
      >
        {activeGroup.words.map((word, i) => {
          const isActive = currentTime >= word.start;
          const isCurrentlySpoken = currentTime >= word.start && currentTime <= word.end;

          const wordStartFrame = Math.round(word.start * fps);
          const frameSinceWord = frame - wordStartFrame;

          // Snappy entrance — fast, no bounce
          const popSpring = spring({
            frame: frameSinceWord,
            fps,
            config: {damping: 22, stiffness: 300, mass: 0.4},
          });

          // Clean scale: appear at 0.85 → 1.0, no overshoot
          const scale = isActive
            ? interpolate(popSpring, [0, 1], [0.85, 1.0])
            : 0;

          // Minimal Y shift — just 6px, fast settle
          const translateY = interpolate(popSpring, [0, 1], [6, 0]);

          const opacity = isActive
            ? interpolate(popSpring, [0, 0.2], [0, 1], {extrapolateRight: 'clamp'})
            : 0;

          // Active word: full white. Past: slightly dimmed. Inactive: hidden
          const wordColor = isCurrentlySpoken
            ? '#FFFFFF'
            : isActive
              ? 'rgba(255, 255, 255, 0.7)'
              : 'rgba(255, 255, 255, 0.3)';

          // Spoken word gets a subtle underline accent via border
          const weight = isCurrentlySpoken ? 700 : 600;

          return (
            <span
              key={i}
              style={{
                fontFamily: brand.fonts.caption,
                fontWeight: weight,
                fontSize,
                letterSpacing: '-0.01em',
                color: wordColor,
                transform: `scale(${scale}) translateY(${isActive ? translateY : 0}px)`,
                opacity: isActive ? opacity : 0,
                display: 'inline-block',
                WebkitTextStroke: '4px #000000',
                textShadow: '0 2px 0 rgba(0,0,0,0.5), 0 0 8px rgba(0,0,0,0.3)',
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
