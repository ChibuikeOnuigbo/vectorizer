// Section 20: reference-workflow test (the in-repo Cloudinary-style mock site).
// Compares USER PIPELINE (app :8000) behavior to REFERENCE/MOCK PIPELINE (:8100):
// - same image, both flows exercised via real browser
// - outcome metrics recorded side by side (no claim the mock uses a real engine:
//   the mock ALWAYS returns the same static blue diamond SVG - captured verbatim).
import { chromium } from "playwright";
import fs from "fs";

const APP = "http://127.0.0.1:8000";
const MOCK = "http://127.0.0.1:8100";
const PNG = "/home/user/vectorizer/test-assets/images/user-provided/teal-orbit-logo.png";
const SHOTS = "/home/user/research/qa-screens/reference";
fs.mkdirSync(SHOTS, { recursive: true });

const out = { user_pipeline: {}, reference_mock: {}, consoleErrors: [] };
const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
const ctx = await browser.newContext({ viewport: { width: 1300, height: 850 } });
const page = await ctx.newPage();
page.on("pageerror", (e) => out.consoleErrors.push("pageerror: " + e.message));

// ---- REFERENCE / MOCK pipeline ----
let t0 = Date.now();
await page.goto(MOCK + "/", { waitUntil: "domcontentloaded" });
await page.setInputFiles("#file", PNG);
await page.click("#convertBtn");
await page.waitForFunction(() => document.querySelector("#status")?.textContent === "Done", null, { timeout: 10000 });
const mockMs = Date.now() - t0;
await page.screenshot({ path: `${SHOTS}/mock-after-convert.png` });
const mockSvg = await (await fetch(MOCK + "/result.svg")).text();
out.reference_mock = {
  system: "model/mock_site.py local reference mock (Cloudinary-inspired UX copycat; STATIC output)",
  ms_total: mockMs,
  result_svg_bytes: mockSvg.length,
  result_svg_sha_note: "single static path diamond - independent of uploaded image (by design of the mock)",
  download_link: "/result.svg",
  upload_ui: "plain <input type=file> + Convert button",
  waits: "artificial 2.5s conversion sleep inside the page",
};

// ---- USER pipeline (real app) ----
t0 = Date.now();
await page.goto(APP + "/", { waitUntil: "domcontentloaded" });
await page.evaluate(async () => { localStorage.clear(); try { for (const d of (await indexedDB.databases())) await indexedDB.deleteDatabase(d.name);} catch{} });
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForSelector("#startBtn");
await page.click("#startBtn");
await page.setInputFiles("#fileInput", PNG);
await page.waitForSelector("#choiceOverlay:not([hidden])", { timeout: 30000 }).catch(() => {});
const appMs = Date.now() - t0;
await page.click("#choiceSimple", { force: true });
await page.waitForFunction(() => window.__vz?.view === "result", null, { timeout: 30000 });
await page.screenshot({ path: `${SHOTS}/app-result.png` });
const svgLen = await page.evaluate(() => document.querySelector("#resultSvg")?.src?.length || 0);
out.user_pipeline = {
  system: "this repository app (vtracer engine + trained model mode)",
  ms_total: appMs,
  svg_preview_url_len: svgLen,
  download: "#downloadBtn (in-page, blob URL of actual generated SVG)",
  upload_ui: "dropzone + file picker, auto-convert on select, workspace-choice modal",
};
out.consoleErrors = out.consoleErrors.slice(0, 10);
fs.writeFileSync("/home/user/research/qa-screens/reference/reference-comparison.json", JSON.stringify(out, null, 1));
console.log("DONE", JSON.stringify(out, null, 1));
await ctx.close();
process.exit(0);
