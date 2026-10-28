// Exhaustive UI section snapshotter — captures EVERY reachable section/state
// of the Vectorizer frontend as real rendered PNGs for visual QA review.
// Usage: node qa/ui_snapshot_sections.mjs <outdir> [baseUrl]
// Needs: CDP Chrome on :9222 (scripts/setup-browser.sh) + app server (default :8000)
import fs from "node:fs";
import playwright from "playwright-core";

const OUT = process.argv[2] || "/home/user/research/qa-screens/sections";
const BASE = process.argv[3] || "http://127.0.0.1:8000";
fs.mkdirSync(OUT, { recursive: true });

const consoleErrors = [];
const softNotes = [];
const shots = []; // {name, desktop:[{mode,...}], mobile:[{mode}]}

// Each section = sequence of steps; steps: click, hover, setFile, waitMs,
// shotElement, shotPage, move, setViewport, focusViaTab, evalJs
function S(name, opts = {}) { return { name, ...opts }; }

const SECTIONS = [
  // ---- LANDING
  { group: "landing", id: "01-landing-page", sel: "#landing", page: true },
  { group: "landing", id: "02-landing-hero", sel: ".landing-inner" },
  { group: "landing", id: "03-landing-cta-hover", steps: [{ hover: "#startBtn" }], sel: ".landing-actions" },
  { group: "landing", id: "04-landing-meta", sel: ".landing-meta" },
  { group: "landing", id: "05-landing-mobile", mob: true, page: true },

  // ---- UPLOAD
  { group: "upload", id: "06-upload-dropzone-empty", steps: [{ click: "#startBtn", wait: 300 }], page: true },
  { group: "upload", id: "07-upload-method-card", steps: [{ click: "#startBtn", wait: 200 }, { hover: "#methodModel" }], sel: ".upload-methods", multiSel: ".method-card" },
  { group: "upload", id: "08-upload-sliders-idle", steps: [{ click: "#startBtn", wait: 200 }], sel: "#modelOptions" },
  { group: "upload", id: "09-upload-slider-hover", steps: [{ click: "#startBtn", wait: 200 }, { hover: "#mColors" }], sel: "#modelOptions" },
  { group: "upload", id: "10-upload-slider-active", steps: [{ click: "#startBtn", wait: 200 }, { mousedown: "#mColors" }], sel: "#modelOptions" },
  { group: "upload", id: "11-upload-slider-set", steps: [{ click: "#startBtn", wait: 200 }, { evalJs: "const r=document.getElementById('mColors');r.value=4;r.dispatchEvent(new Event('input',{bubbles:true}))", wait: 250 }], sel: "#modelOptions" },
  { group: "upload", id: "12-upload-convert-btn-hover", steps: [{ click: "#startBtn", wait: 200 }, { hover: "#convertBtn" }], sel: "#convertBtn" },
  { group: "upload", id: "13-upload-mobile", mob: true, steps: [{ click: "#startBtn", wait: 300 }], page: true },

  // ---- SIMPLE STUDIO (real conversion)
  { group: "result", id: "14-simple-studio", needsConvert: true, page: true },
  { group: "result", id: "15-simple-source-panel", needsConvert: true, sel: "#result .studio-grid .studio-panel:nth-child(1)" },
  { group: "result", id: "16-simple-result-panel", needsConvert: true, sel: "#result .studio-grid .studio-panel:nth-child(2)" },
  { group: "result", id: "17-simple-meta-row", needsConvert: true, sel: "#resultMeta" },
  { group: "result", id: "18-simple-actions-hover", needsConvert: true, steps: [{ hover: "#downloadBtn" }], sel: "#result .panel-actions" },
  { group: "result", id: "19-zoom-toolbar", needsConvert: true, steps: [{ click: "#zoomInBtn", wait: 250 }, { hover: "#zoomResetBtn" }], sel: "#result .zoom-group" },
  { group: "result", id: "20-bg-toggle-off", needsConvert: true, steps: [{ click: "#bgToggleBtn", wait: 350 }], sel: "#resultSvgBox", leave: "#bgToggleBtn" },
  { group: "result", id: "21-simple-mobile", needsConvert: true, mob: true, page: true },

  // ---- ADVANCED STUDIO
  { group: "advanced", id: "22-advanced-full", needsConvert: true, steps: [{ click: "#openAdvancedBtn", wait: 400 }], page: true },
  { group: "advanced", id: "23-advanced-inspect", needsConvert: true, steps: [{ click: "#openAdvancedBtn", wait: 250 }], sel: ".advanced-sidebar" },
  { group: "advanced", id: "24-advanced-inspect-rows", needsConvert: true, steps: [{ click: "#openAdvancedBtn", wait: 250 }], sel: "#inspectBody" },
  { group: "advanced", id: "25-advanced-actions", needsConvert: true, steps: [{ click: "#openAdvancedBtn", wait: 250 }, { hover: "#advDownloadBtn" }], sel: "#advanced .panel-actions" },
  { group: "advanced", id: "26-advanced-zoom", needsConvert: true, steps: [{ click: "#openAdvancedBtn", wait: 250 }, { click: "#advZoomInBtn", wait: 250 }], sel: "#advanced .zoom-group" },
  { group: "advanced", id: "27-advanced-mobile", needsConvert: true, mob: true, steps: [{ click: "#openAdvancedBtn", wait: 250 }], page: true, leave: "#advBackSimpleBtn" },

  // ---- OVERLAYS & STATES
  { group: "overlays", id: "28-drop-overlay", needsConvert: true, steps: [{ evalJs: "document.getElementById('dropOverlay').hidden=false", wait: 200 }], page: true, cleanupEvalJs: "document.getElementById('dropOverlay').hidden=true" },
  { group: "overlays", id: "29-fullscreen-viewer", needsConvert: true, steps: [{ click: "#viewBtn", wait: 600 }], page: true, leave: "#viewCloseBtn" },
  { group: "overlays", id: "30-viewer-zoomed", needsConvert: true, steps: [{ click: "#viewBtn", wait: 400 }, { click: "#viewZoomInBtn", wait: 300 }], page: true, leave: "#viewCloseBtn" },
  { group: "overlays", id: "31-viewer-floating-tools", needsConvert: true, steps: [{ click: "#viewBtn", wait: 400 }], sel: "#viewFloatingTools", leave: "#viewCloseBtn" },
  { group: "overlays", id: "32-viewer-hint", needsConvert: true, steps: [{ click: "#viewBtn", wait: 400 }], sel: "#viewHint", leave: "#viewCloseBtn" },
  { group: "overlays", id: "33-compare-overlay", needsConvert: true, steps: [{ click: "#compareBtn", wait: 600 }], page: true, leave: "#compareCloseBtn" },
  { group: "overlays", id: "34-compare-slider-72", needsConvert: true, steps: [{ click: "#compareBtn", wait: 500 }, { evalJs: "const s=document.getElementById('compareSlider');s.value=72;s.dispatchEvent(new Event('input',{bubbles:true}))", wait: 300 }], sel: "#compareStage", leave: "#compareCloseBtn" },
  { group: "overlays", id: "35-toast-ok", needsConvert: true, steps: [{ evalJs: "const t=document.getElementById('toast');t.hidden=false;t.className='toast ok';t.textContent='Vector ready'", wait: 200 }], sel: "#toast", cleanupEvalJs: "document.getElementById('toast').hidden=true" },
  { group: "overlays", id: "36-toast-error", needsConvert: true, steps: [{ evalJs: "const t=document.getElementById('toast');t.hidden=false;t.className='toast error';t.textContent='Conversion failed Try another image'", wait: 200 }], sel: "#toast", cleanupEvalJs: "document.getElementById('toast').hidden=true" },
];

