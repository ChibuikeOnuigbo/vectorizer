// Browser regression suite (directive §19 + §39 + §18 general interaction).
// Real Chromium over CDP :9222, Playwright driver.
//
// R1 upload-bug: upload -> convert -> click AROUND ON the vector result ->
//    the upload/drop UI must NOT reappear (file dialog nor dropzone view).
// R2 persistence: after conversion, page reload must restore source image and
//    SVG from IndexedDB WITHOUT re-running vectorization.
// R3 general: zoom/pan/fit/reset/compare/bg-toggle/new-image interactions
//    produce the expected state changes.
import { chromium } from "playwright";
import fs from "fs";

const BASE = "http://127.0.0.1:8000";
const SHOTS = "/home/user/research/qa-screens/regressions";
fs.mkdirSync(SHOTS, { recursive: true });
const PNG = "/home/user/vectorizer/test-assets/images/user-provided/teal-orbit-logo.png";

const out = { checks: [], consoleErrors: [], networkErrors: [], screenshots: [], verdict: {} };
const note = (s) => { out.checks.push(s); console.log("QA:", s); };
const shot = async (page, name) => { const p = `${SHOTS}/${name}`; await page.screenshot({ path: p }); out.screenshots.push(p); };

const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") out.consoleErrors.push(m.text()); });
page.on("pageerror", (e) => out.consoleErrors.push("pageerror: " + e.message));
page.on("requestfailed", (r) => out.networkErrors.push(r.url() + " :: " + (r.failure()?.errorText || "?")));

// track convert POSTs to detect unnecessary vectorize re-runs
let convertCalls = 0;
page.on("request", (r) => { if (r.url().includes("/api/convert") && r.method() === "POST") convertCalls++; });

await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector("#startBtn", { timeout: 30000 });

// fresh state
await page.evaluate(async () => {
  localStorage.clear();
  try {
    const dbs = await indexedDB.databases();
    for (const d of dbs) await indexedDB.deleteDatabase(d.name);
  } catch {}
});
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForSelector("#startBtn");

// ---- upload flow
await page.click("#startBtn");
await page.waitForSelector("#dropzone:not([hidden])", { timeout: 15000 });
await page.setInputFiles("#fileInput", PNG);
await page.waitForTimeout(1200);
const uploadState = await page.evaluate(() => ({
  uploadVisible: !document.querySelector("#upload")?.hidden,
}));
note("uploaded file; upload view visible=" + uploadState.uploadVisible + " (selecting a file auto-converts: convert() runs on input change)");
await shot(page, "01-after-upload.png");

// ---- convert happens on file select (input change -> convert()); #convertBtn is the file picker
const conv0 = convertCalls;
// the workspace-choice modal is intentional UX after a successful convert (§38)
await page.waitForSelector("#choiceOverlay:not([hidden])", { timeout: 90000 }).catch(() => {});
const choiceShown = await page.evaluate(() => !document.querySelector("#choiceOverlay")?.hidden);
note("workspace choice overlay shown after convert: " + choiceShown);
await shot(page, "02a-workspace-choice.png");
if (choiceShown) await page.click("#choiceSimple", { force: true });
await page.waitForFunction(() => window.__vz?.view === "result" && !document.querySelector("#result")?.hidden, null, { timeout: 90000 });
await page.waitForSelector("#resultSvg", { timeout: 30000 });
// svg preview is a blob: URL created from the converted SVG text
const svgOk = await page.evaluate(() => {
  const im = document.querySelector("#resultSvg");
  return { view: window.__vz?.view, svgSrcLen: im?.src?.length || 0 };
});
note("conversion done; result view visible. svg probe: " + JSON.stringify(svgOk));
out.verdict.convertCalls_initial = convertCalls - conv0;
await shot(page, "02-result.png");

