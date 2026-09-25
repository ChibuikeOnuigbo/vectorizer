"""Dataset step 3-5: deterministic rasterization of source SVGs -> input.png.

Browser-based rendering per directive ("Browser-based rendering is
acceptable where necessary"): headless chromium via CDP renders grids of
inline SVGs, one PIL slice per cell, saved as the pair input.png.
Variants (section 8): sizes 64/128/256, backgrounds transparent/white/dark,
plus blur + jpeg conditions for a subset.

  bash scripts/setup-browser.sh   # first, if /tmp/chromium wiped
  PYTHONPATH=vendor:app/deps:. python3 scripts/dataset/render_pairs.py [limit]
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(ROOT / "vendor"), str(ROOT / "app/deps"), str(ROOT)):
    sys.path.insert(0, p)

import io  # noqa: E402

import websocket  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

import urllib.request  # noqa: E402

OUT_LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 300
BLUR_CAP = int(sys.argv[3]) if len(sys.argv) > 3 else 0  # 0 = all pairs get blur/jpeg §8 variants
CELL_CSS = lambda cell: f"display:flex;align-items:center;justify-content:center;width:{cell}px;height:{cell}px"  # noqa: E731


def wait_cdp(url: str, tries: int = 60) -> dict:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url + "/json/version", timeout=2) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1)
    raise RuntimeError("CDP not reachable at " + url)


class CDP:
    def __init__(self, base="http://127.0.0.1:9222"):
        wait_cdp(base)
        req = urllib.request.Request(base + "/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            tab = json.loads(r.read())
        self.tab_id = tab["id"]
        self.base = base
        self.ws = websocket.create_connection(tab["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024, suppress_origin=True)
        self.mid = 0

    def call(self, method: str, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def close(self):
        try:
            self.ws.close()
            urllib.request.urlopen(f"{self.base}/json/close/{self.tab_id}", timeout=5)
        except Exception:
            pass


def render_grid(cdp: CDP, svgs: list[str], cell: int, bg: str) -> Image.Image:
    cols = 10
    rows = (len(svgs) + cols - 1) // cols
    fg = "#e5e7eb" if bg != "white" else "black"  # lucide uses stroke=currentColor
    cells = "".join(
        f'<div style="{CELL_CSS(cell)};background:{bg};color:{fg}">{s}</div>' for s in svgs
    )
    html = f'<html><body style="margin:0"><div style="display:grid;grid-template-columns:repeat({cols},{cell}px);gap:0">{cells}</div></body></html>'
    cdp.call("Emulation.setDeviceMetricsOverride", width=cols * cell, height=rows * cell,
             deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="data:text/html;base64," + base64.b64encode(html.encode()).decode())
    time.sleep(0.4)
    shot = cdp.call("Page.captureScreenshot", format="png")
    return Image.open(io.BytesIO(base64.b64decode(shot["data"])))


def inline_svg(svg_text: str, px: int) -> str:
    # force width/height for deterministic cell render
    import re as _re
    t = _re.sub(r'<svg\b', f'<svg width="{px}" height="{px}"', svg_text, count=1)
    return t


def png_bytes(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def main() -> None:
    family = sys.argv[2] if len(sys.argv) > 2 else "fontawesome"
    fam_root = ROOT / f"dataset/icons/{family}"
    raw_index = json.loads((fam_root / "index.json").read_text())
    index = (raw_index["items"] if isinstance(raw_index, dict) else raw_index)[:OUT_LIMIT]
    cdp = CDP()
    done = 0
    records = []
    batch = 100
    for start in range(0, len(index), batch):
        chunk = index[start:start + batch]
        texts = []
        for rec in chunk:
            p = ROOT / rec["source_svg"]
            if not p.exists():
                continue
            t = p.read_text(encoding="utf8", errors="ignore")
            texts.append((rec, t))
        for px, bgm, bglabel in ((64, "white", "w64"), (128, "white", "w128"), (256, "white", "w256"),
                                 (512, "white", "w512"), (128, "#0b1220", "d128")):
            grid = render_grid(cdp, [inline_svg(t, px // 2) for _, t in texts], px, bgm)
            for k, (rec, _t) in enumerate(texts):
                col, row = k % 10, k // 10
                im = grid.crop((col * px, row * px, col * px + px, row * px + px)).convert("RGBA")
                out = ROOT / rec["source_svg"]
                dest = out.parent / f"input-{bglabel}.png"
                im.save(dest)
                extra = ""
                pair_n = start + k
                if bglabel == "w128" and (BLUR_CAP <= 0 or pair_n < BLUR_CAP):
                    # section-8 conditions on the canonical size; RECORDED in
                    # renders.json so every file on disk is manifest-visible
                    blur = im.filter(ImageFilter.GaussianBlur(1.4))
                    blur.save(out.parent / "input-blur128.png")
                    buf = io.BytesIO()
                    im.convert("RGB").save(buf, "JPEG", quality=30)
                    Image.open(io.BytesIO(buf.getvalue())).convert("RGBA").save(out.parent / "input-jpeg128.png")
                    extra = " +blur +jpeg"
                    records.append({"id": rec["id"], "file": str((out.parent / "input-blur128.png").relative_to(ROOT)),
                                    "condition": "size=128,bg=w128,gaussian-blur-r1.4",
                                    "variant_of": rec["id"] + ":w128"})
                    records.append({"id": rec["id"], "file": str((out.parent / "input-jpeg128.png").relative_to(ROOT)),
                                    "condition": "size=128,bg=w128,jpeg-quality-30",
                                    "variant_of": rec["id"] + ":w128"})
                done += 1
                records.append({"id": rec["id"], "file": str(dest.relative_to(ROOT)), "condition": f"size={px},bg={bglabel}"})
        print(f"rendered batch {start}..{start+len(chunk)-1}: {done} inputs", flush=True)
    (fam_root / "renders.json").write_text(json.dumps(records, indent=1))
    cdp.close()
    print(f"DONE: {done} input.png renders for {len(index)} pairs ({family})")


if __name__ == "__main__":
    main()
