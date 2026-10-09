import React from 'react';
import {AbsoluteFill, staticFile} from 'remotion';
import {AnimatedCaptions} from './components/AnimatedCaptions';
import {SpeakerZoom} from './components/SpeakerZoom';
import {ScreenSpeakerComposite} from './components/ScreenSpeakerComposite';
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
  const {brand, captions, speaker_tracking, zoom_emphasis, progress_bar, hook, reframe} = renderData;

  // Real source dimensions measured during tracking; fall back to 1920x1080.
  const sourceWidth = renderData.source_dimensions?.width ?? 1920;
  const sourceHeight = renderData.source_dimensions?.height ?? 1080;

  // Resolve video source - use staticFile for filenames, pass URLs through
  const videoSrc = renderData.source_video.startsWith('http')
    ? renderData.source_video
    : staticFile(renderData.source_video);

  // Composite (screen + speaker) needs a reframe track to crop the speaker.
  const useComposite = renderData.layout === 'composite' && reframe && reframe.keyframes?.length;

  return (
    <AbsoluteFill style={{backgroundColor: brand.colors.background}}>
      {/* Layer 1: Video — composite (screen+speaker) or single-speaker reframe */}
      {useComposite ? (
        <ScreenSpeakerComposite src={videoSrc} reframe={reframe!} brand={brand} />
      ) : (
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
          reframe={reframe}
        />
      )}

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