async function run() {
  const browser = await playwright.chromium.connectOverCDP("http://127.0.0.1:9222");
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("response", (r) => { if (r.url().includes("/api/")) console.log(`API ${r.request().method()} ${r.url().split("/api/")[1]} -> ${r.status()}`); });
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  // kill any restored state for a clean deterministic run
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
  await page.reload({ waitUntil: "networkidle" });

  let converted = false;

  async function doSteps(steps = []) {
    for (const st of steps) {
      if (st.click) {
        const loc = page.locator(st.click).first();
        const vis = await loc.isVisible({ timeout: 800 }).catch(() => false);
        if (vis) await loc.click().catch((e) => consoleErrors.push(`click ${st.click}: ${e.message}`));
      }
      if (st.hover) { await page.hover(st.hover, { timeout: 1500 }).catch(() => softNotes.push(`hover skipped ${st.hover}`)); await page.waitForTimeout(220); }
      if (st.mousedown) {
        try {
          const el = page.locator(st.mousedown).first();
          const b = await el.boundingBox({ timeout: 1500 });
          if (b) { const x = b.x + b.width * 0.55; const y = b.y + b.height / 2; await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + b.width * 0.08, y, { steps: 3 }); }
        } catch (e) { softNotes.push(`mousedown skipped ${st.mousedown}: target missing`); }
        await page.waitForTimeout(200);
      }
      if (st.evalJs) { await page.evaluate(st.evalJs).catch((e) => consoleErrors.push(`evalJs: ${e.message}`)); }
      if (st.wait) await page.waitForTimeout(st.wait);
    }
  }

  async function pickLocator(sel, multiSel) {
    const candidates = [multiSel, sel].filter(Boolean);
    for (const c of candidates) {
      if (!c) continue;
      for (const one of c.split(",").map((s) => s.trim())) {
        const loc = page.locator(one).first();
        try { if (await loc.isVisible({ timeout: 400 })) return loc; } catch (e) {}
      }
    }
    return null;
  }

  let count = 0;
  for (const sec of SECTIONS) {
    count++;
    if (sec.needsConvert && !converted) {
      // real conversion: select a file -> change event auto-converts -> workspace-choice overlay -> Simple Studio
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(BASE + "/", { waitUntil: "networkidle" });
      await page.evaluate(() => { const o = document.getElementById("aiOverlay"); if (o) o.hidden = true; });
      const start = page.locator("#startBtn");
      if (await start.isVisible().catch(() => false)) await start.click().catch(() => {});
      await page.waitForSelector("#dropzone", { timeout: 15000 });
      await page.setInputFiles("#fileInput", "/home/user/vectorizer/test-assets/images/user-provided/teal-orbit-logo.png");
      await page.waitForTimeout(1200);
      await page.waitForSelector("#choiceOverlay:not([hidden])", { timeout: 90000 }).catch(() => {});
      const choiceShown = await page.evaluate(() => { const el = document.querySelector("#choiceOverlay"); return !!el && !el.hidden; });
      console.log(`conversion done; workspace-choice shown=${choiceShown}`);
      await page.screenshot({ path: `${OUT}/17b-workspace-choice.png` });
      if (choiceShown) await page.click("#choiceSimple", { force: true });
      try {
        await page.waitForFunction(() => window.__vz?.view === "result" && !document.querySelector("#result")?.hidden, null, { timeout: 90000 });
        converted = true;
      } catch (e) {
        const toast = await page.locator("#toast").textContent().catch(() => "");
        consoleErrors.push(`conversion failed; toast=${JSON.stringify(toast)}`);
        throw e;
      }
    }

    await page.setViewportSize(sec.mob ? { width: 390, height: 844 } : { width: 1440, height: 900 });
    await doSteps(sec.steps);

    let shot = false;
    if (sec.page) {
      await page.screenshot({ path: `${OUT}/${sec.id}.png` });
      shot = true;
    } else {
      const loc = await pickLocator(sec.sel, sec.multiSel);
      if (loc) { await loc.screenshot({ path: `${OUT}/${sec.id}.png` }); shot = true; }
    }
    console.log(`shot: ${sec.id}${shot ? "" : "  (FELL BACK — selector missing, page shot)"}`);
    if (!shot) await page.screenshot({ path: `${OUT}/${sec.id}.png` });

    for (const st of (sec.steps || [])) { if (st.mousedown) await page.mouse.up().catch(() => {}); }
    if (sec.cleanupEvalJs) await page.evaluate(sec.cleanupEvalJs).catch(() => {});
    if (sec.overlayResidue) await page.evaluate((id) => { const el = document.getElementById(id); if (el) el.hidden = true; }, sec.overlayResidue).catch(() => {});
    if (sec.leave) { await page.click(sec.leave).catch(() => {}); await page.waitForTimeout(300); }
  }

  if (softNotes.length) console.log("notes: " + JSON.stringify(softNotes, null, 1));
  console.log(`console errors: ${consoleErrors.length ? JSON.stringify(consoleErrors, null, 1) : "none"}`);
  console.log(`done -> ${OUT} (${SECTIONS.length} sections)`);
  await ctx.close();
  await browser.close();
}

run().catch((e) => { console.error(e); process.exit(1); });
