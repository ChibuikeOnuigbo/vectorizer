"""Pure-numpy SVG path geometry: flatten beziers, test point coverage,
and score a vectorized SVG against its original raster.

The single composite number in score() is the training reward:
    score = 100 * (0.50 * coverage + 0.20 * precision + 0.30 * color_term)
coverage  = fraction of interior solid pixels of the original that some
            vector path covers (holes hurt this)
precision = fraction of covered pixels that are not clearly outside the
            original (edge overflow / halo hurts this)
color_term = 1 - clipped mean per-channel color error at covered pixels
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

_PATH_RE = re.compile(r"<path\s[^>]*/?>")
_D_RE = re.compile(r'\bd="([^"]+)"')
_FILL_RE = re.compile(r'\bfill="(#[0-9A-Fa-f]{6})"')
_TF_RE = re.compile(r'\btransform="([^"]+)"')
_TR_RE = re.compile(r"translate\(\s*([-\d.]+(?:e[-+]?\d+)?)\s*[,]\s*([-\d.]+(?:e[-+]?\d+)?)\s*\)")
_SC_RE = re.compile(r"scale\(\s*([-\d.]+(?:e[-+]?\d+)?)\s*\)")
_CMD_RE = re.compile(r"([MLCQZmlcqz])|(-?\d*\.?\d+(?:[eE]-?\d+)?|-?\d+\.?)")


@dataclass
class VecPath:
    fill: tuple
    subpaths: list = field(default_factory=list)  # list of (n,2) float32 arrays


def _flatten_cubic(p0, p1, p2, p3, steps=10):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _flatten_quad(p0, c, p1, steps=6):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]))
    return pts


def _tokenize_d(d: str):
    """Yield (cmd, [numbers...]) groups for a path data string."""
    out = []
    cur_cmd = None
    nums = []
    for m in _CMD_RE.finditer(d):
        if m.group(1):
            if cur_cmd is not None and nums:
                out.append((cur_cmd, nums))
                nums = []
            cur_cmd = m.group(1)
        else:
            nums.append(float(m.group(2)))
    if cur_cmd is not None and nums:
        out.append((cur_cmd, nums))
    return out


def parse_svg_paths(svg: str) -> list:
    """Parse my tidy SVG format into VecPath objects (document order).

    Supports absolute and relative M, L, C, Q, Z.
    """
    out = []
    for m in _PATH_RE.finditer(svg):
        tag = m.group(0)
        dm = _D_RE.search(tag)
        fm = _FILL_RE.search(tag)
        if not dm or not fm:
            continue
        r, g, b = (int(fm.group(1)[i:i + 2], 16) for i in (1, 3, 5))
        # vtracer cutout mode places each layer in a local coordinate system
        # with transform="translate(tx,ty)" (sometimes with a scale). Apply it.
        tx = ty = 0.0
        sc = 1.0
        tfm = _TF_RE.search(tag)
        if tfm:
            trm = _TR_RE.search(tfm.group(1))
            if trm:
                tx, ty = float(trm.group(1)), float(trm.group(2))
            scm = _SC_RE.search(tfm.group(1))
            if scm:
                sc = float(scm.group(1))
        subpaths, pts = [], []
        x = y = 0.0
        start = (0.0, 0.0)
        for cmd, nums in _tokenize_d(dm.group(1)):
            i = 0
            low = cmd.lower()
            while i < len(nums):
                if low == "m":
                    if i < len(nums) - 2 and cmd == "M":
                        px, py = nums[i], nums[i + 1]
                    else:  # relative
                        px, py = x + nums[i], y + nums[i + 1]
                    x, y = px, py
                    if len(pts) > 1:
                        subpaths.append(np.array(pts, dtype=np.float32))
                    pts = [(x, y)]
                    start = (x, y)
                    i += 2
                elif low == "l":
                    if cmd == "L":
                        x, y = nums[i], nums[i + 1]
                    else:
                        x += nums[i]
                        y += nums[i + 1]
                    pts.append((x, y))
                    i += 2
                elif low == "c":
                    if cmd == "C":
                        c1, c2, p = (nums[i], nums[i + 1]), (nums[i + 2], nums[i + 3]), (nums[i + 4], nums[i + 5])
                    else:
                        c1 = (x + nums[i], y + nums[i + 1])
                        c2 = (x + nums[i + 2], y + nums[i + 3])
                        p = (x + nums[i + 4], y + nums[i + 5])
                    pts.extend(_flatten_cubic((x, y), c1, c2, p))
                    x, y = p
                    pts.append((x, y))
                    i += 6
                elif low == "q":
                    if cmd == "Q":
                        c, p = (nums[i], nums[i + 1]), (nums[i + 2], nums[i + 3])
                    else:
                        c = (x + nums[i], y + nums[i + 1])
                        p = (x + nums[i + 2], y + nums[i + 3])
                    pts.extend(_flatten_quad((x, y), c, p))
                    x, y = p
                    pts.append((x, y))
                    i += 4
                elif low == "z":
                    if len(pts) > 1:
                        subpaths.append(np.array(pts, dtype=np.float32))
                    pts = []
                    x, y = start
                    i += 1
                else:
                    i += 1
        if len(pts) > 1:
            subpaths.append(np.array(pts, dtype=np.float32))
        if subpaths:
            if tx or ty or sc != 1.0:
                off = np.array([tx, ty], dtype=np.float32)
                subpaths = [poly * sc + off for poly in subpaths]
            out.append(VecPath(fill=(r, g, b), subpaths=subpaths))
    return out


def _inside_poly(q: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Even-odd point-in-polygon, vectorized. q: (M,2), p: (N,2)."""
    a = p
    b = np.roll(p, -1, axis=0)
    qy, qx = q[:, 1:2], q[:, 0:1]          # (M,1)
    ay, by = a[:, 1].reshape(1, -1), b[:, 1].reshape(1, -1)  # (1,N)
    ax, bx = a[:, 0].reshape(1, -1), b[:, 0].reshape(1, -1)  # (1,N)
    cond1 = (ay > qy) != (by > qy)         # (M,N)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = (bx - ax) * (qy - ay) / np.where(by - ay == 0, 1e-12, by - ay) + ax
    cond2 = qx < xint
    return ((cond1 & cond2).sum(axis=1) % 2).astype(bool)


