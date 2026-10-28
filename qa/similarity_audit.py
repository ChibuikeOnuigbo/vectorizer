"""Fine-grained similarity audit: input PNG vs vectorizer SVG outputs.

The trained scorer (model.svg_geom, sample step 6) is a fast RELATIVE metric;
user evidence showed it inflates to ~100 on simplified outputs. This audit is
the strict, fine-grained counterpart (proper test, per user demand):

 * renders each SVG at the INPUT's own resolution (Chromium/CDP)
 * composites onto the input's background style
 * computes: per-pixel RGB MAE, block-SSIM12 mean, alpha-silhouette IoU,
   mid-frequency ridge recall (midfreq_rec50, calibrated 2026-10-10:
   closes the measured 12-64px judge blind spot, evidence/midfreq-judge),
   edge F1 (Sobel endpoints, diagnostic only), and a conservative
   similarity% = 100 * min(f(MAE), f(SSIM), IoU, midfreq_rec50)
   [the minimal channel agreement]

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

    def _once() -> Image.Image:
        cdp = CDP()
        html = f'<html><body style="margin:0"><div style="width:{w}px;height:{h}px">{svg}</div></body></html>'
        cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        if len(html) > 1_500_000:
            # data-URL navigations die silently at multi-MB lengths
            # (measured 2026-10-10: castle 4.8MB and pin 2.4MB html -> blank
            # canvas, iou 0 / mae 100-185). setDocumentContent carries the
            # payload in the CDP message itself (ws max_size 64MB).
            cdp.call("Page.navigate", url="about:blank")
            tree = cdp.call("Page.getFrameTree")
            cdp.call("Page.setDocumentContent", frameId=tree["frameTree"]["frame"]["id"], html=html)
        else:
            cdp.call("Page.navigate", url="data:text/html;base64," + base64.b64encode(html.encode()).decode())
        # parse budget scales with payload: multi-MB soft-stack svgs (castle
        # 3.6MB, pin 1.8MB) were screenshotted mid-parse as blank canvas at
        # the fixed 0.4s (measured 2026-10-10: iou 0 / mae 100-185)
        time.sleep(min(3.0, 0.4 + len(svg) / 2e6))
        # transparent compositor background is essential: without it the browser
        # canvas turns the captured PNG fully opaque white and alpha metrics
        # collapse (found on the teal-orbit user logo: 7.7% artifact)
        cdp.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        shot = cdp.call("Page.captureScreenshot", format="png", omitBackground=True)
        cdp.call("Emulation.setDefaultBackgroundColorOverride")
        cdp.close()
        return Image.open(__import__("io").BytesIO(base64.b64decode(shot["data"]))).convert("RGBA")

    im = _once()
    # blank-render retry: a path-heavy svg must never rasterize to a
    # fully-near-white canvas; if it does, the parse raced the capture
    if svg.count("<path") >= 50:
        arr = np.asarray(im)
        lit = arr[..., :3].astype(np.int16) * (arr[..., 3:4] / 255.0) + 255.0 * (1 - arr[..., 3:4] / 255.0)
        if float(lit.mean()) > 250.0:
            time.sleep(0.5)
            im = _once()
    return im


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
    """Simplified windowed SSIM mean over non-overlapping blocks (luma).

    Images smaller than one block (1x1 pixel-art, 1-px-wide strips) used to
    yield an empty window list -> 0.0, tanking strict scores for pixel-
    perfect conversions (mr-003-edge-1x1: mae=0.0/iou=1.0 scored 0.0).
    Fall back to a single whole-image window in that case.

    Normalization fix (2026-10-10, evidence/midfreq-judge): callers pass
    0..255 luma while the constants below were [0,1]-space (c1=1e-4,
    c2=9e-4), collapsing the contrast/structure terms to ~1e-3 whenever a
    block carried real variance -- 1024px soft-gradient icons scored 0.02
    (measured cv-02: true 0.998). Inputs are scaled to [0,1] at entry so the
    constants mean what SSIM says: C1=(0.01*L)^2, C2=(0.03*L)^2 with L=1.
    """
    H, W = a.shape
    if a.dtype != np.float64:
        a = a.astype(np.float64)
    if b.dtype != np.float64:
        b = b.astype(np.float64)
    if float(a.max()) > 1.5 or float(b.max()) > 1.5:
        a = a / 255.0
        b = b / 255.0
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
    if vals:
        return float(np.mean(vals))
    if H > 0 and W > 0 and a.shape == b.shape:
        pa, pb = a.astype(np.float64), b.astype(np.float64)
        mu_a, mu_b = pa.mean(), pb.mean()
        va, vb = pa.var(), pb.var()
        cov = ((pa - mu_a) * (pb - mu_b)).mean()
        n = (2 * mu_a * mu_b + c1) * (2 * cov + c2)
        d = (mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2)
        return float(n / max(d, 1e-12))
    return 0.0


def midfreq_rec(flat_a: np.ndarray, flat_b: np.ndarray, grid: int = 128) -> float:
    """Mid-frequency structural-fidelity channel (2026-10-10, calibration in
    evidence/midfreq-judge): closes the measured 12-64px judge blind spot
    (x2-07 28px face merges scored judge-96.2 while visually merged; cv-01
    shading-interior drop at ssim .967; cv-09 band invention). Rejected
    candidates measured in the same calibration: unweighted recall/F1
    (bg-mottle confound -> icon-02 clean 0.433), NCC of gradient/std energy
    fields (-0.10 margin), energy ratio (-0.54 margin).

    Winner (only positive-margin variant of the honest family): on a fixed
    128px LANCZOS grid, take per-channel |grad| maps, max over RGB
    (melt-share guard: hue-swap edges share luminance), mask input ridges at
    0.5*mean amplitude, and compute AMPLITUDE-WEIGHTED RECALL of the input
    ridges in the output (1-cell dilation tolerance). p=1 (linear) weighting
    is the measured physics, not a fluke: p=2 collapses to weak_max 0.995
    because merged rows preserve their dominant*outer* outline.
    Separation: blind-weak 0.816..0.953 | clean 0.961..1.000 | gray
    0.985..1.000 (margin +0.008 -- a mild honest tug inside the min()
    composite, ~1-3 pts on flagged rows; x2-08-class sub-band texture loss
    is out of scope by design)."""
    from PIL import Image as _Im
    ga = np.asarray(_Im.fromarray(flat_a.astype(np.uint8)).resize((grid, grid), _Im.LANCZOS), dtype=np.float32)
    gb = np.asarray(_Im.fromarray(flat_b.astype(np.uint8)).resize((grid, grid), _Im.LANCZOS), dtype=np.float32)
    def gmag(x: np.ndarray) -> np.ndarray:
        m = None
        for c in range(3):
            gx = np.abs(np.diff(x[..., c], axis=1, prepend=x[:, :1, c]))
            gy = np.abs(np.diff(x[..., c], axis=0, prepend=x[:1, :, c]))
            g = gx + gy
            m = g if m is None else np.maximum(m, g)
        return m
    ea, eb = gmag(ga), gmag(gb)
    ta = max(1e-6, 0.50 * float(ea.mean()))
    tb = max(1e-6, 0.50 * float(eb.mean()))
    ma, mb = ea > ta, eb > tb
    if not ma.any():
        return 1.0
    db = _dilate1(mb)
    w = ea * ma
    tot = float(w.sum())
    if tot < 1e-9:
        return 1.0
    missed = float((w * ~db).sum())
    return max(0.0, min(1.0, 1.0 - missed / tot))


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
        mfr = midfreq_rec(rgb_in.astype(np.float32), rgb_g.astype(np.float32))
        f_mae = max(0.0, 1.0 - mae / 255.0)
        sim = round(100.0 * min(f_mae, ssim, iou, mfr), 1)
        verdict = "PASS" if sim >= 85 else ("WEAK" if sim >= 70 else "FAIL")
        results["engines"][name] = {
            "visual_similarity_pct": sim, "verdict": verdict,
            "mae": round(mae, 2), "ssim12": round(ssim, 4),
            "silhouette_iou": round(iou, 4), "edge_f1": round(ef1, 4),
            "midfreq_rec50": round(mfr, 4),
            "channel_notes": {
                "f_mae": round(f_mae, 4),
                "note": "similarity = min(f_mae, ssim12, silhouette_iou, midfreq_rec50) * 100; edge_f1 diagnostic only; midfreq_rec50 calibrated 2026-10-10 (evidence/midfreq-judge)",
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
