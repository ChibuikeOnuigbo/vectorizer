import { chromium } from 'playwright';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const page = await (browser.contexts()[0] || await browser.newContext()).newPage();
await page.setViewportSize({ width: 1400, height: 1500 });
await page.goto('http://localhost:8000/model_result/', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(9000);
const info = await page.evaluate(() => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n, hits = [];
  while ((n = walker.nextNode())) {
    if (n.textContent.includes('soft-alpha-boost-halo')) hits.push(n.parentElement);
  }
  if (!hits.length) return { found: false, bodyHas: document.body.innerHTML.includes('soft-alpha-boost-halo') };
  hits[0].scrollIntoView({ block: 'start' });
  window.scrollBy(0, -140);
  return { found: true, n: hits.length };
});
console.log(JSON.stringify(info));
if (!info.found) process.exit(1);
await page.waitForTimeout(2500);
await page.screenshot({ path: 'audits/absolute_test_svg/model_result_gallery_boost_cards.png' });
console.log('OK');
await page.close();
