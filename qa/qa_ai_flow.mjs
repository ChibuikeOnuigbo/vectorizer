// QA walkthrough for the three-method UI (use model / no model / AI assist)
// Real Chromium over CDP — no jsdom, no static inspection.
import { chromium } from "playwright";
import fs from "fs";

const BASE = "http://127.0.0.1:8000";
const SHOTS = "/home/user/research/qa-screens";
fs.mkdirSync(SHOTS, { recursive: true });

const out = {
  browser: null, method: "Playwright connectOverCDP :9222",
  executable: "/tmp/chromium HeadlessChrome",
  viewports: ["1366x850", "430x900"],
  pages: ["/", ],
  interactions: [], consoleErrors: [], networkErrors: [], screenshots: [],
};

const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
out.browser = browser.browserType().name();
const ctx = await browser.newContext({ viewport: { width: 1366, height: 850 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") out.consoleErrors.push(m.text()); });
page.on("requestfailed", (r) => out.networkErrors.push(r.url() + " :: " + (r.failure()?.errorText || "?")));
page.on("pageerror", (e) => out.consoleErrors.push("pageerror: " + e.message));

async function shot(name) {
  const p = `${SHOTS}/${name}.png`;
  await page.screenshot({ path: p, fullPage: false });
  out.screenshots.push(p);
  return p;
}
const note = (s) => { out.interactions.push(s); console.log("QA:", s); };

// 1 landing
await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForTimeout(1200);
await shot("01-landing");
note("landing loaded");
const icons = await page.evaluate(() => document.querySelectorAll("svg.lucide").length);
note(`lucide icons rendered: ${icons}`);

// 2 go to upload
await page.click("#startBtn");
await page.waitForTimeout(500);
await shot("02-upload");
const cards = await page.evaluate(() =>
  [...document.querySelectorAll(".method-card h4")].map((h) => h.textContent.trim()));
note(`method cards: ${cards.join(" | ")}`);

// 3 model sliders
await page.click("#methodModel");
await page.waitForTimeout(300);
const sliderVisible = await page.evaluate(() => {
  const el = document.getElementById("modelOptions");
  return el && !el.hidden && document.querySelectorAll("#modelOptions input.slider").length === 3;
});
await shot("03-model-sliders");
note(`model sliders visible (3): ${sliderVisible}`);

// 4 classic options
await page.click("#methodClassic");
await page.waitForTimeout(300);
const classicInfo = await page.evaluate(() => ({
  presets: document.querySelectorAll(".preset-btn").length,
  enhance: !!document.getElementById("cEnhance"),
  best: !!document.getElementById("cBest"),
}));
await shot("04-classic-options");
note(`classic presets ${classicInfo.presets}, clean-first ${classicInfo.enhance}, best engine ${classicInfo.best}`);

// 5 AI assist pane + settings modal
await page.click("#methodAI");
await page.waitForTimeout(300);
await shot("05-ai-pane");
await page.click("#aiOpenSettingsBtn");
await page.waitForTimeout(400);
const provCount = await page.evaluate(() => document.querySelectorAll("#aiProvider option").length);
await shot("06-ai-modal");
note(`AI settings modal open, providers: ${provCount}`);
// fill settings with a fake key (no real call made)
await page.selectOption("#aiProvider", "gemini");
await page.fill("#aiKey", "qa-test-key-1234567890");
await page.selectOption("#aiDetail", "auto");
await page.click("#aiSaveBtn");
await page.waitForTimeout(300);
const status = await page.evaluate(() => document.getElementById("aiStatusText").textContent.trim());
await shot("07-ai-status");
note(`AI status after save: ${status}`);

// 6 convert with model method (runs real convert)
await page.click("#methodModel");
const [chooser] = await Promise.all([
  page.waitForEvent("filechooser"),
  page.click("#convertBtn"),
]);
await chooser.setFiles("/tmp/testlogo.png");
note("uploaded testlogo.png, waiting for result");
await page.waitForSelector("#choiceOverlay:not([hidden])", { timeout: 60000 });
await shot("08-choice");
await page.click("#choiceSimple");
await page.waitForTimeout(800);
await shot("09-simple-studio");
const rmeta = await page.evaluate(() => document.getElementById("resultMeta").textContent);
note(`simple studio meta: ${rmeta}`);

// 7 redo with AI button present
const aiBtn = await page.evaluate(() => !!document.getElementById("aiStudioBtn"));
note(`redo with AI button present: ${aiBtn}`);

// 8 compare dotted line
const hasCompare = await page.evaluate(() => !!document.getElementById("compareBtn"));
await page.click("#compareBtn");
await page.waitForTimeout(600);
const dividerCss = await page.evaluate(() => {
  const d = document.getElementById("compareDivider");
  const cs = getComputedStyle(d);
  return { borderLeft: cs.borderLeftWidth + " " + cs.borderLeftStyle, top: cs.top, bottom: cs.bottom };
});
await shot("10-compare");
note(`compare divider: ${JSON.stringify(dividerCss)}`);
await page.click("#compareCloseBtn");

// 9 fullscreen viewer
await page.click("#viewBtn");
await page.waitForTimeout(500);
await shot("11-fullscreen");
await page.click("#viewCloseBtn");

// 10 mobile viewport spot check
await page.setViewportSize({ width: 430, height: 900 });
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.waitForTimeout(800);
await shot("12-mobile-landing");
note("mobile landing checked");

// AI error path handled gracefully (fake key -> network blocked in sandbox is expected)
const aiErr = await page.evaluate(async () => {
  try {
    const fd = new FormData();
    const blob = new Blob([new Uint8Array(64)], { type: "image/png" });
    fd.append("file", new File([blob], "x.png", { type: "image/png" }));
    const res = await fetch("/api/ai/vectorize", { method: "POST", headers: { "x-ai-key": "bad" }, body: fd });
    return res.status + " " + (await res.text()).slice(0, 120);
  } catch (e) { return "fetch-fail " + e; }
});
note(`AI endpoint with bad key -> ${aiErr} (friendly error expected)`);

out.interactions.push("done");
fs.writeFileSync(`${SHOTS}/qa-result.json`, JSON.stringify(out, null, 2));
console.log("CONSOLE ERRORS:", out.consoleErrors.length, JSON.stringify(out.consoleErrors.slice(0, 5)));
console.log("NETWORK ERRORS:", out.networkErrors.length, JSON.stringify(out.networkErrors.slice(0, 5)));
await ctx.close();
await browser.disconnect();
console.log("QA DONE");
