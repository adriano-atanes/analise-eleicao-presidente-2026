// Renderiza a animação quadro a quadro (modo vídeo do portal) para virar MP4
// Uso: node 18b_video_apuracao.js <rota> <pasta> <nº de quadros> <quadros parados no fim>
const { chromium } = require('playwright');
(async () => {
  const [rota, dir, nq, hold] = [process.argv[2], process.argv[3], +process.argv[4], +process.argv[5]];
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1080 }, colorScheme: 'dark' });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto('http://localhost:8765/#' + rota); await p.waitForFunction(() => window.__apuracao && window.__apuracao.pronto, null, { timeout: 30000 });
  await p.waitForTimeout(1500);
  const el = await p.$('#vp');
  for (let k = 0; k < nq + hold; k++) {
    const u = Math.min(1, k / (nq - 1));
    await p.evaluate((u) => window.__apuracao.quadro(u), u);
    await el.screenshot({ path: `${dir}/q${String(k).padStart(4, '0')}.png` });
  }
  console.log('ok', errs); await b.close();
})();
