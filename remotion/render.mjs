#!/usr/bin/env node
/**
 * Render script for Viddy clips.
 *
 * Usage:
 *   node render.mjs <render_data.json> [--format vertical|square|both] [--output-dir <dir>]
 *
 * Reads a render data JSON file produced by prepare_render.py,
 * then renders the clip using Remotion.
 */

import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import {readFileSync, mkdirSync, existsSync, copyFileSync} from 'fs';
import {resolve, dirname, basename} from 'path';
import {fileURLToPath} from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error('Usage: node render.mjs <render_data.json> [--format vertical|square|both] [--output-dir <dir>]');
    process.exit(1);
  }

  const renderDataPath = resolve(args[0]);
  const renderData = JSON.parse(readFileSync(renderDataPath, 'utf-8'));

  // Parse options
  let formats = ['vertical'];
  let outputDir = resolve(dirname(renderDataPath), '..', '..', '..', 'output');

  for (let i = 1; i < args.length; i++) {
    if (args[i] === '--format' && args[i + 1]) {
      const fmt = args[i + 1];
      if (fmt === 'both') formats = ['vertical', 'square'];
      else formats = [fmt];
      i++;
    } else if (args[i] === '--output-dir' && args[i + 1]) {
      outputDir = resolve(args[i + 1]);
      i++;
    }
  }

  mkdirSync(outputDir, {recursive: true});

  // Copy source video to public/ so Remotion can serve it as a static file
  const publicDir = resolve(__dirname, 'public');
  mkdirSync(publicDir, {recursive: true});
  const videoFilename = `clip_${String(renderData.clip_number).padStart(2, '0')}.mp4`;
  const publicVideoPath = resolve(publicDir, videoFilename);
  console.log(`Copying clip to public/${videoFilename}...`);
  copyFileSync(renderData.source_video, publicVideoPath);

  console.log(`Bundling Remotion project...`);
  const bundleLocation = await bundle({
    entryPoint: resolve(__dirname, 'src/index.ts'),
    webpackOverride: (config) => config,
    publicDir,
  });

  for (const fmt of formats) {
    const compositionId = fmt === 'vertical' ? 'ClipVertical' : 'ClipSquare';
    const formatKey = fmt === 'vertical' ? 'vertical_9_16' : 'square_1_1';

    const inputProps = {
      renderData: {
        ...renderData,
        // Use staticFile reference (served from public/)
        source_video: videoFilename,
      },
      format: formatKey,
    };

    console.log(`\nSelecting composition: ${compositionId}`);
    const composition = await selectComposition({
      serveUrl: bundleLocation,
      id: compositionId,
      inputProps,
    });

    // Override duration from render data
    composition.durationInFrames = renderData.total_frames;
    composition.fps = renderData.fps;

    const outputFile = resolve(
      outputDir,
      `clip_${String(renderData.clip_number).padStart(2, '0')}_${fmt}.mp4`
    );

    console.log(`Rendering ${compositionId} → ${outputFile}`);
    console.log(`  Duration: ${renderData.duration_seconds}s, ${renderData.total_frames} frames @ ${renderData.fps}fps`);
    console.log(`  Format: ${composition.width}x${composition.height}`);

    await renderMedia({
      composition,
      serveUrl: bundleLocation,
      codec: 'h264',
      outputLocation: outputFile,
      inputProps,
      onProgress: ({progress}) => {
        if (Math.round(progress * 100) % 10 === 0) {
          process.stdout.write(`\r  Progress: ${Math.round(progress * 100)}%`);
        }
      },
    });

    console.log(`\n  Done: ${outputFile}`);
  }

  console.log(`\nAll renders complete. Output: ${outputDir}/`);
}

main().catch((err) => {
  console.error('Render failed:', err);
  process.exit(1);
});
