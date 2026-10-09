#!/usr/bin/env node
/**
 * Render quote-card stills for shareability packs.
 *
 * Reads the social/clip_XX.json files written by scripts/package_clips.py and
 * renders one on-brand quote-card PNG per clip via Remotion's renderStill.
 *
 * Usage:
 *   node render_stills.mjs --social-dir <dir> [--output-dir <dir>] [--brand <brand.json>]
 */

import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import {readFileSync, readdirSync, mkdirSync} from 'fs';
import {resolve, dirname, join} from 'path';
import {fileURLToPath} from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function parseArgs(args) {
  const opts = {socialDir: null, outputDir: null, brand: null};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--social-dir' && args[i + 1]) opts.socialDir = resolve(args[++i]);
    else if (args[i] === '--output-dir' && args[i + 1]) opts.outputDir = resolve(args[++i]);
    else if (args[i] === '--brand' && args[i + 1]) opts.brand = resolve(args[++i]);
  }
  return opts;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.socialDir) {
    console.error('Usage: node render_stills.mjs --social-dir <dir> [--output-dir <dir>] [--brand <brand.json>]');
    process.exit(1);
  }

  const outputDir = opts.outputDir || opts.socialDir;
  mkdirSync(outputDir, {recursive: true});

  const brandPath = opts.brand || resolve(__dirname, '..', 'config', 'brand.json');
  const brand = JSON.parse(readFileSync(brandPath, 'utf-8'));

  const packs = readdirSync(opts.socialDir)
    .filter((f) => /^clip_\d+\.json$/.test(f))
    .sort()
    .map((f) => JSON.parse(readFileSync(join(opts.socialDir, f), 'utf-8')))
    .filter((p) => p.quote_card && p.quote_card.quote);

  if (packs.length === 0) {
    console.log('No quote cards to render.');
    return;
  }

  console.log(`Rendering ${packs.length} quote card(s)...`);
  const bundleLocation = await bundle({
    entryPoint: resolve(__dirname, 'src/index.ts'),
    webpackOverride: (c) => c,
  });

  for (const p of packs) {
    const qc = p.quote_card;
    const inputProps = {
      quote: qc.quote,
      attribution: qc.attribution || p.title || '',
      brand,
    };
    const composition = await selectComposition({
      serveUrl: bundleLocation,
      id: 'QuoteCard',
      inputProps,
    });
    const num = String(p.clip_number).padStart(2, '0');
    const outFile = resolve(outputDir, `quote_${num}.png`);
    await renderStill({
      composition,
      serveUrl: bundleLocation,
      output: outFile,
      inputProps,
      imageFormat: 'png',
    });
    console.log(`  quote_${num}.png`);
  }

  console.log(`\nQuote cards saved to ${outputDir}/`);
}

main().catch((err) => {
  console.error('Quote card render failed:', err);
  process.exit(1);
});
