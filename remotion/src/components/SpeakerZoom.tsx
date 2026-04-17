import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, Easing, OffthreadVideo} from 'remotion';
import type {SpeakerSegment, ZoomMoment} from '../types';

interface SpeakerZoomProps {
  src: string;
  speakerTimeline: SpeakerSegment[];
  zoomMoments: ZoomMoment[];
  baseScale: number;
  zoomScale: number;
  transitionSeconds: number;
  format: 'vertical_9_16' | 'square_1_1';
  sourceWidth: number;
  sourceHeight: number;
}

export const SpeakerZoom: React.FC<SpeakerZoomProps> = ({
  src,
  speakerTimeline,
  zoomMoments,
  baseScale,
  zoomScale,
  transitionSeconds,
  format,
  sourceWidth,
  sourceHeight,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const currentTime = frame / fps;

  // Step 1: Find the active speaker and their position
  const getActiveSpeakerPosition = (): string => {
    for (const seg of speakerTimeline) {
      if (currentTime >= seg.from_seconds && currentTime <= seg.to_seconds) {
        return seg.position;
      }
    }
    return 'center';
  };

  // Step 2: Calculate the target translateX based on speaker position
  // Must use rendered video dimensions (not source) since translateX operates in rendered space
  const getTargetTranslateX = (position: string, renderedWidth: number): number => {
    // For vertical format, we need to crop into one side of the widescreen frame
    // Positive translateX shifts video right (showing left side)
    // Negative translateX shifts video left (showing right side)
    if (position === 'left') {
      return renderedWidth * 0.2;
    } else if (position === 'right') {
      return -renderedWidth * 0.2;
    }
    return 0; // center
  };

  // Step 3: Check if we're in a zoom emphasis moment
  const getZoomBoost = (): number => {
    for (const zm of zoomMoments) {
      const start = zm.at_seconds;
      const end = start + zm.hold_seconds;
      if (currentTime >= start && currentTime <= end) {
        // Ease in/out for the zoom emphasis
        const transIn = 0.3;
        const transOut = 0.3;
        let progress: number;
        if (currentTime < start + transIn) {
          progress = Easing.inOut(Easing.cubic)(
            (currentTime - start) / transIn
          );
        } else if (currentTime > end - transOut) {
          progress = Easing.inOut(Easing.cubic)(
            (end - currentTime) / transOut
          );
        } else {
          progress = 1;
        }
        return progress;
      }
    }
    return 0;
  };

  // Calculate how to fit the source video (needed before speaker tracking)
  const sourceAspect = sourceWidth / sourceHeight;
  const targetAspect = width / height;

  let videoWidth: number;
  let videoHeight: number;

  if (sourceAspect > targetAspect) {
    videoHeight = height;
    videoWidth = height * sourceAspect;
  } else {
    videoWidth = width;
    videoHeight = width / sourceAspect;
  }

  const activePosition = getActiveSpeakerPosition();
  const targetX = getTargetTranslateX(activePosition, videoWidth);
  const zoomBoost = getZoomBoost();

  // Step 4: Smooth transition between speaker positions
  // Find previous and next speaker segments for interpolation
  let smoothX = targetX;

  for (let i = 0; i < speakerTimeline.length; i++) {
    const seg = speakerTimeline[i];
    if (currentTime >= seg.from_seconds && currentTime <= seg.to_seconds) {
      // Check if we're in the transition zone at the start of this segment
      const transStart = seg.from_seconds;
      const transEnd = transStart + transitionSeconds;

      if (currentTime < transEnd && i > 0) {
        const prevPosition = speakerTimeline[i - 1].position;
        const prevX = getTargetTranslateX(prevPosition, videoWidth);
        const progress = Easing.inOut(Easing.cubic)(
          (currentTime - transStart) / transitionSeconds
        );
        smoothX = interpolate(progress, [0, 1], [prevX, targetX]);
      }
      break;
    }
  }

  // Step 5: Calculate final scale (base + zoom emphasis boost)
  const scale = baseScale + (zoomScale - baseScale) * zoomBoost;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        backgroundColor: '#000',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: `translate(-50%, -50%) scale(${scale}) translateX(${smoothX}px)`,
          transformOrigin: 'center center',
        }}
      >
        <OffthreadVideo
          src={src}
          style={{
            width: videoWidth,
            height: videoHeight,
          }}
        />
      </div>
    </div>
  );
};
