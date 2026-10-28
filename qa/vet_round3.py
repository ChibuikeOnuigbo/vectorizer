#!/usr/bin/env python3
"""Distrust battery round 3 -- input-format decoders, dimension boundaries,
output invariants, perf/concurrency/leak smoke. Shipped endpoint only,
default POST (no engine fields) -- same bytes the browser UI sends.

Usage: PYTHONPATH=vendor:app/deps:qa:. python3 qa/vet_round3.py
"""
from __future__ import annotations

import io, json, math, os, re, statistics, sys, time, hashlib
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ("vendor", "app/deps", "qa", "."):
    sys.path.insert(0, os.path.join(ROOT, p))

import numpy as np                        # noqa: E402
import urllib.request                     # noqa: E402
from PIL import Image, ImageDraw          # noqa: E402

BASE = "http://127.0.0.1:8000"

CHECKS = []
def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), str(detail)))
    print(("PASS" if ok else "FAIL"), name, ("-- " + str(detail) if detail else ""), flush=True)

def post_convert(data: bytes, fname: str, fields: dict | None = None,
                 timeout: float = 120.0):
    boundary = "----vet3" + hashlib.md5(os.urandom(8)).hexdigest()
    body = []
    if fields:
        for k, v in fields.items():
            body.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                        f'name="{k}"\r\n\r\n{v}\r\n'.encode())
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f'filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
    body.append(data)
    body.append(f"\r\n--{boundary}--\r\n".encode())
    payload = b"".join(body)
    req = urllib.request.Request(
        BASE + "/api/convert", data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode()), time.time() - t0
    except urllib.error.HTTPError as e:
        try:    detail = e.read().decode()[:200]
        except Exception: detail = ""
        return e.code, {"detail": detail}, time.time() - t0

def png_bytes(im: Image.Image) -> bytes:
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()

def jpeg_bytes(im: Image.Image, q=90) -> bytes:
    b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=q); return b.getvalue()

# synthetic content: 3-shape logo-ish raster with alpha
def logo_rgba(w, h):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle([int(.1*w), int(.1*h), int(.9*w), int(.9*h)],
                         radius=max(2, int(.08*min(w, h))), fill=(30, 144, 200, 255))
    dr.ellipse([int(.55*w), int(.2*h), int(.85*w), int(.5*h)], fill=(240, 160, 40, 255))
    dr.polygon([(int(.2*w), int(.7*h)), (int(.45*w), int(.4*h)), (int(.5*w), int(.8*h))],
               fill=(200, 60, 90, 255))
    return im

L = logo_rgba(320, 240)

# ---------------------------------------------------------------- formats
print("== FORMAT DECODER BATTERY ==", flush=True)

# F1: EXIF-rotated JPEG (stored landscape, displayed portrait via orientation=6)
im_wide = logo_rgba(400, 250).convert("RGB")
exif = Image.Exif(); exif[274] = 6  # orientation: rotate 90 CW for display
b = io.BytesIO(); im_wide.save(b, "JPEG", exif=exif)
st, d, _ = post_convert(b.getvalue(), "exif-rot.jpg")
ok = st == 200
if ok:
    m = d.get("meta", {})
    # displayed orientation is 250x400 (portrait); a decoder ignoring EXIF sees 400x250
    ok = m.get("height") == 400 and m.get("width") == 250
    check("F1 EXIF-rotation honored (displayed 250x400 not stored 400x250)", ok,
          f"status={st} meta={m.get('width')}x{m.get('height')}")
else:
    check("F1 EXIF-rotation honored", False, f"status={st} {d.get('detail','')[:120]}")

# F2: palette PNG with tRNS
p8 = L.convert("P", palette=Image.Palette.ADAPTIVE, colors=32)
info = L.convert("RGBA").info
p8.info["transparency"] = L.convert("RGBA").getchannel("A").point(lambda a: 255 if a > 8 else 0) if False else p8.info.get("transparency")
b2 = io.BytesIO(); p8.save(b2, "PNG", transparency=b"\x00" * 1 if False else None)
# simpler honest palette+alpha: save RGBA-quantized palette with default alpha path
b2 = io.BytesIO(); L.convert("P", palette=Image.Palette.ADAPTIVE, colors=32).save(b2, "PNG")
st, d, _ = post_convert(b2.getvalue(), "palette.png")
svg_f2 = d.get("svg", "")
check("F2 palette PNG converts", st == 200 and "<svg" in svg_f2[:400],
      f"status={st} prolog={'<?xml' in svg_f2[:20]}")