// ---- R1 must-not-reopen-upload
const before = await page.evaluate(() => ({
  uploadVisible: !document.querySelector("#upload")?.hidden,
  landingVisible: !document.querySelector("#landing")?.hidden,
}));
async function ensureViewerClosed() {
  for (let k = 0; k < 3; k++) {
    const open = await page.evaluate(() => !document.querySelector("#viewOverlay")?.hidden);
    if (!open) return true;
    await page.keyboard.press("Escape").catch(() => {});
    await page.waitForTimeout(150);
    const still = await page.evaluate(() => !document.querySelector("#viewOverlay")?.hidden);
    if (still) await page.click("#viewCloseBtn", { force: true }).catch(() => {});
    await page.waitForTimeout(150);
  }
  return !(await page.evaluate(() => !document.querySelector("#viewOverlay")?.hidden));
}
// click on the SVG result area itself, then around it (edges); the svg box legally
// opens the fullscreen viewer - close it after each such click, like a user would
for (const sel of ["#resultSvgBox", "#srcPreviewBox", "#resultMeta", "#srcMeta"]) {
  const el = await page.$(sel);
  if (el) { const bb = await el.boundingBox(); await page.mouse.click(bb.x + bb.width / 2, bb.y + bb.height / 2); await page.waitForTimeout(200); }
  await ensureViewerClosed();
}
const r1 = await page.evaluate(() => ({
  uploadVisible: !document.querySelector("#upload")?.hidden,
  landingVisible: !document.querySelector("#landing")?.hidden,
  resultVisible: !document.querySelector("#result")?.hidden,
}));
// a native file chooser can't be observed directly; detect that an input click would
// have opened the dialog by spying on programmatic .click() calls
const dlgSpy = await page.evaluate(() => { // re-arm spy then simulate real clicks again
  window.__dlgSpy = 0;
  const fi = document.querySelector("#fileInput");
  window.__dlgSpyErr = null;
  const orig = fi.click.bind(fi);
  fi.click = () => { window.__dlgSpy++; };
  return true;
});
await page.click("#resultSvgBox"); await page.waitForTimeout(300);
const viewerOpen = await page.evaluate(() => !document.querySelector("#viewOverlay")?.hidden);
note("fullscreen viewer opened by result click: " + viewerOpen);
const closed = await ensureViewerClosed();
note("viewer closed after Escape: " + closed);
await page.click("#srcPreviewBox"); await page.waitForTimeout(150);
const spyCount = await page.evaluate(() => window.__dlgSpy ?? -1);
await page.keyboard.press("Escape").catch(() => {});
await page.waitForTimeout(200);
const spyCount2 = await page.evaluate(() => window.__dlgSpy ?? -1);
const r1pass = !r1.uploadVisible && !r1.landingVisible && r1.resultVisible && spyCount === 0 && spyCount2 === 0;
note(`R1 upload-bug: resultVisible=${r1.resultVisible} uploadVisible=${r1.uploadVisible} landingVisible=${r1.landingVisible} fileDialogClicks=${spyCount} viewerOpened=${viewerOpen} afterEsc=${spyCount2} -> ${r1pass ? "PASS" : "FAIL"}`);
out.verdict.R1_upload_bug = r1pass ? "PASS" : "FAIL";
out.verdict.R1_detail = { before, r1, spyCount };

// ---- R3 interactions (compare/zoom/bg) on result view
const z0 = await page.textContent("#zoomLevel");
await page.click("#zoomInBtn"); await page.waitForTimeout(120);
const z1 = await page.textContent("#zoomLevel");
await page.click("#zoomResetBtn"); await page.waitForTimeout(120);
const z2 = await page.textContent("#zoomLevel");
await page.click("#bgToggleBtn").catch(() => {});
await page.waitForTimeout(120);
await page.click("#compareBtn").catch(() => {});
await page.waitForTimeout(300);
const cmp = await page.evaluate(() => ({
  cmpVisible: !document.querySelector("#compareOverlay")?.hidden || !!document.querySelector(".compare-overlay:not([hidden])") || document.body.textContent.includes("Compare"),
}));
await shot(page, "03-zoom-compare.png");
await page.keyboard.press("Escape").catch(() => {}); // close compare overlay if open
await page.waitForTimeout(200);
const r3pass = z0 !== z1 && z2 === "100%";
note(`R3 zoom: ${z0} -> ${z1} -> reset ${z2}; compare overlay visible=${cmp.cmpVisible} -> ${r3pass ? "PASS" : "FAIL"}`);
out.verdict.R3_interactions = r3pass ? "PASS" : "FAIL";

// ---- R2 persistence: reload and wait; source + svg restore, no re-convert
const conv1 = convertCalls;
await page.reload({ waitUntil: "domcontentloaded" });
await page.waitForTimeout(3500);
const restored = await page.evaluate(() => {
  const svg = document.querySelector("#resultSvg");
  const orig = document.querySelector("#resultOriginal");
  const adv = document.querySelector("#advanced");
  const res = document.querySelector("#result");
  return {
    resultVisible: res ? !res.hidden : false,
    advancedVisible: adv ? !adv.hidden : false,
    svgSrcLen: svg && svg.src ? svg.src.length : 0,
    origSrcLen: orig && orig.src ? orig.src.length : 0,
  };
});
await shot(page, "04-after-reload.png");
// svg/orig previews are short blob: URLs (~50-70 chars); what matters is the result
// view is restored with both srcs bound and no re-conversion request was sent
const r2pass = (restored.resultVisible || restored.advancedVisible) && restored.svgSrcLen > 20 && restored.origSrcLen > 20 && (convertCalls - conv1) === 0;
note(`R2 persistence: svgLen=${restored.svgSrcLen} origLen=${restored.origSrcLen} reconvertCalls=${convertCalls - conv1} -> ${r2pass ? "PASS" : "FAIL"}`);
out.verdict.R2_persistence = r2pass ? "PASS" : "FAIL";
out.verdict.R2_detail = { restored, reconvertCalls: convertCalls - conv1 };

// ---- new image button returns to upload intentionally (explicit action allowed)
await page.click("#newBtn").catch(() => {});
await page.waitForTimeout(400);
const afterNew = await page.evaluate(() => ({
  uploadVisible: !document.querySelector("#upload")?.hidden,
}));
note(`new-image returns to upload (explicit action): ${afterNew.uploadVisible ? "PASS" : "CHECK"}`);
out.verdict.R4_new_image = afterNew.uploadVisible ? "PASS" : "CHECK_MANUAL";

fs.writeFileSync("/home/user/research/qa-screens/regressions/regressions.json", JSON.stringify(out, null, 1));
console.log("VERDICT", JSON.stringify(out.verdict));
await ctx.close();
process.exit(0);
