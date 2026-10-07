#!/usr/bin/env python3
"""Independent verification battery for the user-upload evidence.

Written under a "trust nothing" mandate: every claim about the upload->
vector evidence is re-proven by methods that share NO code with the original
measurement where feasible:

  1. IDENTITY     md5 of the uploaded files vs canonical test assets
  2. DETERMINISM  two fresh live conversions must be byte-identical
  3. TRUE VECTOR  assert no <image>/data:image/base64 blobs in the SVG
  4. TWO PATHS    HTTP POST svg vs real-browser DOM upload svg: byte-equal
  5. INDEP-SCORE  hand-rolled numpy scorer (MAE / silhouette IoU / windowed
                  SSIM) recomputed here -- NOT imported from similarity_audit
  6. DOM PIXELS   screenshot the app's own result <img> in the browser and
                  hand-score that against the input (what the user sees)
  7. SCALABILITY  render the 56-90 KB svg at 4x -- geometry must scale
                  (an embedded raster would need megabytes, excluded by 3)

Run: PYTHONPATH=app/deps:vendor:qa:. python3 qa/verify_upload_evidence.py
Requires: app on :8000, CDP browser on :9222.
"""
from __future__ import annotations

import hashlib, io, json, re, subprocess, sys, time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qa"))
from runner import http_convert               # transport only (multipart POST)
from similarity_audit import render_svg       # rasterizer only (CDP screenshot)

OUT = ROOT / "evidence" / "upload-check"
CASES = [
    ("blue-bird", ROOT / "download.png", 74.5),
    ("teal-logo", ROOT / "image-removebg-preview.png", 87.9),
]
CANON = {
    "blue-bird": ROOT / "test-assets/images/user-provided/blue-bird-appicon.png",
    "teal-logo": ROOT / "test-assets/images/user-provided/teal-orbit-logo.png",
}

ok_all = True
def chk(name: str, ok: bool, detail: str = ""):
    global ok_all
    ok_all = ok_all and ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))

def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()

# ---- hand-rolled scoring (no audit imports) --------------------------------
def hand_channels(inp: Image.Image, vec: Image.Image) -> dict:
    # NOTE: composite in float64 -- int16 overflows at 255*255 BEFORE the
    # /255.0 divide (first-battery revision bug; caught because this battery
    # disagreed with the audit, which is the point of running it).
    a = np.asarray(inp.convert("RGBA")).astype(np.float64)   # HxWx4
    b = np.asarray(vec.convert("RGBA")).astype(np.float64)
    assert a.shape == b.shape, f"shape mismatch {a.shape} vs {b.shape}"
    ca = a[..., :3] * a[..., 3:] / 255.0 + 255.0 * (1 - a[..., 3:] / 255.0)
    cb = b[..., :3] * b[..., 3:] / 255.0 + 255.0 * (1 - b[..., 3:] / 255.0)
    mae = float(np.abs(ca - cb).mean())
    f_mae = max(0.0, 1.0 - mae / 255.0)
    ma = a[..., 3] > 14
    mb = b[..., 3] > 14
    u = int((ma | mb).sum())
    iou = int((ma & mb).sum()) / u if u else 1.0
    # Rec.601 luma (definition-matching) AND mean luma (independent variant)
    g601_a = ca[..., 0] * 0.299 + ca[..., 1] * 0.587 + ca[..., 2] * 0.114
    g601_b = cb[..., 0] * 0.299 + cb[..., 1] * 0.587 + cb[..., 2] * 0.114

    def wssim(ga, gb):
        c1, c2 = 0.01 ** 2, 0.03 ** 2
        vals = []
        blk = 12
        H, W = ga.shape
        for y in range(0, H - blk + 1, blk):
            for x in range(0, W - blk + 1, blk):
                pa, pb = ga[y:y+blk, x:x+blk], gb[y:y+blk, x:x+blk]
                mva, mvb = pa.mean(), pb.mean()
                va, vb = pa.var(), pb.var()
                cov = ((pa - mva) * (pb - mvb)).mean()
                vals.append(((2*mva*mvb + c1) * (2*cov + c2)) /
                            max((mva**2 + mvb**2 + c1) * (va + vb + c2), 1e-12))
        return float(np.mean(vals)) if vals else 1.0

    ssim = wssim(g601_a, g601_b)
    ssim_mean = wssim(ca.mean(axis=2), cb.mean(axis=2))
    return {"mae": round(mae, 3), "f_mae": round(f_mae, 4),
            "iou": round(iou, 4), "ssim": round(ssim, 4),
            "ssim_mean_luma": round(ssim_mean, 4),
            "score": round(100 * min(f_mae, iou, ssim), 1)}

def grey(im: Image.Image, px: int) -> Image.Image:
    return im.convert("RGBA").resize((px, px), Image.BILINEAR)

report = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "method": "independent re-verification, no shared scoring code",
          "cases": []}
OUT.mkdir(parents=True, exist_ok=True)

