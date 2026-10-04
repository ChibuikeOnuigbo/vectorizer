import { chromium } from 'playwright';
import fs from 'fs';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const page = await (browser.contexts()[0] || await browser.newContext()).newPage();
await page.setViewportSize({ width: 1400, height: 1000 });
await page.goto('http://localhost:8000/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1500);
await page.click('#startBtn');
await page.waitForSelector('#upload:not([hidden])');
const [fc] = await Promise.all([page.waitForEvent('filechooser'), page.click('#convertBtn')]);
await fc.setFiles('/home/user/vectorizer/model_result/inputs/text_23800_0141_v07_blur2.png');
await page.waitForFunction(() => {
  const c = document.getElementById('choiceOverlay');
  const r = document.getElementById('result');
  return (c && !c.hidden) || (r && !r.hidden);
}, { timeout: 60000 });
const choiceVisible = await page.evaluate(() => { const c = document.getElementById('choiceOverlay'); return c && !c.hidden; });
if (choiceVisible) {
  await page.click('#choiceSimple');
  await page.waitForSelector('#result:not([hidden])', { timeout: 20000 });
}
await page.waitForFunction(() => {
  const im = document.getElementById('resultSvg');
  return im && im.complete && im.naturalWidth > 0;
}, null, { timeout: 30000 });
const meta = await page.textContent('#resultMeta');
console.log('RESULT META:', meta.trim());
await page.screenshot({ path: 'audits/absolute_test_svg/e2e_boost_ghost_ui.png' });
// server-side engine stamp cross-check: fetch current svg
const res = await page.evaluate(async () => {
  const r = await fetch(document.getElementById('resultSvg').src);
  const t = await r.text();
  const m = t.match(/data-engine="([^"]+)"/);
  return m ? m[1] : null;
});
console.log('ENGINE STAMP:', res);
await page.close();
console.log('OK');
