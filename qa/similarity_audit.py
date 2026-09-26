"""Fine-grained similarity audit: input PNG vs vectorizer SVG outputs.

The trained scorer (model.svg_geom, sample step 6) is a fast RELATIVE metric;
user evidence showed it inflates to ~100 on simplified outputs. This audit is
the strict, fine-grained counterpart (proper test, per user demand):

 * renders each SVG at the INPUT's own resolution (Chromium/CDP)
 * composites onto the input's background style
 * computes: per-pixel RGB MAE, block-SSIM12 mean, alpha-silhouette IoU,
   edge F1 (Sobel endpoints), and a conservative similarity% =
   100 * min(f(MAE), f(SSIM), IoU)  [the minimal channel agreement]

Verdict:  similarity >= 85 -> PASS;  70-85 -> WEAK;  < 70 -> FAIL
No score is ever padded: a 5-path blur-average simplification of a complex
logo CANNOT score 95+ here.

  PYTHONPATH=vendor:app/deps:. python3 qa/similarity_audit.py <input.png> [--svg x.svg ...] [--out qa/audits/<name>]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts/dataset"))
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT / "app/deps"))

from render_pairs import CDP  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402


def render_svg(svg: str, w: int, h: int) -> Image.Image:
    import base64
    cdp = CDP()
    html = f'<html><body style="margin:0"><div style="width:{w}px;height:{h}px">{svg}</div></body></html>'
    cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="data:text/html;base64," + base64.b64encode(html.encode()).decode())
    time.sleep(0.4)
    # transparent compositor background is essential: without it the browser
    # canvas turns the captured PNG fully opaque white and alpha metrics
    # collapse (found on the teal-orbit user logo: 7.7% artifact)
    cdp.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
    shot = cdp.call("Page.captureScreenshot", format="png", omitBackground=True)
    cdp.call("Emulation.setDefaultBackgroundColorOverride")
    cdp.close()
    return Image.open(__import__("io").BytesIO(base64.b64decode(shot["data"]))).convert("RGBA")


def _to_png_bytes(im: Image.Image) -> bytes:
    import io
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def bg_flat(im: Image.Image, rgb=(255, 255, 255)) -> Image.Image:
    flat = Image.new("RGBA", im.size, rgb + (255,))
    flat.paste(im, (0, 0), im)
    return flat


def ssim_block(a: np.ndarray, b: np.ndarray, block: int = 12) -> float:
    """Simplified windowed SSIM mean over non-overlapping blocks (luma)."""
    H, W = a.shape
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    vals = []
    for y in range(0, H - block + 1, block):
        for x in range(0, W - block + 1, block):
            pa = a[y:y + block, x:x + block].astype(np.float64)
            pb = b[y:y + block, x:x + block].astype(np.float64)
            mu_a, mu_b = pa.mean(), pb.mean()
            va, vb = pa.var(), pb.var()
            cov = ((pa - mu_a) * (pb - mu_b)).mean()
            n = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
            d = (mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2)
            vals.append(n / max(d, 1e-12))
    return float(np.mean(vals)) if vals else 0.0


def edge_map(g: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    return (gx + gy) > 40


def _dilate1(m: np.ndarray) -> np.ndarray:
    out = m.copy()
    out[1:, :] |= m[:-1, :]
    out[:-1, :] |= m[1:, :]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    return out


def edge_f1(a: np.ndarray, b: np.ndarray, tol_px: int = 1) -> float:
    """Edge-overlap F1 with +-tol_px geometric tolerance (ring-thin strokes
    would otherwise score ~0 under a 1-2px renderer offset)."""
    ea, eb = edge_map(a), edge_map(b)
    for _ in range(max(0, tol_px)):
        ea_d, eb_d = _dilate1(ea), _dilate1(eb)
        ea, eb = ea_d, eb_d
    tp = int((ea & eb).sum())
    fp = int((~ea & eb).sum())
    fn = int((ea & ~eb).sum())
    if tp + fp + fn == 0:
        return 1.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def audit(input_path: str, svgs: dict[str, str], out_dir: str | None = None,
          save_composite: bool = True) -> dict:
    inp = Image.open(input_path).convert("RGBA")
    W, H = inp.size
    flat_in = bg_flat(inp)
    gi = np.asarray(flat_in.convert("L"), dtype=np.float32)
    ai = np.asarray(inp.split()[3], dtype=np.int16)
    sil_in = ai > 14
    rgb_in = np.asarray(flat_in.convert("RGB"), dtype=np.int16)

    results = {"input": input_path, "size": [W, H], "engines": {}}
    tiles = [flat_in]
    labels = ["INPUT"]
    for name, svg in svgs.items():
        if not svg.strip():
            results["engines"][name] = {"error": "empty svg"}
            tiles.append(Image.new("RGB", (W, H), (255, 255, 255)))
            labels.append(name + " (empty)")
            continue
        gen = render_svg(svg, W, H)
        flat_g = bg_flat(gen)
        gg = np.asarray(flat_g.convert("L"), dtype=np.float32)
        ag = np.asarray(gen.split()[3], dtype=np.int16)
        sil_g = ag > 14
        rgb_g = np.asarray(flat_g.convert("RGB"), dtype=np.int16)

        mae = float(np.abs(rgb_in - rgb_g).mean())
        ssim = ssim_block(gi, gg)
        inter = int((sil_in & sil_g).sum())
        union = int((sil_in | sil_g).sum())
        iou = inter / union if union else 1.0
        ef1 = edge_f1(gi, gg)
        f_mae = max(0.0, 1.0 - mae / 255.0)
        sim = round(100.0 * min(f_mae, ssim, iou), 1)
        verdict = "PASS" if sim >= 85 else ("WEAK" if sim >= 70 else "FAIL")
        results["engines"][name] = {
            "visual_similarity_pct": sim, "verdict": verdict,
            "mae": round(mae, 2), "ssim12": round(ssim, 4),
            "silhouette_iou": round(iou, 4), "edge_f1": round(ef1, 4),
            "channel_notes": {
                "f_mae": round(f_mae, 4),
                "note": "similarity = min(f_mae, ssim12, silhouette_iou) * 100; edge_f1 diagnostic only",
            },
            "svg_bytes": len(svg.encode()),
        }
        tiles.append(flat_g)
        labels.append(f"{name}: {sim}%{verdict}")

    if save_composite and out_dir:
        td = ROOT / out_dir
        td.mkdir(parents=True, exist_ok=True)
        strip = Image.new("RGB", (W * len(tiles), H + 30), (255, 255, 255))
        from PIL import ImageDraw
        dr = ImageDraw.Draw(strip)
        for k, (tl, lb) in enumerate(zip(tiles, labels)):
            strip.paste(tl.convert("RGB"), (k * W, 0))
            dr.text((k * W + 10, H + 6), lb, fill=(0, 0, 0))
        out_png = td / (Path(input_path).stem + "_similarity.png")
        strip.save(out_png)
        results["composite"] = str(out_png.relative_to(ROOT))
        (td / (Path(input_path).stem + "_similarity.json")).write_text(json.dumps(results, indent=1))
    return results


if __name__ == "__main__":
    args = sys.argv[1:]
    inp = args.pop(0)
    svgs: dict[str, str] = {}
    out = None
    i = 0
    while i < len(args):
        if args[i] == "--svg":
            svgs[Path(args[i + 1]).stem] = Path(args[i + 1]).read_text()
            i += 2
        elif args[i] == "--out":
            out = args[i + 1]
            i += 2
        else:
            i += 1
    print(json.dumps(audit(inp, svgs, out), indent=1)[:2000])
