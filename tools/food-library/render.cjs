// Renders every SVG in <svgDir> to a 512×512 PNG in <pngDir> (Chromium, same look on every PC)
const fs = require('fs'), path = require('path'), { chromium } = require('playwright');
(async () => {
  const [svgDir, pngDir] = process.argv.slice(2);
  fs.mkdirSync(pngDir, { recursive: true });
  const b = await chromium.launch(), p = await b.newPage({ viewport: { width: 512, height: 512 } });
  for(const f of fs.readdirSync(svgDir).filter(f => f.endsWith('.svg')).sort()){
    await p.setContent(`<html><body style="margin:0">${fs.readFileSync(path.join(svgDir, f), 'utf8')}</body></html>`);
    await p.screenshot({ path: path.join(pngDir, f.replace(/\.svg$/, '.png')), clip: { x: 0, y: 0, width: 512, height: 512 } });
  }
  await b.close();
})();
