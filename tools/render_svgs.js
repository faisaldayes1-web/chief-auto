// Rasterises every SVG in a folder to a transparent PNG with Chromium (Playwright).
// Usage: node tools/render_svgs.js <svg_dir> <png_dir> [scale] [preview_color]
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || '/opt/node-tools/node_modules/playwright');

(async () => {
  const [src, dst, scaleArg] = process.argv.slice(2);
  const scale = parseFloat(scaleArg || '0.6');
  fs.mkdirSync(dst, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const f of fs.readdirSync(src).filter((f) => f.endsWith('.svg')).sort()) {
    const svg = fs.readFileSync(path.join(src, f), 'utf8');
    const w = parseInt(/width="(\d+)"/.exec(svg)[1], 10);
    const h = parseInt(/height="(\d+)"/.exec(svg)[1], 10);
    await page.setViewportSize({ width: Math.round(w * scale), height: Math.round(h * scale) });
    await page.setContent(`<html><body style="margin:0;background:transparent">
      <div style="width:${w}px;height:${h}px;transform:scale(${scale});transform-origin:0 0">${svg}</div></body></html>`);
    await page.screenshot({ path: path.join(dst, f.replace('.svg', '.png')), omitBackground: true });
  }
  await browser.close();
})();
