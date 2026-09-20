"""Best-effort scraper for public vectorizer sites (vectorizer.io,
vectorizer.studio, vectorizer.ai).

For each site it:
  * loads the page,
  * finds the file input or — by reading button labels ("sense") — the
    convert/upload control,
  * uploads one of our test logos,
  * then runs a while-loop with a wait timer, polling until a result
    (download link, data URL, or a large inline SVG) appears,
  * downloads/saves the result SVG plus a screenshot (we can't "see" the
    page, so the screenshot is the visual proof),
  * records everything in model/scraped/results.json.

Scraped outputs are combined with our own pipeline outputs for ranking:
the site's SVG is scored with the SAME reward as our candidates.

Usage:  PYTHONPATH=vendor:. python -m model.scrape_sites [--site https://...]
        (requires the QA chromium running on 127.0.0.1:9222 — see scripts/setup-browser.sh)
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from pathlib import Path

SITES = [
    "https://vectorizer.io/",
    "https://vectorizer.studio/",
    "https://vectorizer.ai/",
]
BTN_RE = re.compile(r"convert|vectoriz|upload|start|try|run|go\b|drop", re.I)
RESULT_ANCHORS = ['a[download]', 'a[href$=".svg"]', 'a[href$=".png"]',
                  'a[href^="data:image/svg"]', 'a[href^="blob:"]']
WAIT_POLL = 0.75          # seconds between polls
WAIT_LIMIT = 90           # seconds to wait for a result per site


async def grab_result(page, outdir: Path, tag: str) -> dict:
    """One poll pass: look for any result artifact. Returns info dict or None."""
    for sel in RESULT_ANCHORS:
        el = await page.query_selector(sel)
        if not el:
            continue
        href = await el.get_attribute("href") or ""
        if href.startswith("data:image/svg"):
            try:
                b64 = href.split(",", 1)[1]
                (outdir / f"{tag}.svg").write_bytes(base64.b64decode(b64))
                return {"kind": "data-url", "path": str(outdir / f"{tag}.svg")}
            except Exception:
                continue
        if href.startswith("blob:"):
            try:
                async with page.expect_download(timeout=8000) as dl_info:
                    await el.click()
                dl = await dl_info.value
                dest = outdir / f"{tag}.svg"
                await dl.save_as(str(dest))
                return {"kind": "download", "path": str(dest)}
            except Exception:
                continue
        if href.startswith("http"):
            try:
                resp = await page.request.get(href)
                body = await resp.body()
                if b"<svg" in body[:4000] or b"<path" in body[:4000]:
                    (outdir / f"{tag}.svg").write_bytes(body)
                    return {"kind": "link", "path": str(outdir / f"{tag}.svg")}
            except Exception:
                continue
    # large inline svg (result rendered in the DOM)
    for svg in await page.query_selector_all("svg"):
        try:
            box = await svg.bounding_box()
            if not box or box["width"] < 220 or box["height"] < 220:
                continue
            html = await svg.evaluate("el => el.outerHTML")
            if "<path" in html and "viewBox" in html:
                (outdir / f"{tag}.svg").write_text(html)
                return {"kind": "inline-svg", "path": str(outdir / f"{tag}.svg")}
        except Exception:
            continue
    return None


async def scrape_one(browser, url: str, test_img: str, outdir: Path, tag: str) -> dict:
    page = await browser.contexts[0].new_page()
    info = {"site": url, "ok": False, "error": None}
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        fi = await page.query_selector("input[type=file]")
        if fi:
            await fi.set_input_files(test_img)
        # press the convert/run button if the page has one (matched by label)
        btn = None
        for b in await page.query_selector_all("button, a[role=button], [role=button]"):
            try:
                txt = (await b.inner_text()) or ""
            except Exception:
                continue
            if BTN_RE.search(txt):
                btn = b
                break
        if btn:
            await btn.click()
        elif not fi:
            info["error"] = "no file input or convert control found"
            await page.screenshot(path=str(outdir / f"{tag}.png"), full_page=True)
            return info
        # while-loop with wait timer: keep polling until the result shows up
        deadline = time.time() + WAIT_LIMIT
        while time.time() < deadline:
            await asyncio.sleep(WAIT_POLL)
            got = await grab_result(page, outdir, tag)
            if got:
                info.update(ok=True, **got)
                break
        if not info["ok"]:
            info["error"] = f"no result within {WAIT_LIMIT}s"
        await page.screenshot(path=str(outdir / f"{tag}.png"), full_page=True)
    except Exception as e:  # noqa: BLE001
        info["error"] = str(e)[:300]
        try:
            await page.screenshot(path=str(outdir / f"{tag}.png"), full_page=True)
        except Exception:
            pass
    finally:
        await page.close()
    return info


async def run(sites, test_img, outdir):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        results = []
        for url in sites:
            tag = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
            print(f"scraping {url} ...", flush=True)
            t0 = time.time()
            info = await asyncio.wait_for(scrape_one(browser, url, test_img, outdir, tag),
                                          timeout=WAIT_LIMIT + 60)
            info["seconds"] = round(time.time() - t0, 1)
            results.append(info)
            print(f"  -> {info.get('kind') or 'failed'} {info.get('error') or ''}")
        await browser.close()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", action="append", default=[])
    ap.add_argument("--image", default="download.png")
    ap.add_argument("--out", default="model/scraped")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    sites = args.site or SITES
    results = asyncio.run(run(sites, args.image, outdir))

    # score whatever we managed to get, with the SAME reward as our pipeline
    scored = []
    for info in results:
        if not info.get("ok") or not info.get("path"):
            continue
        try:
            from PIL import Image
            from model.svg_geom import score as rscore
            orig = Image.open(args.image).convert("RGBA")
            s = rscore(orig, Path(info["path"]).read_text())
            info["reward"] = s
            scored.append(s["score"])
        except Exception as e:  # noqa: BLE001
            info["reward_error"] = str(e)[:200]
    (outdir / "results.json").write_text(json.dumps(results, indent=1))
    ok = sum(1 for r in results if r["ok"])
    print(f"\ndone: {ok}/{len(results)} sites produced a result; "
          f"site rewards: {scored if scored else 'n/a'}")
    print(f"saved -> {outdir / 'results.json'}")
    if ok == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
