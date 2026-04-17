import React from 'react';
import {AbsoluteFill, staticFile} from 'remotion';
import {AnimatedCaptions} from './components/AnimatedCaptions';
import {SpeakerZoom} from './components/SpeakerZoom';
import {ProgressBar} from './components/ProgressBar';
import {HookOverlay} from './components/HookOverlay';
import type {RenderData} from './types';

interface ClipCompositionProps {
  renderData: RenderData;
  format: 'vertical_9_16' | 'square_1_1';
}

export const ClipComposition: React.FC<ClipCompositionProps> = ({
  renderData,
  format,
}) => {
  const {brand, captions, speaker_tracking, zoom_emphasis, progress_bar, hook} = renderData;

  // Source video dimensions (from the cut clip, same as original)
  const sourceWidth = 1280;
  const sourceHeight = 720;

  // Resolve video source - use staticFile for filenames, pass URLs through
  const videoSrc = renderData.source_video.startsWith('http')
    ? renderData.source_video
    : staticFile(renderData.source_video);

  return (
    <AbsoluteFill style={{backgroundColor: brand.colors.background}}>
      {/* Layer 1: Video with continuous speaker tracking + zoom emphasis */}
      <SpeakerZoom
        src={videoSrc}
        speakerTimeline={speaker_tracking.timeline}
        zoomMoments={zoom_emphasis.moments}
        baseScale={speaker_tracking.base_scale}
        zoomScale={zoom_emphasis.zoom_scale}
        transitionSeconds={speaker_tracking.transition_seconds}
        format={format}
        sourceWidth={sourceWidth}
        sourceHeight={sourceHeight}
      />

      {/* Layer 2: Hook text overlay (first 3 seconds) */}
      {hook && <HookOverlay text={hook} brand={brand} displayDuration={3} />}

      {/* Layer 3: Animated captions */}
      <AnimatedCaptions
        groups={captions.groups}
        brand={brand}
        format={format}
      />

      {/* Layer 4: Progress bar */}
      <ProgressBar config={progress_bar} />
    </AbsoluteFill>
  );
};
