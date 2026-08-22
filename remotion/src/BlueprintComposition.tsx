import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

/**
 * Blueprint — 16:9 long-form composition.
 *
 * Sequences per-section VO audio and renders each beat's asset
 * (slide / chart / logo / broll placeholder) with word-timed captions
 * at the bottom. Brand theming comes from config/brand.json via the
 * render data payload.
 */

type Word = {word: string; start: number; end: number; highlight: boolean};
type CaptionGroup = {text: string; words: Word[]; start: number; end: number};

type AssetSpec = {
  type: 'slide' | 'chart' | 'broll' | 'screen_rec' | 'logo';
  title?: string;
  bullets?: string[];
  chart_type?: 'bar' | 'line' | 'waterfall';
  series?: {label: string; value: number}[];
  unit?: string;
  source?: string;
  search_query?: string;
  company?: string;
  caption?: string;
  tool?: string;
  action?: string;
};

type Beat = {beat: number; start: number; end: number; asset: AssetSpec};
type Section = {id: string; start: number; duration: number; audio: string; beats: Beat[]};

export type BlueprintRenderData = {
  slug: string;
  title: string;
  duration_seconds: number;
  fps: number;
  total_frames: number;
  resolution: [number, number];
  sections: Section[];
  captions: {groups: CaptionGroup[]; style: string; words_per_group: number};
  brand: any;
};

