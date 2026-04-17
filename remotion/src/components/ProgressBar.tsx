import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {ProgressBarConfig} from '../types';

interface ProgressBarProps {
  config: ProgressBarConfig;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({config}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  if (!config.enabled) return null;

  const progress = frame / durationInFrames;

  return (
    <div
      style={{
        position: 'absolute',
        top: config.position === 'top' ? (config.top_offset_px || 230) : undefined,
        bottom: config.position === 'bottom' ? 0 : undefined,
        left: 0,
        right: 0,
        height: config.height_px,
        backgroundColor: config.bg_color,
        zIndex: 20,
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${progress * 100}%`,
          backgroundColor: config.color,
          borderRadius: config.position === 'top' ? '0 0 2px 0' : '0 2px 0 0',
        }}
      />
    </div>
  );
};
