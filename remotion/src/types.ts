export interface Word {
  word: string;
  start: number;
  end: number;
  highlight: boolean;
}

export interface CaptionGroup {
  text: string;
  words: Word[];
  start: number;
  end: number;
}

export interface SpeakerSegment {
  from_seconds: number;
  to_seconds: number;
  speaker: string;
  position: string; // 'left', 'right', 'center'
}

export interface ZoomMoment {
  at_seconds: number;
  target_speaker: string;
  hold_seconds: number;
  transition: string;
}

export interface BrandConfig {
  colors: {
    background: string;
    caption_text: string;
    caption_highlight: string;
    progress_bar: string;
    progress_bar_bg: string;
  };
  fonts: {
    caption: string;
    caption_weight: number;
    caption_size_px: number;
  };
  caption_position: string;
  caption_margin_bottom_px: number;
  progress_bar_height_px: number;
  logo_path: string | null;
  watermark: string | null;
}

export interface ProgressBarConfig {
  enabled: boolean;
  position: string;
  height_px: number;
  color: string;
  bg_color: string;
}

export interface RenderData {
  clip_number: number;
  source_video: string;
  duration_seconds: number;
  fps: number;
  total_frames: number;
  formats: string[];
  resolutions: Record<string, [number, number]>;
  hook: string;
  title: string;
  captions: {
    groups: CaptionGroup[];
    style: string;
    words_per_group: number;
  };
  speaker_tracking: {
    timeline: SpeakerSegment[];
    base_scale: number;
    transition_seconds: number;
  };
  zoom_emphasis: {
    moments: ZoomMoment[];
    zoom_scale: number;
  };
  brand: BrandConfig;
  progress_bar: ProgressBarConfig;
}