# F3: 16-bit grayscale PNG
g16 = (np.abs(np.random.default_rng(3).normal(90, 40, (240, 320)))).astype(np.uint16) * 256
g16 = Image.fromarray(g16, "I;16")
b3 = io.BytesIO(); g16.save(b3, "PNG")
st, d, _ = post_convert(b3.getvalue(), "gray16.png")
check("F3 16-bit grayscale PNG converts", st == 200, f"status={st} {d.get('detail','')[:80]}")

# F4: CMYK JPEG
cmyk = L.convert("CMYK")
b4 = io.BytesIO(); cmyk.save(b4, "JPEG")
st, d, _ = post_convert(b4.getvalue(), "cmyk.jpg")
check("F4 CMYK JPEG converts (or honest 4xx, never 500)", st < 500, f"status={st}")

# F5: interlaced PNG
b5 = io.BytesIO(); L.save(b5, "PNG", interlace=True)
st, d, _ = post_convert(b5.getvalue(), "interlaced.png")
check("F5 interlaced PNG converts", st == 200, f"status={st}")

# F6: animated GIF (3 frames)
frames = [logo_rgba(200, 150).convert("RGB"),
          logo_rgba(200, 150).point(lambda v: v).convert("RGB"),
          logo_rgba(200, 150).convert("RGB")]
b6 = io.BytesIO(); frames[0].save(b6, "GIF", save_all=True, append_images=frames[1:], duration=200, loop=0)
st, d, t = post_convert(b6.getvalue(), "anim.gif", timeout=180)
check("F6 animated GIF handled (no hang/500)", st < 500 and t < 170, f"status={st} t={t:.1f}s")

# F7: BMP 24-bit
b7 = io.BytesIO(); L.convert("RGB").save(b7, "BMP")
st, d, _ = post_convert(b7.getvalue(), "bmp.bmp")
check("F7 BMP converts", st == 200, f"status={st}")

# F8: WebP with alpha
b8 = io.BytesIO(); L.save(b8, "WEBP", quality=95)
st, d, _ = post_convert(b8.getvalue(), "alpha.webp")
check("F8 WebP+alpha converts", st == 200, f"status={st}")

# F9: 1-bit PNG
b9 = io.BytesIO()
L.convert("L").point(lambda v: 255 if v > 128 else 0).convert("1").save(b9, "PNG")
st, d, _ = post_convert(b9.getvalue(), "onebit.png")
check("F9 1-bit PNG converts", st == 200, f"status={st}")

# F10: fully transparent RGBA
empty = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
st, d, t = post_convert(png_bytes(empty), "empty.png")
check("F10 fully-transparent image -> honest response (no 500/hang)",
      st != 500 and t < 30, f"status={st} t={t:.1f}s paths={d.get('meta',{}).get('paths')}")

# ------------------------------------------------------------- dimensions
print("== DIMENSION BOUNDARIES ==", flush=True)
for tag, (w, h) in {"D1 1x1": (1, 1), "D2 3x256 sliver": (3, 256),
                    "D3 64x64 pixel-art boundary": (64, 64),
                    "D4 65x65 off-boundary": (65, 65),
                    "D5 2000x30 panorama": (2000, 30)}.items():
    st, d, t = post_convert(png_bytes(logo_rgba(w, h)), f"{tag.split()[0]}.png")
    if st == 200:
        m = d.get("meta", {})
        mw, mh = m.get("width"), m.get("height")
        if mw == w and mh == h:
            ok = True
        else:
            # >MAX_EDGE: pipeline downscales with ONE isotropic factor; the only
            # aspect wobble allowed is integer-pixel rounding (<=0.5px) of the
            # already-tiny short edge. Verify scale isotropy, not ratio strings:
            # w_out/w_in == h_out/h_in, each within 1 pixel of w,h * factor.
            import math as _m
            f = min(1.0, 1500 / max(w, h))
            ok = (abs(mw - max(1, round(w * f))) <= 0 and
                  abs(mh - max(1, round(h * f))) <= 0)
        check(f"{tag}: 200 + isotropic scale kept", ok, f"{w}x{h} -> {mw}x{mh} t={t:.1f}s")
    else:
        check(f"{tag}: 200", False, f"status={st} {d.get('detail','')[:100]}")

# D6: 12MP load completes (under the 64MP guard)
big = logo_rgba(4000, 3000)
st, d, t = post_convert(png_bytes(big), "big12mp.png", timeout=300)
check("D6 4000x3000 12MP converts within 5min (no worker death)",
      st == 200 and d.get("svg"), f"status={st} t={t:.1f}s kb={d.get('meta',{}).get('kb')}")

