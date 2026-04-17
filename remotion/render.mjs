#!/usr/bin/env node
/**
 * Render script for Viddy clips.
 *
 * Supports two modes:
 *   Single clip:  node render.mjs <render_data.json> [options]
 *   Batch:        node render.mjs --batch <render_data_dir> [options]
 *
 * Options:
 *   --format vertical|square|both    Output format (default: vertical)
 *   --output-dir <dir>               Output directory
 *   --preview                        Render at 540p for fast preview
 *   --concurrency <n>                Parallel renders (default: 3)
 */

import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import {readFileSync, mkdirSync, copyFileSync, readdirSync, unlinkSync} from 'fs';
import {resolve, dirname, basename, join} from 'path';
import {fileURLToPath} from 'url';
import os from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseArgs(args) {
  const opts = {
    inputs: [],
    formats: ['vertical'],
    outputDir: null,
    preview: false,
    concurrency: 3,
    batch: null,
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--format' && args[i + 1]) {
      const fmt = args[i + 1];
      if (fmt === 'both') opts.formats = ['vertical', 'square'];
      else opts.formats = [fmt];
      i++;
    } else if (args[i] === '--output-dir' && args[i + 1]) {
      opts.outputDir = resolve(args[i + 1]);
      i++;
    } else if (args[i] === '--preview') {
      opts.preview = true;
    } else if (args[i] === '--concurrency' && args[i + 1]) {
      opts.concurrency = parseInt(args[i + 1], 10);
      i++;
    } else if (args[i] === '--batch' && args[i + 1]) {
      opts.batch = resolve(args[i + 1]);
      i++;
    } else if (!args[i].startsWith('--')) {
      opts.inputs.push(resolve(args[i]));
    }
  }

  return opts;
}

async function renderClip({renderData, bundleLocation, publicDir, format, outputDir, preview}) {
  const compositionId = format === 'vertical' ? 'ClipVertical' : 'ClipSquare';
  const formatKey = format === 'vertical' ? 'vertical_9_16' : 'square_1_1';
  const clipNum = String(renderData.clip_number).padStart(2, '0');

  const videoFilename = `clip_${clipNum}.mp4`;

  const inputProps = {
    renderData: {
      ...renderData,
      source_video: videoFilename,
    },
    format: formatKey,
  };

  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: compositionId,
    inputProps,
  });

  composition.durationInFrames = renderData.total_frames;
  composition.fps = renderData.fps;

  // Preview mode: scale down resolution
  if (preview) {
    const scale = 0.5;
    composition.width = Math.round(composition.width * scale);
    composition.height = Math.round(composition.height * scale);
  }

  const suffix = preview ? `_${format}_preview` : `_${format}`;
  const outputFile = resolve(outputDir, `clip_${clipNum}${suffix}.mp4`);

  const startTime = Date.now();
  console.log(`  [clip ${clipNum}] Rendering ${composition.width}x${composition.height} ${format}...`);

  await renderMedia({
    composition,
    serveUrl: bundleLocation,
    codec: 'h264',
    outputLocation: outputFile,
    inputProps,
    // Use fewer threads per render when running concurrent
    concurrency: 2,
    onProgress: ({progress}) => {
      const pct = Math.round(progress * 100);
      if (pct % 25 === 0) {
        process.stdout.write(`\r  [clip ${clipNum}] ${pct}%`);
      }
    },
  });

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\r  [clip ${clipNum}] Done in ${elapsed}s → ${outputFile}`);

  return outputFile;
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error(`Usage:
  node render.mjs <render_data.json> [options]
  node render.mjs --batch <render_data_dir> [options]

