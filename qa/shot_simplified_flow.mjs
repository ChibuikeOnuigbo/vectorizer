// Driven screenshot proof (2026-10-05 simplification): simplified upload UI,
// single Smart card + palette slider, then convert teal + blue-bird and capture
// the live input/output result views (Simple Studio + Advanced inspection).
import { chromium } from "playwright";
import path from "path";
import fs from "fs";

const BASE = "http://127.0.0.1:8000";
const OUT = "/home/user/vectorizer/qa/shots/simplified-ui";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
const ctx = browser.contexts()[0] || (await browser.newContext());
const page = await ctx.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.evaluate(async () => {
  localStorage.clear();
  const dbs = await indexedDB.databases();
  for (const db of dbs) if (db.name) indexedDB.deleteDatabase(db.name);
});
await page.reload({ waitUntil: "networkidle" });
await page.waitForSelector("#landing:not([hidden])");
await page.screenshot({ path: OUT + "/01-landing.png" });

await page.click("#startBtn");
await page.waitForSelector("#upload:not([hidden])");
await page.waitForTimeout(400);
await page.screenshot({ path: OUT + "/02-upload-simplified.png" });

// palette slider at 4 to prove the one knob works (gallery shows UI state)
async function setColors(v) {
  await page.evaluate((val) => {
    const el = document.getElementById("mColors");
    el.value = String(val);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, v);
}

async function convertShot(file, tag, colorVal) {
  await page.click("#newBtn").catch(() => {});
  await page.waitForSelector("#upload:not([hidden])").catch(() => {});
  const [fc] = await Promise.all([
    page.waitForEvent("filechooser"),
    page.click("#convertBtn"),
  ]);
  if (colorVal) await setColors(colorVal);
  await fc.setFiles("/home/user/vectorizer/" + file);
  await page.waitForSelector("#result:not([hidden])", { timeout: 60000 });
  await page.waitForFunction(() => {
    const im = document.getElementById("resultSvg");
    return im && im.complete && im.naturalWidth > 0;
  }, { timeout: 30000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${tag}.png` });
}

await convertShot("test-assets/images/user-provided/teal-orbit-logo.png", "03-teal-result");
await convertShot("test-assets/images/user-provided/blue-bird-appicon.png", "04-bird-result");
await convertShot("test-assets/images/generated/palette-36tiles.png", "05-palette-default");
await convertShot("test-assets/images/generated/palette-36tiles.png", "06-palette-colors8", 3); // slider idx 3 = 16 colors

// Advanced inspection view (knob-free diagnostics kept)
await page.click("#openAdvancedBtn");
await page.waitForSelector("#advanced:not([hidden])", { timeout: 10000 });
await page.waitForTimeout(500);
await page.screenshot({ path: OUT + "/07-advanced-inspection.png" });

await page.close();
await browser.close();
console.log("shots written to", OUT);
