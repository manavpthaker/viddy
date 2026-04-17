#!/usr/bin/env node
/**
 * Render preview stills at key moments for fast visual QA.
 *
 * Instead of waiting 1-2 min for a full video render, this outputs
 * a few JPEG frames so you can check captions, zoom, safe zones.
 *
 * Usage:
 *   node preview-stills.mjs <render_data.json> [--frames 15,45,90,180]
 *   node preview-stills.mjs <render_data.json> --output-dir ./previews
 */

import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import {readFileSync, mkdirSync, copyFileSync} from 'fs';
import {resolve, dirname} from 'path';
import {fileURLToPath} from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error('Usage: node preview-stills.mjs <render_data.json> [--frames 15,45,90,180]');
    process.exit(1);
  }

  const renderDataPath = resolve(args[0]);
  const renderData = JSON.parse(readFileSync(renderDataPath, 'utf-8'));
  const clipNum = String(renderData.clip_number).padStart(2, '0');

  // Parse options
  let frameNumbers = [15, 45, 90, Math.round(renderData.total_frames / 2), renderData.total_frames - 30];
  let outputDir = resolve(dirname(renderDataPath), '..', 'previews');

  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--frames' && args[i + 1]) {
      frameNumbers = args[i + 1].split(',').map(Number);
      i++;
    } else if (args[i] === '--output-dir' && args[i + 1]) {
      outputDir = resolve(args[i + 1]);
      i++;
    }
  }

  // Filter out invalid frame numbers
  frameNumbers = frameNumbers.filter(f => f >= 0 && f < renderData.total_frames);

  mkdirSync(outputDir, {recursive: true});

  // Copy video to public
  const publicDir = resolve(__dirname, 'public');
  mkdirSync(publicDir, {recursive: true});
  const videoFilename = `clip_${clipNum}.mp4`;
  copyFileSync(renderData.source_video, resolve(publicDir, videoFilename));

  console.log(`Bundling...`);
  const bundleLocation = await bundle({
    entryPoint: resolve(__dirname, 'src/index.ts'),
    webpackOverride: (config) => config,
    publicDir,
  });

  const inputProps = {
    renderData: {...renderData, source_video: videoFilename},
    format: 'vertical_9_16',
  };

  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: 'ClipVertical',
    inputProps,
  });

  composition.durationInFrames = renderData.total_frames;
  composition.fps = renderData.fps;

  console.log(`\nRendering ${frameNumbers.length} stills for clip ${clipNum}...`);

  for (const frame of frameNumbers) {
    const timeSeconds = (frame / renderData.fps).toFixed(1);
    const outputFile = resolve(outputDir, `clip_${clipNum}_frame_${frame}_${timeSeconds}s.jpeg`);

    await renderStill({
      composition,
      serveUrl: bundleLocation,
      output: outputFile,
      inputProps,
      frame,
      imageFormat: 'jpeg',
      jpegQuality: 85,
    });

    console.log(`  Frame ${frame} (${timeSeconds}s) → ${outputFile}`);
  }

  // Clean up
  try {
    const {unlinkSync} = await import('fs');
    unlinkSync(resolve(publicDir, videoFilename));
  } catch {}

  console.log(`\nDone. Previews in: ${outputDir}/`);
}

main().catch((err) => {
  console.error('Preview failed:', err);
  process.exit(1);
});
