"""Image feature vector for the smart-model parameter predictor.

The SAME feature definition is implemented in app/static/app.js
(computeFeatures) — keep the two in sync. Everything is computed from a
16x16 RGBA stretch of the image plus a handful of global stats, so the
browser (canvas) and python (PIL) produce near-identical vectors.

Feature layout (float32, total FEATURE_DIM):
  [0:1024]     16x16 RGBA pixels stretched, /255
  [1024:1027]  mean RGB over content pixels (alpha > 0.5)
  [1027:1030]  std of RGB over ALL pixels
  [1030]       content fraction (alpha > 0.5)
  [1031:1043]  hue bin presence: 12 bins, 1 if >= 2% of content pixels fall in bin
  [1043]       mean saturation over content pixels
  [1044]       alpha edge density: mean |d(alpha)| on the 16x16 grid, /1.0 clipped
  [1045]       distinct 4-bit colors in the 16x16 block (r,g,b,a // 16) / 256 clipped
  [1046]       luma gradient magnitude over content, /1.5 clipped
"""
from __future__ import annotations

import numpy as np
from PIL import Image

FEATURE_DIM = 1047
N = 16


def _rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """rgb: (...,3) float 0..1 -> hsv (...,3) h in 0..1."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    h = np.zeros_like(d)
    mask = d > 0
    mr = mask & (mx == r)
    mg = mask & (mx == g) & ~mr
    mb = mask & ~mr & ~mg
    h[mr] = ((g[mr] - b[mr]) / d[mr]) % 6
    h[mg] = ((b[mg] - r[mg]) / d[mg]) + 2
    h[mb] = ((r[mb] - g[mb]) / d[mb]) + 4
    h = (h / 6) % 1
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
    v = mx
    return np.stack([h, s, v], axis=-1)


def image_features(img: Image.Image) -> np.ndarray:
    """Compute the shared feature vector for an RGBA image."""
    small = img.convert("RGBA").resize((N, N), Image.BILINEAR)
    p = np.asarray(small, dtype=np.float32) / 255.0
    out = np.empty(FEATURE_DIM, dtype=np.float32)
    out[0:1024] = p.reshape(-1)

    m = p[..., 3] > 0.5
    rgb = p[..., :3]
    if m.any():
        content = rgb[m]
    else:
        content = np.zeros((1, 3), dtype=np.float32)
    out[1024:1027] = content.mean(axis=0)
    out[1027:1030] = rgb.std(axis=(0, 1))
    out[1030] = m.mean()

    hsv = _rgb_to_hsv(rgb)
    if m.any():
        hues = hsv[..., 0][m]
        sats = hsv[..., 1][m]
    else:
        hues = np.zeros(1, dtype=np.float32)
        sats = np.zeros(1, dtype=np.float32)
    hist, _ = np.histogram(hues, bins=12, range=(0.0, 1.0))
    frac = hist / max(1, len(hues))
    out[1031:1043] = (frac >= 0.02).astype(np.float32)
    out[1043] = sats.mean()

    a = p[..., 3]
    edge = np.abs(np.roll(a, -1, axis=1) - a) + np.abs(np.roll(a, -1, axis=0) - a)
    out[1044] = min(1.0, float(edge.mean()))

    key = (p[..., 0] * 15).astype(np.int32) << 12 | (p[..., 1] * 15).astype(np.int32) << 8 | \
          (p[..., 2] * 15).astype(np.int32) << 4 | p[..., 3].astype(np.int32)
    out[1045] = min(1.0, len(np.unique(key)) / 256.0)

    luma = rgb.mean(axis=-1)
    gx = np.abs(np.roll(luma, -1, axis=1) - luma)
    gy = np.abs(np.roll(luma, -1, axis=0) - luma)
    if m.any():
        out[1046] = min(1.0, float(np.maximum(gx, gy)[m].mean()) / 1.5)
    else:
        out[1046] = 0.0
    return out


def params_to_targets(p: dict) -> np.ndarray:
    """Concrete vtracer params -> normalized target vector (5)."""
    return np.array([
        1.0 if p["profile"] == "flat" else 0.0,
        (p["color_precision"] - 1) / 7.0,
        (p["layer_difference"] - 6) / 34.0,
        np.log2(max(1, p["filter_speckle"])) / 3.0,
        (p["max_iterations"] - 8) / 40.0,
    ], dtype=np.float32)


def targets_to_params(y: np.ndarray) -> dict:
    """Normalized model output (5) -> concrete vtracer params (clamped)."""
    y = np.clip(y, 0.0, 1.0)
    profile = "flat" if y[0] > 0.5 else "photo"
    cp = int(round(1 + y[1] * 7))
    ld = int(round(6 + y[2] * 34))
    sp = int(2 ** round(y[3] * 3))
    mi = int(round(8 + y[4] * 40))
    return {
        "profile": profile,
        "color_precision": int(np.clip(cp, 1, 8)),
        "layer_difference": int(np.clip(ld, 6, 40)),
        "filter_speckle": int(np.clip(sp, 1, 8)),
        "max_iterations": int(np.clip(mi, 8, 48)),
    }
