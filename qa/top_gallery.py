"""Compose the TOP-10 vectorization gallery from the live proof report.

Top-10 rows by model pixel score (ties broken by filename). For each row the
strip shows: INPUT raster | MODEL-mode SVG output | CLASSIC-mode SVG output,
rendered deterministically through headless Chromium (same CDP renderer as
the icon harness) and captioned with the real scores from
app/static/testreport/report.json. Evidence-only: no fabricated tiles; the
JSON index records exactly which report row each tile came from.

  PYTHONPATH=vendor:app/deps:. python3 qa/top_gallery.py
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts/dataset"))
from render_pairs import CDP, inline_svg, png_bytes  # shared render backbone

from PIL import Image, ImageDraw, ImageFont

REPORT = ROOT / "app/static/testreport/report.json"
OUTDIR = ROOT / "qa/screenshots/top10"
TOPN = 10
TILE = 320
PAD = 8
LBL_H = 44


def load_font(sz: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def render_svgs(cdp: CDP, svg_paths: list[Path], px: int) -> list[Image.Image]:
    """Render a row of SVGs in one grid screenshot (10 cols)."""
    texts = [p.read_text(encoding="utf8", errors="ignore") for p in svg_paths]
    frame = f'<div style="width:{px}px;height:{px}px;display:flex;align-items:center;justify-content:center"><!--c--></div>'
    cells = []
    for t in texts:
        html_cell = inline_svg(t, px)
        cells.append(f'<div style="width:{px}px;height:{px}px">{html_cell}</div>')
    n = len(cells)
    import base64 as b64
    html = (f'<html><body style="margin:0;font-family:sans-serif"><div style="display:grid;'
            f'grid-template-columns:repeat({n},{px}px);gap:0">' + "".join(cells) + "</div></body></html>")
    cdp.call("Emulation.setDeviceMetricsOverride", width=px * n, height=px,
             deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="data:text/html;base64," + b64.b64encode(html.encode()).decode())
    import time
    time.sleep(0.5)
    shot = cdp.call("Page.captureScreenshot", format="png")
    full = Image.open(io.BytesIO(b64.b64decode(shot["data"]))).convert("RGBA")
    return [full.crop((k * px, 0, k * px + px, px)) for k in range(n)]


def opaque_frac(path: Path) -> float:
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A")
    bp = a.getbbox()
    if not bp:
        return 0.0
    hist = a.histogram()
    return sum(hist[9:]) / (im.width * im.height)


def _prepare_rows() -> list:
    rows = json.loads(REPORT.read_text())["rows"]
    trep = ROOT / "app/static/testreport"
    for r in rows:
        r["_opaque"] = opaque_frac(trep / f"in_{int(r['i']):03d}.png")
    return rows


def build_gallery(top: list, png_name: str, json_name: str) -> None:
    trep = ROOT / "app/static/testreport"
    cdp = CDP()
    m_tiles = render_svgs(cdp, [trep / f"m_{r['i']:03d}.svg" for r in top], TILE - PAD * 2)
    c_tiles = render_svgs(cdp, [trep / f"c_{r['i']:03d}.svg" for r in top], TILE - PAD * 2)
    cdp.close()

    row_h = TILE + LBL_H
    art = Image.new("RGB", (TILE * 3, row_h * TOPN), (255, 255, 255))
    dr = ImageDraw.Draw(art)
    f_lbl = load_font(15)
    f_hd = load_font(16)
    dr.text((PAD, 2), "INPUT", fill=(0, 0, 0), font=f_hd)
    dr.text((TILE + PAD, 2), "MODEL output", fill=(0, 0, 0), font=f_hd)
    dr.text((2 * TILE + PAD, 2), "CLASSIC output", fill=(0, 0, 0), font=f_hd)

    gallery_index = []
    for k, r in enumerate(top):
        i = int(r["i"])
        name = r["name"]
        y = k * row_h
        # input: letterboxed to tile
        inp = Image.open(trep / f"in_{i:03d}.png").convert("RGBA")
        inp.thumbnail((TILE - PAD * 2, TILE - PAD * 2), Image.LANCZOS)
        card = Image.new("RGB", (TILE, TILE), (245, 247, 250))
        cx = (TILE - inp.width) // 2
        cy = (TILE - inp.height) // 2
        card.paste(inp, (cx, cy), inp)
        art.paste(card, (0, y))
        for col, tile in ((1, m_tiles[k]), (2, c_tiles[k])):
            s_card = Image.new("RGB", (TILE, TILE), (245, 247, 250))
            tw = TILE - PAD * 2
            t2 = tile.copy()
            t2.thumbnail((tw, tw), Image.LANCZOS)
            s_card.paste(t2, ((TILE - t2.width) // 2, (TILE - t2.height) // 2), t2)
            art.paste(s_card, (col * TILE, y))
        dr.text((PAD, y + TILE + 4), f"#{k + 1}  {name}", fill=(17, 24, 39), font=f_lbl)
        dr.text((TILE + PAD, y + TILE + 4),
                f"model score {r['m_score']}%  ·  {r['m_paths']} paths · {r['m_kb']} KB",
                fill=(17, 24, 39), font=f_lbl)
        dr.text((2 * TILE + PAD, y + TILE + 4),
                f"classic score {r['c_score']}%  ·  {r['c_paths']} paths · {r['c_kb']} KB",
                fill=(17, 24, 39), font=f_lbl)
        gallery_index.append({
            "rank": k + 1, "report_row": i, "name": name,
            "input": f"app/static/testreport/in_{i:03d}.png",
            "model_svg": f"app/static/testreport/m_{i:03d}.svg",
            "classic_svg": f"app/static/testreport/c_{i:03d}.svg",
            "opaque_frac": round(r["_opaque"], 4),
            "empty_canvas_risk": bool(r["_opaque"] < 0.01),
            "m_score": r["m_score"], "c_score": r["c_score"],
            "m_paths": r["m_paths"], "c_paths": r["c_paths"],
            "m_kb": r["m_kb"], "c_kb": r["c_kb"],
        })

    png = OUTDIR / png_name
    art.save(png)
    (OUTDIR / json_name).write_text(json.dumps({
        "source": "app/static/testreport/report.json (100-image proof report, live app outputs)",
        "rule": "top-10 rows by model score, ties by name" + (" + opaque>=1% (excludes empty-canvas degenerate matches)" if "core" in png_name else ""),
        "gallery": f"qa/screenshots/top10/{png_name}",
        "tiles": gallery_index,
    }, indent=1))
    assert png.stat().st_size > 50_000, png.stat().st_size
    print(f"gallery: {png.relative_to(ROOT)} ({png.stat().st_size // 1024} KB) for "
          f"{[t['name'] for t in gallery_index]}")


def main() -> None:
    rows = _prepare_rows()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    top = sorted(rows, key=lambda r: (-(r["m_score"] or 0), r["name"]))[:TOPN]
    build_gallery(top, "top10_gallery.png", "index.json")
    top_core = [r for r in sorted(rows, key=lambda r: (-(r["m_score"] or 0), r["name"]))
                if r["_opaque"] >= 0.01][:TOPN]
    build_gallery(top_core, "top10_gallery_core.png", "index_core.json")


if __name__ == "__main__":
    main()
