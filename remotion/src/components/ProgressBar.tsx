import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import type {ProgressBarConfig} from '../types';

interface ProgressBarProps {
  config: ProgressBarConfig;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({config}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, fps} = useVideoConfig();

  if (!config.enabled) return null;

  const progress = frame / durationInFrames;

  // Fade in during first 0.5s
  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        height: config.height_px,
        backgroundColor: config.bg_color,
        zIndex: 20,
        opacity,
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${progress * 100}%`,
          backgroundColor: config.color,
          borderRadius: '0 2px 2px 0',
          boxShadow: `0 0 6px ${config.color}50`,
        }}
      />
    </div>
  );
};
