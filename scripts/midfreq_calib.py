#!/usr/bin/env python3
"""Calibration run for mid-frequency judge-channel candidates (2026-10-10).

Phase 1 renders each pair once (CDP, transparent), caches flattened RGB
arrays in /tmp/mfcache (harness-volatile only, not committed).
Phase 2 sweeps candidate channels offline on the cached arrays.

Pre-registered clusters from the visual-verdict READMEs:
  blind-weak: rows the old judge scored high while visual review found
    12-64px structure loss (x2-07 face merges, cv-01 shading interiors,
    cv-09 band invention). x2-08 confetti STAYS gray: its loss lives below
    the documented band (<12px) and honest channels must not be tuned to it.
  clean: visually PASS rows.
  gray: weakness not mid-frequency-boundary (texture mush, washed fills,
    mottled bg) -- observed, not threshold-defining.

Run: PYTHONPATH=qa:scripts/dataset:vendor:app/deps python3 scripts/midfreq_calib.py [--sweep-only]
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qa")); sys.path.insert(0, str(ROOT / "scripts/dataset"))
sys.path.insert(0, str(ROOT / "vendor")); sys.path.insert(0, str(ROOT / "app/deps"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

CACHE = Path("/tmp/mfcache")
X2, CV, BG, FIX = "evidence/icon-x2-set", "evidence/curve-cv-set", "evidence/bg-remove-set", "evidence/fix-t3-speckle"

def p(d, i, s): return (f"{ROOT}/{d}/inputs/{i}.png", f"{ROOT}/{d}/svgs/{s}.svg")

PAIRS = [
    ("x2-07-voxel-heart",   *p(X2, "x2-07-voxel-heart", "x2-07-voxel-heart"), "blind-weak"),
    ("cv-01-thick-ribbon",  *p(CV, "cv-01-thick-ribbon-logo", "cv-01-thick-ribbon-logo"), "blind-weak"),
    ("cv-09-grad-ribbon",   *p(CV, "cv-09-gradient-ribbon", "cv-09-gradient-ribbon"), "blind-weak"),
    ("x2-08-holo-badge",    *p(X2, "x2-08-holo-iridescent-badge", "x2-08-holo-iridescent-badge"), "gray"),
    ("cv-02-spiral",        *p(CV, "cv-02-spiral-swirl-logo", "cv-02-spiral-swirl-logo"), "clean"),
    ("cv-03-blobs",         *p(CV, "cv-03-organic-blob-circles", "cv-03-organic-blob-circles"), "clean"),
    ("cv-04-flourish",      *p(CV, "cv-04-calligraphic-flourish", "cv-04-calligraphic-flourish"), "clean"),
    ("cv-05-loops",         *p(CV, "cv-05-interlocking-loops", "cv-05-interlocking-loops"), "clean"),
    ("cv-06-waves",         *p(CV, "cv-06-wave-stack", "cv-06-wave-stack"), "clean"),
    ("cv-07-rings",         *p(CV, "cv-07-rings-ellipses", "cv-07-rings-ellipses"), "clean"),
    ("cv-08-curls",         *p(CV, "cv-08-tight-hooks-swirls", "cv-08-tight-hooks-swirls"), "clean"),
    ("cv-10-glass",         *p(CV, "cv-10-glass-translucent-curves", "cv-10-glass-translucent-curves"), "clean"),
    ("x2-03-anchor",        *p(X2, "x2-03-lineal-color-anchor", "x2-03-lineal-color-anchor"), "clean"),
    ("x2-06-castle",        *p(X2, "x2-06-diorama-game-castle", "x2-06-diorama-game-castle"), "clean"),
    ("icon-01-rocket",      f"{ROOT}/{BG}/inputs/icon-01-rocket-flatbg.png", f"{ROOT}/{FIX}/icon-01-rocket-flatbg.svg", "clean"),
    ("icon-02-leaf",        f"{ROOT}/{BG}/inputs/icon-02-leaf-flatbg.png", f"{ROOT}/{FIX}/icon-02-leaf-flatbg.svg", "clean"),
    ("icon-03-anchor",      f"{ROOT}/{BG}/inputs/icon-03-anchor-flatbg.png", f"{ROOT}/{FIX}/icon-03-anchor-flatbg.svg", "clean"),
    ("x2-02-bee",           *p(X2, "x2-02-sticker-cutout-bee", "x2-02-sticker-cutout-bee"), "gray"),
    ("x2-04-mug",           *p(X2, "x2-04-doodle-crosshatch-mug", "x2-04-doodle-crosshatch-mug"), "gray"),
    ("x2-05-pin",           *p(X2, "x2-05-metallic-pin-lightning", "x2-05-metallic-pin-lightning"), "gray"),
]

def flatten_rgb(im: Image.Image) -> np.ndarray:
    rgba = np.asarray(im.convert("RGBA"), dtype=np.float32)
    a = rgba[..., 3:4] / 255.0
    return rgba[..., :3] * a + 255.0 * (1.0 - a)

def phase_render() -> None:
    from similarity_audit import render_svg
    CACHE.mkdir(exist_ok=True)
    for name, inp, svg_p, _cl in PAIRS:
        f = CACHE / f"{name}.npz"
        if f.exists():
            continue
        im = Image.open(inp)
        gen = render_svg(Path(svg_p).read_text(), *im.size)
        np.savez_compressed(f, a=flatten_rgb(im), b=flatten_rgb(gen))
        print("rendered", name, im.size, "->", f.stat().st_size // 1024, "KB")

def down(x: np.ndarray, grid: int = 128) -> np.ndarray:
    return np.asarray(Image.fromarray(x.astype(np.uint8)).resize((grid, grid), Image.LANCZOS), dtype=np.float32)

def dilate1(m: np.ndarray) -> np.ndarray:
    out = m.copy()
    out[1:, :] |= m[:-1, :]; out[:-1, :] |= m[1:, :]
    out[:, 1:] |= m[:, :-1]; out[:, :-1] |= m[:, 1:]
    return out

def f1_of(ma: np.ndarray, mb: np.ndarray) -> float:
    if not ma.any() and not mb.any():
        return 1.0
    da, db = dilate1(ma), dilate1(mb)
    tp = int((mb & da).sum()); fp = int((mb & ~da).sum()); fn = int((ma & ~db).sum())
    if tp + fp + fn == 0:
        return 1.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)

def box_mean(x: np.ndarray, r: int) -> np.ndarray:
    xp = np.pad(x.astype(np.float64), r, mode="edge")
    ii = np.zeros((xp.shape[0] + 1, xp.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = np.cumsum(np.cumsum(xp, 0), 1)
    w = 2 * r + 1
    return ((ii[w:, w:] - ii[:-w, w:] - ii[w:, :-w] + ii[:-w, :-w]) / (w * w)).astype(np.float32)

def gmag_rgb(x: np.ndarray) -> np.ndarray:
    m = None
    for c in range(3):
        gx = np.abs(np.diff(x[..., c], axis=1, prepend=x[:, :1, c]))
        gy = np.abs(np.diff(x[..., c], axis=0, prepend=x[:1, :, c]))
        m = gx + gy if m is None else np.maximum(m, gx + gy)
    return m.astype(np.float32)

def std_rgb(x: np.ndarray, r: int) -> np.ndarray:
    acc = None
    for c in range(3):
        ch = x[..., c]
        m = box_mean(ch, r)
        var = box_mean(ch * ch, r) - m * m
        sd = np.sqrt(np.maximum(var, 0.0))
        acc = sd if acc is None else np.maximum(acc, sd)
    return acc.astype(np.float32)

def ncc(a: np.ndarray, b: np.ndarray) -> float:
    va, vb = a.ravel() - a.mean(), b.ravel() - b.mean()
    d = float(np.sqrt((va * va).sum() * (vb * vb).sum()))
    return 1.0 if d < 1e-9 else max(0.0, float((va * vb).sum()) / d)

def phase_sweep() -> None:
    rows = []
    for name, _i, _s, cl in PAIRS:
        z = np.load(CACHE / f"{name}.npz")
        ga, gb = down(z["a"]), down(z["b"])
        eA, eB = gmag_rgb(ga), gmag_rgb(gb)
        sA, sB = std_rgb(ga, 2), std_rgb(gb, 2)
        cand = {
            "edgeF1_t30": f1_of(eA > max(1e-6, 0.30 * eA.mean()), eB > max(1e-6, 0.30 * eB.mean())),
            "edgeF1_t50": f1_of(eA > max(1e-6, 0.50 * eA.mean()), eB > max(1e-6, 0.50 * eB.mean())),
            "edgeF1_med": f1_of(eA > max(1e-6, float(np.median(eA) * 1.5)), eB > max(1e-6, float(np.median(eB) * 1.5))),
            "ncc_edge":   ncc(box_mean(eA, 1), box_mean(eB, 1)),
            "stdF1_t25":  f1_of(sA > max(1e-6, 0.25 * sA.mean()), sB > max(1e-6, 0.25 * sB.mean())),
            "ncc_std":    ncc(box_mean(sA, 1), box_mean(sB, 1)),
            "energy_ratio": 1.0 if eA.mean() < 1e-6 else min(1.0, float(eB.mean() / eA.mean())),
        }
        rows.append({"name": name, "cluster": cl, **cand})
        print(f"{name:22s} {cl:10s} " + "  ".join(f"{k}={v:.3f}" for k, v in cand.items()))
    print("\n=== separation (blind-weak vs clean; margin = clean_min - weak_max) ===")
    keys = list(rows[0].keys() - {"name", "cluster"})
    for k in keys:
        weak = [r[k] for r in rows if r["cluster"] == "blind-weak"]
        clean = [r[k] for r in rows if r["cluster"] == "clean"]
        print(f"{k:14s} weak {min(weak):.3f}..{max(weak):.3f} | clean {min(clean):.3f}..{max(clean):.3f} | margin {min(clean)-max(weak):+.3f}")
    Path(ROOT / "evidence/midfreq-judge").mkdir(exist_ok=True)
    Path(ROOT / "evidence/midfreq-judge/calib.json").write_text(json.dumps(rows, indent=1))
    print("wrote evidence/midfreq-judge/calib.json")

if __name__ == "__main__":
    if "--sweep-only" not in sys.argv:
        phase_render()
    phase_sweep()