Options:
  --format vertical|square|both    Output format (default: vertical)
  --output-dir <dir>               Output directory
  --preview                        Render at 540p for fast review (~4x faster)
  --concurrency <n>                Parallel renders (default: 3)`);
    process.exit(1);
  }

  const opts = parseArgs(args);

  // Collect all render data files
  let renderDataPaths = [...opts.inputs];

  if (opts.batch) {
    const files = readdirSync(opts.batch)
      .filter(f => f.endsWith('.json'))
      .sort()
      .map(f => join(opts.batch, f));
    renderDataPaths = files;
  }

  if (renderDataPaths.length === 0) {
    console.error('No render data files found.');
    process.exit(1);
  }

  // Load all render data
  const allRenderData = renderDataPaths.map(p => ({
    path: p,
    data: JSON.parse(readFileSync(p, 'utf-8')),
  }));

  // Output dir
  const outputDir = opts.outputDir || resolve(dirname(renderDataPaths[0]), '..', '..', '..', 'output');
  mkdirSync(outputDir, {recursive: true});

  const publicDir = resolve(__dirname, 'public');
  mkdirSync(publicDir, {recursive: true});

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  VIDDY RENDER`);
  console.log(`${'='.repeat(60)}`);
  console.log(`  Clips: ${allRenderData.length}`);
  console.log(`  Formats: ${opts.formats.join(', ')}`);
  console.log(`  Resolution: ${opts.preview ? '540p (preview)' : '1080p (full)'}`);
  console.log(`  Concurrency: ${opts.concurrency}`);
  console.log(`  Output: ${outputDir}/`);
  console.log(`${'='.repeat(60)}\n`);

  // Copy ALL clip videos to public/ BEFORE bundling
  // Remotion bundles the public dir at bundle time, so files must exist then
  console.log('Copying clip videos to public/...');
  for (const {data} of allRenderData) {
    const clipNum = String(data.clip_number).padStart(2, '0');
    const videoFilename = `clip_${clipNum}.mp4`;
    const dest = resolve(publicDir, videoFilename);
    copyFileSync(data.source_video, dest);
  }
  console.log(`  ${allRenderData.length} clips copied\n`);

  // Bundle once — this is the expensive webpack step
  const bundleStart = Date.now();
  console.log('Bundling Remotion project (once)...');
  const bundleLocation = await bundle({
    entryPoint: resolve(__dirname, 'src/index.ts'),
    webpackOverride: (config) => config,
    publicDir,
  });
  const bundleTime = ((Date.now() - bundleStart) / 1000).toFixed(1);
  console.log(`Bundle complete in ${bundleTime}s\n`);

  // Build render jobs
  const jobs = [];
  for (const {data} of allRenderData) {
    for (const format of opts.formats) {
      jobs.push({renderData: data, format});
    }
  }

  // Execute with concurrency limit
  const totalStart = Date.now();
  const results = [];
  const concurrency = Math.min(opts.concurrency, jobs.length);

  // Simple concurrency pool
  let jobIndex = 0;
  const workers = Array.from({length: concurrency}, async () => {
    while (jobIndex < jobs.length) {
      const idx = jobIndex++;
      const job = jobs[idx];
      try {
        const output = await renderClip({
          ...job,
          bundleLocation,
          publicDir,
          outputDir,
          preview: opts.preview,
        });
        results.push({clip: job.renderData.clip_number, format: job.format, output, success: true});
      } catch (err) {
        console.error(`  [clip ${job.renderData.clip_number}] FAILED: ${err.message}`);
        results.push({clip: job.renderData.clip_number, format: job.format, success: false, error: err.message});
      }
    }
  });

  await Promise.all(workers);

  // Clean up public dir
  for (const {data} of allRenderData) {
    const clipNum = String(data.clip_number).padStart(2, '0');
    const videoFilename = `clip_${clipNum}.mp4`;
    try { unlinkSync(resolve(publicDir, videoFilename)); } catch {}
  }

  const totalTime = ((Date.now() - totalStart) / 1000).toFixed(1);
  const succeeded = results.filter(r => r.success).length;

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  COMPLETE: ${succeeded}/${jobs.length} renders in ${totalTime}s`);
  console.log(`  Output: ${outputDir}/`);
  console.log(`${'='.repeat(60)}\n`);
}

main().catch((err) => {
  console.error('Render failed:', err);
  process.exit(1);
});
