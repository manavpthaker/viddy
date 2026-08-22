import React from 'react';
import {Composition, getInputProps} from 'remotion';
import {ClipComposition} from './ClipComposition';
import {BlueprintComposition, type BlueprintRenderData} from './BlueprintComposition';
import type {RenderData} from './types';

// Minimal default for Blueprint studio preview (real props come via --props)
const defaultBlueprintData: BlueprintRenderData = {
  slug: 'preview',
  title: 'Blueprint Preview',
  duration_seconds: 10,
  fps: 30,
  total_frames: 300,
  resolution: [1920, 1080],
  sections: [
    {
      id: 'hook',
      start: 0,
      duration: 10,
      audio: '',
      beats: [
        {
          beat: 1,
          start: 0,
          end: 10,
          asset: {type: 'slide', title: 'This is a preview slide', bullets: ['Point one', 'Point two', 'Point three']},
        },
      ],
    },
  ],
  captions: {groups: [], style: 'highlight', words_per_group: 4},
  brand: {
    colors: {
      background: '#000000',
      caption_text: '#FFFFFF',
      caption_highlight: '#7B9E87',
      progress_bar: '#7B9E87',
      progress_bar_bg: 'rgba(255,255,255,0.1)',
    },
    fonts: {caption: 'DM Sans', caption_weight: 800, caption_size_px: 64},
  },
};

// Default render data for Remotion Studio preview
const defaultRenderData: RenderData = {
  clip_number: 1,
  source_video: '',
  duration_seconds: 10,
  fps: 30,
  total_frames: 300,
  formats: ['vertical_9_16'],
  resolutions: {
    vertical_9_16: [1080, 1920],
    square_1_1: [1080, 1080],
  },
  hook: 'Preview hook text here',
  title: 'Preview Clip',
  captions: {
    groups: [
      {
        text: 'This is a',
        words: [
          {word: 'This', start: 0.5, end: 0.8, highlight: false},
          {word: 'is', start: 0.8, end: 1.0, highlight: false},
          {word: 'a', start: 1.0, end: 1.2, highlight: false},
        ],
        start: 0.5,
        end: 1.2,
      },
      {
        text: 'preview clip',
        words: [
          {word: 'preview', start: 1.3, end: 1.7, highlight: true},
          {word: 'clip', start: 1.7, end: 2.0, highlight: false},
        ],
        start: 1.3,
        end: 2.0,
      },
    ],
    style: 'highlight',
    words_per_group: 3,
  },
  speaker_tracking: {
    timeline: [],
    base_scale: 1.35,
    transition_seconds: 0.4,
  },
  zoom_emphasis: {
    moments: [],
    zoom_scale: 1.06,
  },
  brand: {
    colors: {
      background: '#000000',
      caption_text: '#FFFFFF',
      caption_highlight: '#7B9E87',
      progress_bar: '#7B9E87',
      progress_bar_bg: 'rgba(255,255,255,0.15)',
    },
    fonts: {
      caption: 'DM Sans',
      caption_weight: 800,
      caption_size_px: 64,
    },
    caption_position: 'bottom_center',
    caption_margin_bottom_px: 180,
    progress_bar_height_px: 4,
    logo_path: null,
    watermark: null,
  },
  progress_bar: {
    enabled: true,
    position: 'top',
    height_px: 4,
    color: '#7B9E87',
    bg_color: 'rgba(255,255,255,0.15)',
    top_offset_px: 230,
  },
};

interface ClipProps {
  renderData: RenderData;
  format: 'vertical_9_16' | 'square_1_1';
}

const calculateClipMetadata: (props: {props: ClipProps}) => Promise<{
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
}> = async ({props}) => {
  const {renderData, format} = props;
  const resolution = renderData.resolutions[format] || (format === 'square_1_1' ? [1080, 1080] : [1080, 1920]);
  return {
    durationInFrames: renderData.total_frames || Math.ceil(renderData.duration_seconds * renderData.fps),
    fps: renderData.fps,
    width: resolution[0],
    height: resolution[1],
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ClipVertical"
        component={ClipComposition}
        calculateMetadata={calculateClipMetadata}
        defaultProps={{
          renderData: defaultRenderData,
          format: 'vertical_9_16' as const,
        }}
      />
      <Composition
        id="ClipSquare"
        component={ClipComposition}
        calculateMetadata={calculateClipMetadata}
        defaultProps={{
          renderData: defaultRenderData,
          format: 'square_1_1' as const,
        }}
      />
      <Composition
        id="Blueprint"
        component={BlueprintComposition}
        calculateMetadata={async ({props}) => ({
          durationInFrames:
            props.renderData.total_frames || Math.ceil(props.renderData.duration_seconds * props.renderData.fps),
          fps: props.renderData.fps,
          width: props.renderData.resolution?.[0] ?? 1920,
          height: props.renderData.resolution?.[1] ?? 1080,
        })}
        defaultProps={{renderData: defaultBlueprintData}}
      />
    </>
  );
};
