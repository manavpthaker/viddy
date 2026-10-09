import React from 'react';
import {AbsoluteFill} from 'remotion';
import type {BrandConfig} from '../types';

export interface QuoteCardData {
  quote: string;
  attribution: string;
  brand: BrandConfig;
}

/**
 * A still quote card for carousels / reposts. Rendered via renderStill().
 * On-brand: black ground, DM Sans, sage accent. Designed at 1080x1350 (LinkedIn
 * portrait) but scales to whatever the composition dimensions are.
 */
export const QuoteCard: React.FC<QuoteCardData> = ({quote, attribution, brand}) => {
  const accent = brand.colors.caption_highlight;
  // Shrink type as the quote gets longer so it always fits comfortably.
  const len = (quote || '').length;
  const fontSize = len > 220 ? 52 : len > 140 ? 64 : len > 80 ? 78 : 92;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: brand.colors.background,
        padding: '120px 96px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      {/* Accent mark */}
      <div style={{width: 72, height: 6, backgroundColor: accent, borderRadius: 3}} />

      {/* Quote */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          justifyContent: 'center',
        }}
      >
        <p
          style={{
            fontFamily: brand.fonts.caption,
            fontWeight: 800,
            fontSize,
            lineHeight: 1.18,
            letterSpacing: '-0.02em',
            color: brand.colors.caption_text,
            margin: 0,
          }}
        >
          <span style={{color: accent}}>“</span>
          {quote}
          <span style={{color: accent}}>”</span>
        </p>
      </div>

      {/* Attribution */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <div style={{width: 40, height: 3, backgroundColor: accent}} />
        <span
          style={{
            fontFamily: brand.fonts.caption,
            fontWeight: 600,
            fontSize: 34,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.7)',
          }}
        >
          {attribution}
        </span>
      </div>
    </AbsoluteFill>
  );
};
