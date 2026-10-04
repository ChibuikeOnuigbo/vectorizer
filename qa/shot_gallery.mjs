import { chromium } from 'playwright-core';
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const ctx = browser.contexts()[0] || await browser.newContext();
const page = await ctx.newPage();
await page.goto('http://127.0.0.1:8000/model_result/index.html', {waitUntil:'load', timeout: 30000});
await page.waitForTimeout(1500);
await page.screenshot({path:'/tmp/gallery_top.png', fullPage:false});
// scroll to find the teal trend strip + stats header
const header = await page.evaluate(() => document.querySelector('h1,.stats,#stats')?.innerText?.slice(0,300));
console.log('HEADER:', header?.replace(/\s+/g,' ').slice(0,240));
const trend = await page.evaluate(() => {
  const els=[...document.querySelectorAll('div')].filter(d=>d.textContent.includes('teal vs-reference trend'));
  return els.length ? els[0].textContent.slice(0,300) : 'NOT FOUND';
});
console.log('TREND:', trend.replace(/\s+/g,' ').slice(0,240));
await page.close().catch(()=>{});
process.exit(0);