const FadeIn: React.FC<{children: React.ReactNode; startFrame: number}> = ({children, startFrame}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame - startFrame, [0, 12], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const translateY = interpolate(frame - startFrame, [0, 12], [16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return <div style={{opacity, transform: `translateY(${translateY}px)`}}>{children}</div>;
};

const SlideAsset: React.FC<{spec: AssetSpec; brand: any; startFrame: number}> = ({spec, brand, startFrame}) => (
  <FadeIn startFrame={startFrame}>
    <div style={{padding: '120px 160px'}}>
      <h1
        style={{
          fontFamily: brand.fonts.caption,
          fontWeight: 800,
          fontSize: 72,
          color: brand.colors.caption_text,
          marginBottom: 48,
          lineHeight: 1.15,
        }}
      >
        {spec.title}
      </h1>
      {(spec.bullets || []).map((b, i) => (
        <div
          key={i}
          style={{
            fontFamily: brand.fonts.caption,
            fontWeight: 500,
            fontSize: 44,
            color: brand.colors.caption_text,
            opacity: 0.9,
            marginBottom: 28,
            display: 'flex',
            gap: 24,
          }}
        >
          <span style={{color: brand.colors.caption_highlight}}>—</span>
          {b}
        </div>
      ))}
    </div>
  </FadeIn>
);

const ChartAsset: React.FC<{spec: AssetSpec; brand: any; startFrame: number}> = ({spec, brand, startFrame}) => {
  const frame = useCurrentFrame();
  const series = spec.series || [];
  const max = Math.max(...series.map((s) => s.value), 1);
  const growth = interpolate(frame - startFrame, [6, 40], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <FadeIn startFrame={startFrame}>
      <div style={{padding: '100px 160px'}}>
        <h2
          style={{
            fontFamily: brand.fonts.caption,
            fontWeight: 800,
            fontSize: 52,
            color: brand.colors.caption_text,
            marginBottom: 64,
          }}
        >
          {spec.title}
        </h2>
        <div style={{display: 'flex', alignItems: 'flex-end', gap: 48, height: 480}}>
          {series.map((s, i) => (
            <div key={i} style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%'}}>
              <div
                style={{
                  fontFamily: brand.fonts.caption,
                  fontSize: 34,
                  fontWeight: 800,
                  color: brand.colors.caption_highlight,
                  textAlign: 'center',
                  marginBottom: 12,
                }}
              >
                {spec.unit === '$' ? '$' : ''}
                {Math.round(s.value * growth).toLocaleString()}
                {spec.unit && spec.unit !== '$' ? spec.unit : ''}
              </div>
              <div
                style={{
                  height: `${(s.value / max) * 100 * growth}%`,
                  background: brand.colors.caption_highlight,
                  borderRadius: 8,
                  minHeight: 4,
                }}
              />
              <div
                style={{
                  fontFamily: brand.fonts.caption,
                  fontSize: 28,
                  color: brand.colors.caption_text,
                  opacity: 0.7,
                  textAlign: 'center',
                  marginTop: 16,
                }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>
        {spec.source && (
          <div style={{fontFamily: brand.fonts.caption, fontSize: 22, opacity: 0.5, color: brand.colors.caption_text, marginTop: 40}}>
            Source: {spec.source}
          </div>
        )}
      </div>
    </FadeIn>
  );
};

const FallbackAsset: React.FC<{spec: AssetSpec; brand: any; startFrame: number}> = ({spec, brand, startFrame}) => (
  <FadeIn startFrame={startFrame}>
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <div
        style={{
          fontFamily: brand.fonts.caption,
          fontWeight: 800,
          fontSize: 56,
          color: brand.colors.caption_text,
          opacity: 0.85,
          maxWidth: 1200,
          textAlign: 'center',
        }}
      >
        {spec.type === 'logo'
          ? spec.company
          : spec.type === 'broll'
            ? `[B-ROLL: ${spec.search_query}]`
            : `[SCREEN REC: ${spec.tool} — ${spec.action}]`}
      </div>
      {spec.caption && (
        <div style={{fontFamily: brand.fonts.caption, fontSize: 32, color: brand.colors.caption_highlight, marginTop: 24}}>
          {spec.caption}
        </div>
      )}
    </AbsoluteFill>
  </FadeIn>
);

const Captions: React.FC<{groups: CaptionGroup[]; brand: any}> = ({groups, brand}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const active = groups.find((g) => t >= g.start && t <= g.end);
  if (!active) return null;
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 80,
        width: '100%',
        textAlign: 'center',
        fontFamily: brand.fonts.caption,
        fontWeight: brand.fonts.caption_weight,
        fontSize: 42,
      }}
    >
      {active.words.map((w, i) => (
        <span
          key={i}
          style={{
            color: t >= w.start && w.highlight ? brand.colors.caption_highlight : brand.colors.caption_text,
            opacity: t >= w.start ? 1 : 0.45,
            marginRight: 14,
          }}
        >
          {w.word}
        </span>
      ))}
    </div>
  );
};

export const BlueprintComposition: React.FC<{renderData: BlueprintRenderData}> = ({renderData}) => {
  const {fps} = useVideoConfig();
  const {sections, captions, brand} = renderData;

  return (
    <AbsoluteFill style={{backgroundColor: brand.colors.background}}>
      {sections.map((section) => (
        <Sequence
          key={section.id}
          from={Math.round(section.start * fps)}
          durationInFrames={Math.max(1, Math.round(section.duration * fps))}
        >
          <Audio src={staticFile(section.audio)} />
        </Sequence>
      ))}
      {sections.flatMap((section) =>
        section.beats.map((beat) => {
          const from = Math.round(beat.start * fps);
          const dur = Math.max(1, Math.round((beat.end - beat.start) * fps));
          const spec = beat.asset;
          return (
            <Sequence key={`${section.id}-${beat.beat}`} from={from} durationInFrames={dur}>
              {spec.type === 'slide' ? (
                <SlideAsset spec={spec} brand={brand} startFrame={0} />
              ) : spec.type === 'chart' ? (
                <ChartAsset spec={spec} brand={brand} startFrame={0} />
              ) : (
                <FallbackAsset spec={spec} brand={brand} startFrame={0} />
              )}
            </Sequence>
          );
        }),
      )}
      <Captions groups={captions.groups} brand={brand} />
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          height: 4,
          width: '100%',
          background: brand.colors.progress_bar_bg,
        }}
      >
        <ProgressFill color={brand.colors.progress_bar} total={renderData.total_frames} />
      </div>
    </AbsoluteFill>
  );
};

const ProgressFill: React.FC<{color: string; total: number}> = ({color, total}) => {
  const frame = useCurrentFrame();
  return <div style={{height: '100%', width: `${(frame / total) * 100}%`, background: color}} />;
};