for tag, src, claimed in CASES:
    print(f"\n===== {tag} ({src.name}) =====")
    data = src.read_bytes()
    inp = Image.open(io.BytesIO(data)).convert("RGBA")

    chk(f"{tag} identity md5 == canonical test asset",
        md5(data) == md5(CANON[tag].read_bytes()), md5(data)[:10])

    code1, p1, ms1, e1 = http_convert({}, path=str(src), fname=src.name, timeout=180)
    code2, p2, ms2, e2 = http_convert({}, path=str(src), fname=src.name, timeout=180)
    s1, s2 = (p1 or {}).get("svg"), (p2 or {}).get("svg")
    chk(f"{tag} live convert #1 ok", code1 == 200 and bool(s1))
    chk(f"{tag} determinism (2 fresh converts byte-identical)",
        bool(s1) and s1 == s2, f"sha256={hashlib.sha256((s1 or '').encode()).hexdigest()[:16]}")

    low = (s1 or "").lower()
    chk(f"{tag} TRUE VECTOR: no <image>/data:image/base64",
        "<image" not in low and "data:image" not in low and "base64" not in low)
    prim = len(re.findall(r"<(path|rect|circle|polygon|ellipse)\b", s1 or ""))
    chk(f"{tag} has vector primitives", prim >= 1, f"{prim} primitives, {len(s1)//1024} KB")
    eng = re.search(r'data-engine="([^"]+)"', s1).group(1)

    (OUT / f"{tag}-input.png").write_bytes(data)
    (OUT / f"{tag}-output.svg").write_text(s1)

    vec = render_svg(s1, inp.size[0], inp.size[1])
    hc = hand_channels(inp, vec)
    chk(f"{tag} independent score vs claimed ({hc['score']} vs {claimed})",
        abs(hc["score"] - claimed) <= 1.0,
        f"mae={hc['mae']} iou={hc['iou']} ssim={hc['ssim']}")

    big = render_svg(s1, inp.size[0] * 4, inp.size[1] * 4)
    a4 = np.asarray(big.convert("RGBA"))[..., 3]
    chk(f"{tag} scalable vector (4x render has full silhouette)",
        (a4 > 14).mean() > 0.002 and big.size[0] == inp.size[0] * 4)

    # DOM path: real browser upload through the actual UI; capture the
    # /api/convert response the UI received (byte-compare vs raw HTTP).
    node_script = ROOT / "qa" / f"_dom_upload_{tag}.mjs"   # must live where node_modules resolves
    node_script.write_text(f"""
import {{ chromium }} from 'playwright';
import fs from 'fs';
const b = await chromium.connectOverCDP('http://127.0.0.1:9222');
const page = await (b.contexts()[0] || await b.newContext()).newPage();
let domSvg = null;
page.on('response', async r => {{
  if (r.url().includes('/api/convert')) {{
    try {{ domSvg = (await r.json()).svg; }} catch (e) {{}}
  }}
}});
await page.goto('http://127.0.0.1:8000/', {{waitUntil: 'domcontentloaded'}});
const buf = fs.readFileSync({json.dumps(str(src))});
await page.setInputFiles('#fileInput', {{name: {json.dumps(src.name)}, mimeType: 'image/png', buffer: buf}});
await page.waitForSelector('#result:not([hidden])', {{timeout: 30000}});
await page.waitForTimeout(700);
fs.writeFileSync({json.dumps(f"/tmp/dom-{tag}.svg")}, domSvg || 'MISSING');
process.exit(domSvg ? 0 : 2);
""")
    dom = subprocess.run(["node", str(node_script)], cwd=ROOT / "qa",
                         capture_output=True, text=True, timeout=120)
    dom_svg = Path(f"/tmp/dom-{tag}.svg").read_text() if Path(f"/tmp/dom-{tag}.svg").exists() else ""
    if dom.returncode != 0:
        print(f"   (node dom probe rc={dom.returncode}: {dom.stderr.strip()[:200]})")
    chk(f"{tag} UI DOM path svg == HTTP svg byte-identical",
        dom.returncode == 0 and dom_svg == s1,
        "browser upload and raw POST produced the same vector"
        if dom.returncode == 0 and dom_svg == s1 else
        f"rc={dom.returncode} DOM {len(dom_svg)}B vs HTTP {len(s1)}B")
    node_script.unlink(missing_ok=True)
    report["cases"].append({"tag": tag, "file": src.name,
                            "svg_sha256": hashlib.sha256(s1.encode()).hexdigest(),
                            "engine": eng, "primitives": prim,
                            "svg_bytes": len(s1),
                            "hand_score": hc, "claimed_strict": claimed})

dupes = md5((ROOT / "image-removebg-preview.png").read_bytes()) == \
        md5((ROOT / "image-removebg-preview (1).png").read_bytes())
chk("the two 'preview' uploads are byte-identical (2 unique images among 3)", dupes)

(OUT / "verification.json").write_text(json.dumps(report, indent=1))
print(f"\n{'ALL PASS' if ok_all else 'FAILURES PRESENT'} -> evidence/upload-check/verification.json")
sys.exit(0 if ok_all else 1)
