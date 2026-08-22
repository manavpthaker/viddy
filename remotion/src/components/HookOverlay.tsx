import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import type {BrandConfig} from '../types';

interface HookOverlayProps {
  text: string;
  brand: BrandConfig;
  displayDuration?: number;
}

export const HookOverlay: React.FC<HookOverlayProps> = ({
  text,
  brand,
  displayDuration = 3,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const endFrame = displayDuration * fps;

  if (frame > endFrame) return null;

  // Container entrance: slide up + fade in
  const containerSpring = spring({
    frame,
    fps,
    config: {damping: 14, stiffness: 180, mass: 0.8},
  });

  const containerY = interpolate(containerSpring, [0, 1], [30, 0]);
  const containerOpacity = interpolate(containerSpring, [0, 1], [0, 1]);

  // Fade out at the end
  const fadeOut = interpolate(
    frame,
    [endFrame - fps * 0.4, endFrame],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  // Word-by-word typewriter reveal
  const words = text.split(' ');
  const revealDuration = Math.min(1.2, displayDuration * 0.4); // seconds for full reveal
  const perWordDelay = revealDuration / words.length;

  // Accent bar animation — grows in height
  const barHeight = interpolate(containerSpring, [0, 1], [0, 100]);

  return (
    <div
      style={{
        position: 'absolute',
        top: '8%',
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity: containerOpacity * fadeOut,
        transform: `translateY(${containerY}px)`,
        zIndex: 15,
      }}
    >
      <div
        style={{
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          padding: '20px 32px',
          borderRadius: 14,
          borderLeft: `5px solid ${brand.colors.caption_highlight}`,
          maxWidth: '85%',
          display: 'flex',
          alignItems: 'stretch',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Subtle gradient shimmer */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: `linear-gradient(135deg, transparent 40%, ${brand.colors.caption_highlight}08 50%, transparent 60%)`,
            backgroundSize: '200% 200%',
          }}
        />
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0 14px',
            position: 'relative',
          }}
        >
          {words.map((word, i) => {
            const wordDelay = i * perWordDelay;
            const wordFrame = frame - wordDelay * fps;

            const wordSpring = spring({
              frame: Math.max(0, wordFrame),
              fps,
              config: {damping: 12, stiffness: 220, mass: 0.5},
            });

            const wordOpacity = wordFrame < 0 ? 0 : interpolate(wordSpring, [0, 1], [0, 1]);
            const wordY = interpolate(wordSpring, [0, 1], [10, 0]);
            const wordScale = interpolate(wordSpring, [0, 1], [0.8, 1]);

            return (
              <span
                key={i}
                style={{
                  fontFamily: brand.fonts.caption,
                  fontWeight: 800,
                  fontSize: 52,
                  color: brand.colors.caption_text,
                  lineHeight: 1.35,
                  opacity: wordOpacity,
                  transform: `translateY(${wordY}px) scale(${wordScale})`,
                  display: 'inline-block',
                  textShadow: '0 2px 8px rgba(0,0,0,0.4)',
                }}
              >
                {word}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};
