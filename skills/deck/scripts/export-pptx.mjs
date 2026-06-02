#!/usr/bin/env node

import { readdir, mkdir, rm, access } from 'node:fs/promises';
import { resolve, join, basename } from 'node:path';
import puppeteer from 'puppeteer';
import PptxGenJS from 'pptxgenjs';

const SLIDE_WIDTH = 1280;
const SLIDE_HEIGHT = 720;
const DEFAULT_SCALE_FACTOR = 3;

function parseArgs() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error('Usage: node export-pptx.mjs <presentation-dir> [output-filename] [--scale N]');
    console.error('Example: node export-pptx.mjs ./presentation deck --scale 3');
    process.exit(1);
  }

  let scaleFactor = DEFAULT_SCALE_FACTOR;
  const scaleIdx = args.indexOf('--scale');
  if (scaleIdx !== -1) {
    scaleFactor = parseInt(args[scaleIdx + 1]) || DEFAULT_SCALE_FACTOR;
    args.splice(scaleIdx, 2);
  }

  const presentationDir = resolve(args[0]);
  const outputName = args[1] || 'deck';
  return { presentationDir, outputName, scaleFactor };
}

async function discoverSlides(presentationDir) {
  const slidesDir = join(presentationDir, 'slides');

  try {
    await access(slidesDir);
  } catch {
    throw new Error(`Slides directory not found: ${slidesDir}`);
  }

  const files = await readdir(slidesDir);
  const slideFiles = files
    .filter(f => /^slide\d+\.html$/i.test(f))
    .sort((a, b) => {
      const numA = parseInt(a.match(/\d+/)[0]);
      const numB = parseInt(b.match(/\d+/)[0]);
      return numA - numB;
    });

  if (slideFiles.length === 0) {
    throw new Error(`No slide HTML files found in ${slidesDir}`);
  }

  return slideFiles.map(f => join(slidesDir, f));
}

async function renderSlides(slidePaths, tempDir, scaleFactor) {
  await mkdir(tempDir, { recursive: true });

  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const imagePaths = [];

  try {
    const page = await browser.newPage();
    await page.setViewport({
      width: SLIDE_WIDTH,
      height: SLIDE_HEIGHT,
      deviceScaleFactor: scaleFactor,
    });

    for (let i = 0; i < slidePaths.length; i++) {
      const slidePath = slidePaths[i];
      const imageFile = join(tempDir, `slide${i + 1}.png`);

      console.log(`  Rendering slide ${i + 1}/${slidePaths.length}: ${basename(slidePath)}`);

      await page.goto(`file://${slidePath}`, {
        waitUntil: 'networkidle0',
        timeout: 30000,
      });

      // Wait for CSS animations to complete (slides use up to ~2s animations with staggered delays)
      await new Promise(r => setTimeout(r, 2500));

      // Target the .slide element directly for a precise capture
      const slideElement = await page.$('.slide');
      if (slideElement) {
        await slideElement.screenshot({ path: imageFile, type: 'png' });
      } else {
        // Fallback: clip the viewport area
        await page.screenshot({
          path: imageFile,
          type: 'png',
          clip: { x: 0, y: 0, width: SLIDE_WIDTH, height: SLIDE_HEIGHT },
        });
      }

      imagePaths.push(imageFile);
    }
  } finally {
    await browser.close();
  }

  return imagePaths;
}

async function buildPptx(imagePaths, outputPath, title) {
  const pptx = new PptxGenJS();

  // Standard 16:9 widescreen layout (10" x 5.625")
  pptx.defineLayout({ name: 'CUSTOM_16_9', width: 10, height: 5.625 });
  pptx.layout = 'CUSTOM_16_9';
  pptx.title = title;

  for (const imagePath of imagePaths) {
    const slide = pptx.addSlide();
    slide.addImage({
      path: imagePath,
      x: 0,
      y: 0,
      w: '100%',
      h: '100%',
    });
  }

  await pptx.writeFile({ fileName: outputPath });
}

async function cleanup(tempDir) {
  try {
    await rm(tempDir, { recursive: true, force: true });
  } catch {
    // best-effort cleanup
  }
}

async function main() {
  const { presentationDir, outputName, scaleFactor } = parseArgs();
  const tempDir = join(presentationDir, '.export-temp');
  const outputFile = join(presentationDir, `${outputName}.pptx`);

  console.log('Exporting presentation to PPTX...');
  console.log(`  Source: ${presentationDir}`);
  console.log(`  Output: ${outputFile}`);
  console.log(`  Scale:  ${scaleFactor}x`);

  try {
    console.log('\n[1/3] Discovering slides...');
    const slidePaths = await discoverSlides(presentationDir);
    console.log(`  Found ${slidePaths.length} slides`);

    console.log('\n[2/3] Rendering slides to images...');
    const imagePaths = await renderSlides(slidePaths, tempDir, scaleFactor);

    console.log('\n[3/3] Building PPTX file...');
    await buildPptx(imagePaths, outputFile, outputName);

    console.log(`\nDone! PPTX saved to: ${outputFile}`);
  } catch (error) {
    console.error(`\nExport failed: ${error.message}`);
    process.exit(1);
  } finally {
    await cleanup(tempDir);
  }
}

main();
