// Proof test: 100-image report page renders, verdict clicks append to file.
// Real Chromium over CDP :9222 — no jsdom.
import { chromium } from "playwright";
import fs from "fs";

const BASE = "http://127.0.0.1:8000";
const SHOTS = "/home/user/research/qa-screens/proof";
fs.mkdirSync(SHOTS, { recursive: true });

const out = { interactions: [], consoleErrors: [], networkErrors: [], screenshots: [], data: {} };
const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") out.consoleErrors.push(m.text()); });
page.on("requestfailed", (r) => out.networkErrors.push(r.url() + " :: " + (r.failure()?.errorText || "?")));
page.on("pageerror", (e) => out.consoleErrors.push("pageerror: " + e.message));
const note = (s) => { out.interactions.push(s); console.log("QA:", s); };

// 1) status endpoint
const status = await (await fetch(`${BASE}/api/test/report`)).json();
note(`report status: built=${status.built} images=${status.images} modelAvg=${status.m_avg} classicAvg=${status.c_avg}`);
out.data.status = status;

// 2) open page
await page.goto(`${BASE}/static/test-report.html`, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector(".row img", { timeout: 30000 });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${SHOTS}/01-top.png` });
out.screenshots.push(`${SHOTS}/01-top.png`);

const rows = await page.evaluate(() => document.querySelectorAll(".row").length);
const imgs = await page.evaluate(() => {
  const arr = [...document.querySelectorAll(".row .imgbox img")];
  const broken = arr.filter(im => !im.complete || im.naturalWidth === 0).length;
  return { total: arr.length, broken };
});
note(`rows=${rows} imgs=${imgs.total} broken=${imgs.broken}`);
out.data.rows = rows; out.data.imgs = imgs;

// scroll mid + bottom screenshots
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
await page.waitForTimeout(800);
await page.screenshot({ path: `${SHOTS}/02-mid.png` });
out.screenshots.push(`${SHOTS}/02-mid.png`);
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(800);
await page.screenshot({ path: `${SHOTS}/03-bottom.png` });
out.screenshots.push(`${SHOTS}/03-bottom.png`);
await page.evaluate(() => window.scrollTo(0, 0));

// 3) verdict clicks: row 0 model good, row 1 classic bad, row 2 model good
const v0 = await (await (await fetch(`${BASE}/api/manual/verdicts`)).json()).total;
note(`verdicts before: ${v0}`);
const btns = await page.$$("#appclicks button");
// click specific buttons via JS for determinism
await page.click('.row:nth-child(1) .col:nth-child(2) .vbtn.good');
await page.waitForTimeout(500);
await page.click('.row:nth-child(2) .col:nth-child(3) .vbtn.bad');
await page.waitForTimeout(500);
await page.click('.row:nth-child(3) .col:nth-child(2) .vbtn.good');
await page.waitForTimeout(800);
await page.screenshot({ path: `${SHOTS}/04-verdict-clicks.png` });
out.screenshots.push(`${SHOTS}/04-verdict-clicks.png`);
const vAfter = await (await (await fetch(`${BASE}/api/manual/verdicts`)).json());
note(`verdicts after 3 clicks: total=${vAfter.total} good=${vAfter.good} bad=${vAfter.bad}`);
out.data.verdicts = { before: v0, after: vAfter.total, good: vAfter.good, bad: vAfter.bad };

// 4) check the appended file is real JSONL on disk
const fileCount = fs.existsSync("/home/user/vectorizer/model_data_snapshot/verdicts.jsonl")
  ? fs.readFileSync("/home/user/vectorizer/model_data_snapshot/verdicts.jsonl", "utf8").trim().split("\n").filter(Boolean).length
  : 0;
note(`verdicts.jsonl lines on disk: ${fileCount} (appended to file = proof)`);
out.data.verdictsFileLines = fileCount;

// 5) cleanup: unvote the 3 test votes so the file stays the user's
for (const sel of ['.row:nth-child(1) .col:nth-child(2) .vbtn.good',
                   '.row:nth-child(2) .col:nth-child(3) .vbtn.bad',
                   '.row:nth-child(3) .col:nth-child(2) .vbtn.good']) {
  await page.click(sel);
  await page.waitForTimeout(400);
}
const vFinal = await (await (await fetch(`${BASE}/api/manual/verdicts`)).json()).total;
note(`verdicts after cleanup un-vote: ${vFinal}`);
out.data.verdictsAfterCleanup = vFinal;

fs.writeFileSync(`${SHOTS}/qa-proof.json`, JSON.stringify(out, null, 2));
console.log("CONSOLE ERRORS:", out.consoleErrors.length, JSON.stringify(out.consoleErrors.slice(0, 4)));
console.log("NETWORK ERRORS:", out.networkErrors.length, JSON.stringify(out.networkErrors.slice(0, 4)));
console.log("QA PROOF DONE");
process.exit(0);