# ------------------------------------------------------------- invariants
print("== OUTPUT INVARIANTS ==", flush=True)
sample = png_bytes(L)
st1, d1, _ = post_convert(sample, "inv.png")
st2, d2, _ = post_convert(sample, "inv.png")
check("I1 determinism: same bytes in -> identical SVG (sha256)",
      d1.get("svg") == d2.get("svg"),
      f"{hashlib.sha256((d1.get('svg','')).encode()).hexdigest()[:12]} vs "
      f"{hashlib.sha256((d2.get('svg','')).encode()).hexdigest()[:12]}")

import xml.etree.ElementTree as ET
svgs = []
for i, (w, h) in enumerate([(320, 240), (64, 64), (500, 125), (128, 512), (222, 222)]):
    _, dd, _ = post_convert(png_bytes(logo_rgba(w, h)), f"inv{i}.png")
    svgs.append(dd.get("svg", ""))
ok_xml = True
try:
    for s in svgs: ET.fromstring(s)
except Exception as e:
    ok_xml = False
check("I2 all SVG outputs XML-well-formed", ok_xml)

bad = [i for i, s in enumerate(svgs)
       if re.search(r"<script|on[a-z]+\s*=|https?://(?!www\.w3\.org)", s)]
check("I3 no script/handlers/external refs in outputs", not bad, f"bad={bad}")

nan = [i for i, s in enumerate(svgs) if re.search(r"nan|inf", s, re.I)]
check("I4 no NaN/Inf tokens in path data", not nan, f"bad={nan}")

fills = {}
for c in (2, 4, 8, 16, 32):
    _, dd, _ = post_convert(sample, "inv.png", {"colors": str(c)})
    fills[c] = dd.get("meta", {}).get("colors", 0)
mono = all(fills[a] <= fills[b] + 1 for a, b in zip((2, 4, 8, 16), (4, 8, 16, 32)))
check("I5 palette knob monotonic non-decreasing richness", mono, f"{fills}")
bounded = all(fills[c] <= c + 1 for c in fills)
check("I5b meta colors honor requested bound", bounded, f"{fills}")

# ------------------------------------------------------------- perf / leak
print("== PERF / CONCURRENCY / LEAK SMOKE ==", flush=True)
imgs = [png_bytes(logo_rgba(200 + 20 * i, 150)) for i in range(8)]
with ThreadPoolExecutor(max_workers=8) as ex:
    rs = list(ex.map(lambda b_: post_convert(b_, "c.png"), imgs))
okc = all(st == 200 for st, _, _ in rs)
widths = [d.get("meta", {}).get("width") for _, d, _ in rs]
check("C1 8 concurrent distinct uploads: all 200, no width cross-contamination",
      okc and sorted(widths) == [200 + 20 * i for i in range(8)], f"widths={sorted(widths)}")

lat = []
for i in range(12):
    st, d, t = post_convert(png_bytes(logo_rgba(256, 256)), "lat.png")
    if st == 200: lat.append(t)
p95 = sorted(lat)[int(len(lat) * 0.95)] if lat else 99
check("C2 latency p95<5s mean<2s on 256px logos", p95 < 5 and statistics.mean(lat) < 2,
      f"mean={statistics.mean(lat):.2f}s p95={p95:.2f}s")

# C3 leak smoke: RSS growth over 40 converts
rss0 = None
try:
    import resource
    def rss_mb():
        if sys.platform.startswith("linux"):
            return int(open(f"/proc/{os.getpid()}/status").read().split("VmRSS:")[1].split()[0]) / 1024
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
except Exception:
    def rss_mb(): return 0.0
# server-side RSS read via /proc of the uvicorn process
import subprocess, glob
pid_line = subprocess.run(["pgrep", "-f", "uvicorn app.main"], capture_output=True, text=True).stdout.split()
def srv_rss():
    for pid in pid_line:
        try:
            return int(open(f"/proc/{pid}/status").read().split("VmRSS:")[1].split()[0]) / 1024
        except Exception: pass
    return 0.0
r0 = srv_rss()
for i in range(40):
    post_convert(png_bytes(logo_rgba(300, 300)), "leak.png")
r1 = srv_rss()
check("C3 server RSS growth over 40 converts < 150MB (leak smoke)",
      (r1 - r0) < 150, f"{r0:.0f}MB -> {r1:.0f}MB")

print(f"\n== ROUND-3 SUMMARY: {sum(1 for _, ok, _ in CHECKS if ok)}/{len(CHECKS)} PASS ==", flush=True)
json.dump({"results": [{"name": n, "ok": ok, "detail": dt} for n, ok, dt in CHECKS]},
          open(os.path.join(ROOT, "qa", "results-vet-round3.json"), "w"), indent=1)
sys.exit(0 if all(ok for _, ok, _ in CHECKS) else 1)
