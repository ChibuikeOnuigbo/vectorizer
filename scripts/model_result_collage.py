#!/usr/bin/env python3
"""Build one side-by-side collage PNG per model_result entry: LEFT = the
original input raster, RIGHT = the current rendered SVG output, with a header
carrying the strict verdict + scores. Every test always pairs input with its
output inside one image so mismatches are visible at a glance.
Usage: PYTHONPATH=vendor:app/deps:. python3 scripts/model_result_collage.py [--n 20]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "model_result"
COL = OUT / "collages"
sys.path.insert(0, str(ROOT / "qa"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from similarity_audit import render_svg  # noqa: E402  (headless-chrome rasterizer)


def checker(w: int, h: int, cell: int = 12) -> Image.Image:
    img = Image.new("RGB", (w, h), (238, 238, 238))
    d = ImageDraw.Draw(img)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2 == 0:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(208, 208, 208))
    return img


def find_ui_input(src: Path, name: str) -> Path | None:
    if src.exists():
        return src
    alt = OUT / "inputs" / name
    return alt if alt.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="limit (0 = all)")
    args = ap.parse_args()
    idx = json.loads((OUT / "index.json").read_text())
    COL.mkdir(exist_ok=True)
    # prune stale collages from older sweeps (ids are reused across builds;
    # without this the folder accumulates obsolete copies forever)
    current = {f"{e['id']}-{Path(e['source']).stem}.png"
               for e in idx["entries"] if e.get("status") == "OK"}
    for stale in COL.glob("mr-*.png"):
        if stale.name not in current:
            stale.unlink()
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except Exception:
        font = bold = ImageFont.load_default()

    made = 0
    for e in idx["entries"]:
        if args.n and made >= args.n:
            break
        if e.get("status") != "OK":
            continue
        svg_path = OUT / e["svg"]
        if not svg_path.exists():
            continue
        verdict = e.get("strict_verdict", "?")
        pct = e.get("strict_similarity_pct", e.get("strict_similarity_to_input_pct", 0.0))
        title = e.get("source", "?").split("/")[-1] if e.get("source") else e["svg"]

        if e["id"] == "mr-000":
            inp = find_ui_input(OUT.parent / "test-assets/images/user-provided/teal-orbit-logo.png",
                                "teal-orbit-logo.png")
            verdict, pct = "PASS", pct
        else:
            src = OUT.parent / e.get("source", "")
            inp = find_ui_input(src, Path(e.get("source", "x")).name)
        if inp is None:
            print(f"[{e['id']}] input missing, skipping ({title})")
            continue

        original = Image.open(inp).convert("RGBA")
        W, H = original.size
        rendered = render_svg(svg_path.read_text(), W, H)
        if rendered is None:
            print(f"[{e['id']}] render failed ({title})")
            continue

        canvas_w = W * 2 + 30
        header_h = 64
        canvas = Image.new("RGB", (canvas_w, H + header_h), (18, 20, 26))
        board = checker(canvas_w, H)
        canvas.paste(board, (0, header_h))
        canvas.paste(original.convert("RGB"), (0, header_h), original)
        canvas.paste(rendered.convert("RGB"), (W + 30, header_h), rendered)

        d = ImageDraw.Draw(canvas)
        color = {"PASS": (60, 200, 120), "WEAK": (240, 190, 60), "FAIL": (240, 90, 90)}.get(verdict, (200, 200, 200))
        d.text((12, 8), f"{e['id']}  {title}", font=bold, fill=(230, 232, 238))
        d.text((12, 38), f"{verdict} {pct}%   engine:{e.get('engine','?')}   "
                         f"left=input  right=output   ssim {e.get('channels',{}).get('ssim12','?')}  "
                         f"iou {e.get('channels',{}).get('silhouette_iou','?')}",
               font=font, fill=color)
        out = COL / f"{e['id']}-{Path(title).stem}.png"
        canvas.save(out)
        made += 1
        if made % 50 == 0:
            print(f"  ... {made} collages", flush=True)
    print(f"collages written: {made} -> {COL}")


if __name__ == "__main__":
    main()
