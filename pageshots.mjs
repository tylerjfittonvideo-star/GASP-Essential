// Rebrand comparison shots: full page at 1x (dodges Chrome's 16384px capture
// limit) plus above-the-fold at 2x, for desktop and mobile widths.
// Usage: node pageshots.mjs <path-or-url> <tag>   e.g. node pageshots.mjs /products.html products-r1
import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(__dirname, 'temporary screenshots');
if (!fs.existsSync(dir)) fs.mkdirSync(dir);

const target = process.argv[2] || '/';
const tag = process.argv[3] || 'shot';
const url = (target.startsWith('http') ? target : 'http://localhost:3000' + target)
  + (target.includes('?') ? '&' : '?') + 'preview=1';

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  args: ['--no-sandbox'],
});

for (const [width, name] of [[1440, 'desktop'], [390, 'mobile']]) {
  const page = await browser.newPage();
  await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 700));
  await page.screenshot({ path: path.join(dir, `${tag}-${name}-full.png`), fullPage: true });
  await page.setViewport({ width, height: 900, deviceScaleFactor: 2 });
  await new Promise(r => setTimeout(r, 300));
  await page.screenshot({ path: path.join(dir, `${tag}-${name}-fold.png`) });
  await page.close();
}
await browser.close();
console.log('saved', tag);
