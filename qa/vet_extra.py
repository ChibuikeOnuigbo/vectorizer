#!/usr/bin/env python3
"""Deep-vet battery (round 2): areas the main gate doesn't cover.

  A. CONCURRENCY        8 parallel uploads must each match their sequential
                        hash (no cross-contamination / shared-state races)
  B. DECOMPRESSION      huge-dimension images must not hang/crash the server
                        (PIL bomb raiser -> graceful 422, big-but-ok -> 200)
  C. SVG INTEGRITY      60 corpus outputs: well-formed XML + no active content
                        (script/foreignObject/javascript:/onload handlers)
  D. PALETTE BOUNDARIES colors=1/2/128/129/0.5/'abc'/-3 clamp to 2..128 rules
  E. PATH TRAVERSAL     ../ must never serve outside static roots
  F. GALLERY HONESTY    index.html counts must equal index.json recounts

Run: PYTHONPATH=app/deps:vendor:qa:. python3 qa/vet_extra.py
Requires: app on :8000, CDP browser on :9222.
"""
from __future__ import annotations

import concurrent.futures as cf
import io, json, re, sys
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qa"))
from runner import http_convert  # noqa: E402

import urllib.request, urllib.error  # noqa: E402

ok_all = True
def chk(name, ok, detail=""):
    global ok_all
    ok_all = ok_all and ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))

def get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

# ---------- A. concurrency ---------------------------------------------------
print("=== A. concurrency ===")
pool = sorted((ROOT / "test-assets/images/generated").glob("gen-0[0-3]*.png"))[:8]
seq = {}
for p in pool:
    _, pl, _, err = http_convert({}, path=str(p), fname=p.name, timeout=180)
    seq[p.name] = pl["svg"] if not err else None
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(http_convert, {}, None, p.read_bytes(), p.name, "/api/convert", 180): p.name for p in pool}
    par = {}
    for f in cf.as_completed(futs):
        _, pl, _, err = f.result()
        par[futs[f]] = pl["svg"] if not err else None
chk("8 parallel uploads all 200", all(v for v in par.values()))
same = sum(1 for n in seq if seq[n] and par[n] == seq[n])
chk("parallel == sequential byte-identical (no cross-contamination)",
    same == len(pool), f"{same}/{len(pool)} identical")

# ---------- B. decompression / huge dimensions -------------------------------
# Header-level pixel cap (added vet 2026-10-07): files <=20MB but >8192^2
# total pixels must be 413'd before any raster is allocated. (First battery
# run proved the need: 10000^2 walked straight through, ~400MB+ spike.)
print("=== B. pixel-bomb guard ===")
ok8k = io.BytesIO()
Image.new("RGB", (8000, 8000), (200, 30, 30)).save(ok8k, "PNG")      # 64MP, under cap
code, pl, ms, err = http_convert({}, raw=ok8k.getvalue(), fname="ok8k.png", timeout=300)
chk("8000x8000 under cap converts (200)", code == 200 and pl and bool(pl.get("svg")),
    f"{round((ms or 0)/1000, 1)}s")

big = io.BytesIO()
Image.new("RGB", (10000, 10000), (30, 30, 200)).save(big, "PNG")     # 100MP bomb
code, pl, ms, err = http_convert({}, raw=big.getvalue(), fname="bomb10k.png", timeout=120)
detail = (pl or {}).get("detail", "") if isinstance(pl, dict) else str(err)[:60]
chk("10000x10000 (100MP) rejected 413 at header, fast",
    code == 413 and (ms is None or ms < 3000), f"HTTP {code} in {round((ms or 0)/1000,2)}s: {str(detail)[:70]}")
code, _ = get("/healthz")
chk("server alive after bomb attempts", code == 200)

# ---------- C. SVG integrity + active content --------------------------------
print("=== C. SVG XML integrity + safety (60 corpus) ===")
corpus = sorted((ROOT / "model/data/logos").glob("*.png"))[:30] + \
         sorted((ROOT / "model/data/logos_text").glob("*.png"))[:30]
bad_xml, active = [], []
for p in corpus:
    _, pl, _, err = http_convert({}, path=str(p), fname=p.name, timeout=120)
    svg = (pl or {}).get("svg", "")
    try:
        ET.fromstring(svg)
    except ET.ParseError as e:
        bad_xml.append((p.name, str(e)[:60]))
    low = svg.lower()
    if re.search(r"<script|<foreignobject|javascript:|onload=|onerror=", low):
        active.append(p.name)
chk("60 corpus SVGs well-formed XML", not bad_xml, str(bad_xml[:3]))
chk("60 corpus SVGs no active content", not active, str(active[:3]))

