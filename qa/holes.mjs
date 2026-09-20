import { chromium } from "playwright";
import { readdirSync } from "node:fs";
const browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
const ctx = browser.contexts()[0] || await browser.newContext();
const page = await ctx.newPage();
await page.goto("http://127.0.0.1:8000/", { waitUntil: "domcontentloaded" });
const files = readdirSync("app/static/var").filter(f => f.endsWith(".svg")).sort();
for (const f of files) {
  const r = await page.evaluate(async (file) => {
    const svgText = await (await fetch("/static/var/" + file)).text();
    const svgImg = new Image();
    await new Promise((res, rej) => { svgImg.onload = res; svgImg.onerror = rej; svgImg.src = URL.createObjectURL(new Blob([svgText], { type: "image/svg+xml" })); });
    const origImg = new Image();
    await new Promise((res, rej) => { origImg.onload = res; origImg.onerror = rej; origImg.src = "/static/var/teal-orig.png"; });
    const W = svgImg.naturalWidth, H = svgImg.naturalHeight;
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.fillStyle = "#FF0000"; x.fillRect(0, 0, W, H);
    x.drawImage(svgImg, 0, 0, W, H);
    const oc = document.createElement("canvas"); oc.width = origImg.naturalWidth; oc.height = origImg.naturalHeight;
    const ox = oc.getContext("2d", { willReadFrequently: true });
    ox.drawImage(origImg, 0, 0);
    const od = ox.getImageData(0, 0, oc.width, oc.height).data;
    const sd = x.getImageData(0, 0, W, H).data;
    const solid = (px, py) => px >= 0 && py >= 0 && px < oc.width && py < oc.height && od[(py * oc.width + px) * 4 + 3] >= 250;
    const isRed = (si) => sd[si] > 200 && sd[si + 1] < 70 && sd[si + 2] < 70;
    const sx = W / oc.width, sy = H / oc.height;
    let holes = 0, edge = 0, opaque = 0;
    for (let y = 3; y < oc.height - 3; y += 3) {
      for (let px = 3; px < oc.width - 3; px += 3) {
        if (!solid(px, y)) continue;
        opaque++;
        const si = (Math.min(H - 1, Math.round(y * sy)) * W + Math.min(W - 1, Math.round(px * sx))) * 4;
        if (!isRed(si)) continue;
        if (solid(px - 1, y) && solid(px + 1, y) && solid(px, y - 1) && solid(px, y + 1)) holes++; else edge++;
      }
    }
    return { holes, edge, opaque };
  }, f);
  console.log(f, JSON.stringify(r));
}
await browser.close();
