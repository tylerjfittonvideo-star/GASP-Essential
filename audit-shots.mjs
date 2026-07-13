// One-off capture for the rebrand audit — full page at 1x (dodges Chrome's
// 16384px capture limit) plus per-section viewport crops at 2x.
import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(__dirname, 'temporary screenshots');
if (!fs.existsSync(dir)) fs.mkdirSync(dir);

const URL_BASE = 'http://localhost:3000/?preview=1';
const SECTIONS = ['hero', 'problem', 'services', 'about', 'platforms', 'why', 'engage', 'cta'];

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox'],
});

async function capture(width, tag) {
  const page = await browser.newPage();

  // Full page at 1x
  await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
  await page.goto(URL_BASE, { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(dir, `audit-${tag}-full.png`), fullPage: true });

  // Section crops at 2x
  await page.setViewport({ width, height: 900, deviceScaleFactor: 2 });
  for (const id of SECTIONS) {
    await page.evaluate(sid => {
      const el = document.getElementById(sid);
      if (el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 64);
    }, id);
    await new Promise(r => setTimeout(r, 300));
    await page.screenshot({ path: path.join(dir, `audit-${tag}-${id}.png`) });
  }
  await page.close();
}

await capture(1440, 'desktop');
await capture(390, 'mobile');
await browser.close();
console.log('done');