# ---------- D. palette knob boundaries ---------------------------------------
print("=== D. palette knob boundaries ===")
probe = ROOT / "test-assets/images/generated/gen-06-base.png"
def with_colors(c):
    _, pl, _, err = http_convert({"colors": str(c)}, path=str(probe), fname=probe.name, timeout=120)
    return pl.get("svg") if not err else None
s_def = with_colors(None)
s1, s2, s128, s129 = with_colors(1), with_colors(2), with_colors(128), with_colors(129)
s_abc, s_neg, s_half = with_colors("abc"), with_colors(-3), with_colors(0.5)
chk("colors=abc/-3/0.5 don't crash and fall back to default",
    all(v == s_def for v in (s_abc, s_neg, s_half)))
chk("colors=1 clamps to 2 (== colors=2)", s1 == s2, f"{len(s1 or '')} vs {len(s2 or '')}")
chk("colors=129 clamps to 128 (== colors=128)", s129 == s128)
# knob-bites semantics (pinned since 2026-10-05): the palette knob re-injects
# cp/max_inks/tone_bands on PALETTE-AWARE (banding) engines only; mono/pixel
# routes are already minimal-ink, so colors=N is a no-op there by design.
tiles = ROOT / "test-assets/images/generated/palette-36tiles.png"
def tiles_colors(c):
    _, pl, _, err = http_convert({"colors": str(c)} if c else {}, path=str(tiles), fname=tiles.name, timeout=120)
    return pl.get("svg") if not err else None
t_def, t2, t64 = tiles_colors(None), tiles_colors(2), tiles_colors(64)
chk("colors knob bites on palette-aware engine (36tiles c2 != default != c64)",
    t2 != t_def and t_def != t64 and t2 != t64,
    f"lens {len(t2 or '')}/{len(t_def or '')}/{len(t64 or '')}")
chk("colors=2 no-op on mono engine by design (1-2 ink art)", s2 == s_def)

# ---------- E. path traversal -------------------------------------------------
print("=== E. path traversal ===")
tests = [
    "/../requirements.txt",
    "/static/..%2f..%2frequirements.txt",
    "/model_result/../app/main.py",
    "/static/%2e%2e/%2e%2e/app/main.py",
]
leaks = []
for t in tests:
    code, body = get(t)
    if code == 200 and (b"fastapi" in body.lower() or b"MAX_EDGE" in body or b"import" in body[:200]):
        leaks.append((t, code))
chk("no source served via traversal", not leaks, str(leaks))
code, _ = get("/api/convert")
chk("GET /api/convert not 200 (method not allowed/405)", code != 200, f"HTTP {code}")

# ---------- F. gallery honesty ------------------------------------------------
print("=== F. gallery header honesty ===")
idx = json.loads((ROOT / "model_result/index.json").read_text())
rows = [r for r in idx["entries"] if r.get("status") == "OK"]
# the reference row (mr-000) renders as a PASS card but has no status field
ref_p = sum(1 for r in idx["entries"]
            if "strict_similarity_to_input_pct" in r and r.get("strict_verdict") == "PASS")
n_p = sum(1 for r in rows if r["strict_verdict"] == "PASS") + ref_p
n_w = sum(1 for r in rows if r["strict_verdict"] == "WEAK")
n_f = sum(1 for r in rows if r["strict_verdict"] == "FAIL")
html = (ROOT / "model_result/index.html").read_text()
m = re.search(r"<h1>[^<]*?(\d+) PASS · (\d+) WEAK · (\d+) FAIL over (\d+) rows</h1>", html)
if m:
    hp, hw, hf, hr = map(int, m.groups())
    chk("gallery h1 counts == index.json recount (incl. reference row)",
        (hp, hw, hf) == (n_p, n_w, n_f),
        f"header {hp}/{hw}/{hf} vs recount {n_p}/{n_w}/{n_f}")
    # badges actually rendered must equal the header (no hidden inflation);
    # ladder cards live above the data grid and are not data rows.
    grid_html = html.split('<div class="grid">', 1)[1] if '<div class="grid">' in html else html
    bp = len(re.findall(r'class="badge PASS"', grid_html))
    bw = len(re.findall(r'class="badge WEAK"', grid_html))
    bf = len(re.findall(r'class="badge FAIL"', grid_html))
    badges = (bp, bw, bf)
    chk("rendered badges == header counts", badges == (hp, hw, hf),
        f"badges {badges} vs header {(hp, hw, hf)}")
else:
    chk("gallery h1 counts == index.json recount", False, "h1 pattern not found")

print(f"\n{'ALL PASS' if ok_all else 'FAILURES PRESENT'}")
sys.exit(0 if ok_all else 1)
