import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, OffthreadVideo, staticFile} from 'remotion';
import type {BRollSegment} from '../types';

interface BRollOverlayProps {
  segments: BRollSegment[];
  format: 'vertical_9_16' | 'square_1_1';
}

export const BRollOverlay: React.FC<BRollOverlayProps> = ({segments, format}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const currentTime = frame / fps;

  return (
    <>
      {segments.map((segment) => {
        const {from_seconds, to_seconds, transition_seconds, source_video, source_start_seconds} = segment;
        const transition = transition_seconds || 0.3;

        // Skip if not in range (with transition padding)
        if (currentTime < from_seconds - transition || currentTime > to_seconds + transition) {
          return null;
        }

        // Crossfade opacity
        const opacity = interpolate(
          currentTime,
          [from_seconds, from_seconds + transition, to_seconds - transition, to_seconds],
          [0, 1, 1, 0],
          {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
        );

        if (opacity <= 0) return null;

        // Resolve video source
        const videoSrc = source_video.startsWith('http')
          ? source_video
          : staticFile(source_video);

        // Calculate startFrom: how many frames into the B-roll to start
        const startFromFrames = Math.round((source_start_seconds || 0) * fps);

        // Scale B-roll to cover the output frame (center-crop)
        // Stock video is typically 16:9 landscape, output is 9:16 or 1:1
        const sourceAspect = 16 / 9;
        const outputAspect = width / height;
        let scale: number;
        if (outputAspect > sourceAspect) {
          scale = width / (height * sourceAspect) * height / height;
        } else {
          scale = height / (width / sourceAspect) * width / width;
        }
        // Simpler: just ensure cover
        const coverScale = Math.max(width / (height * sourceAspect), 1) * (height / height);
        const finalScale = Math.max(coverScale, height / (width / sourceAspect));

        return (
          <div
            key={segment.id}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              opacity,
              overflow: 'hidden',
              zIndex: 5,
            }}
          >
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: `translate(-50%, -50%)`,
                width: '100%',
                height: '100%',
              }}
            >
              <OffthreadVideo
                src={videoSrc}
                startFrom={startFromFrames}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  objectPosition: 'center',
                }}
                muted
              />
            </div>
          </div>
        );
      })}
    </>
  );
};