def cover_mask(paths: list, w: int, h: int, step: int = 4):
    """Return (cover (h/step, w/step) bool, top color idx per covered pixel).

    Document order = draw order; the LAST path covering a pixel wins its color.
    """
    gh, gw = h // step, w // step
    ys, xs = np.mgrid[0:gh, 0:gw]
    pts = np.stack([xs.ravel() * step + step / 2, ys.ravel() * step + step / 2],
                   axis=1).astype(np.float32)
    color = np.full(pts.shape[0], -1, dtype=np.int32)
    for idx, vp in enumerate(paths):
        for poly in vp.subpaths:
            bx0 = max(0, int(poly[:, 0].min()) // step - 1)
            by0 = max(0, int(poly[:, 1].min()) // step - 1)
            bx1 = min(gw, int(poly[:, 0].max()) // step + 2)
            by1 = min(gh, int(poly[:, 1].max()) // step + 2)
            if bx0 >= bx1 or by0 >= by1:
                continue
            sel = (xs >= bx0) & (xs < bx1) & (ys >= by0) & (ys < by1)
            sub = pts[sel.ravel()]
            if sub.shape[0] == 0:
                continue
            inside = _inside_poly(sub, poly)
            if not inside.any():
                continue
            where = sel.ravel().nonzero()[0][inside]
            color[where] = idx  # later paths overwrite -> topmost
    cover = color >= 0
    return cover.reshape(gh, gw), color.reshape(gh, gw)


def score(original: Image.Image, svg: str, step: int = 4) -> dict:
    """Composite 0-100 perfection score of svg vs original raster."""
    original = original.convert("RGBA")
    w, h = original.size
    gh, gw = h // step, w // step
    a_small = np.asarray(original.getchannel("A").resize((gw, gh), Image.NEAREST),
                         dtype=np.uint8)
    solid = a_small > 128
    nbrs = (np.roll(solid, -1, 0) & np.roll(solid, 1, 0)
            & np.roll(solid, -1, 1) & np.roll(solid, 1, 1))
    interior = solid & nbrs
    near = solid.copy()
    for _ in range(3):
        near = (near | np.roll(near, -1, 0) | np.roll(near, 1, 0)
                | np.roll(near, -1, 1) | np.roll(near, 1, 1))
    outside = (a_small <= 20) & ~near

    paths = parse_svg_paths(svg)
    cover, cidx = cover_mask(paths, w, h, step=step)
    fill_cols = np.array([vp.fill for vp in paths], dtype=np.float32)

    n_int = int(interior.sum())
    if n_int == 0:
        return {"coverage": 1.0, "precision": 1.0, "color_err": 0.0,
                "score": 100.0, "paths": len(paths)}
    coverage = float((cover & interior).sum()) / n_int

    n_cov = int(cover.sum())
    if n_cov == 0:
        return {"coverage": 0.0, "precision": 1.0, "color_err": 255.0,
                "score": 0.0, "paths": len(paths)}
    precision = 1.0 - float((cover & outside).sum()) / n_cov

    rg_small = np.asarray(original.convert("RGB").resize((gw, gh), Image.NEAREST),
                          dtype=np.float32)
    mask = cover & interior
    if mask.any():
        top = fill_cols[np.clip(cidx[mask], 0, len(fill_cols) - 1)]
        err = float(np.abs(top - rg_small[mask]).mean())
    else:
        err = 255.0
    color_term = 1.0 - min(err, 60.0) / 60.0
    s = 100.0 * (0.50 * coverage + 0.20 * precision + 0.30 * color_term)
    return {"coverage": round(coverage, 4), "precision": round(precision, 4),
            "color_err": round(err, 2), "score": round(float(s), 2),
            "paths": len(paths)}
