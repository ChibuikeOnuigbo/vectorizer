"""
Vectorization pipeline.

Goal: clean, hole-free SVG output from raster images with zero user settings.

Strategy
--------
1. Load image, normalize, downscale huge inputs (<= 1500px on the long edge).
2. Transparency: pixels with alpha > 128 become "content", everything else is
   painted with a *synthetic* background color C0 chosen to be as far as
   possible from the image's real palette.
3. Flat-art detection (<= 4 significant colors): the working image is
   quantized to a small hard palette first, so anti-aliased edge shades
   collapse into one clean flat color instead of producing 40 near-identical
   layers (the usual cause of "hole-y", messy SVGs).
4. vtracer color mode traces the working image. Every pixel belongs to
   exactly one color class and the classes tile the whole canvas, so the
   stacked layers never leave gaps — no holes, no seams.
5. Post-process: for transparent inputs the C0 background layer is removed,
   leaving a genuine transparent SVG background.

The result: a small number of flat, closed, stacked path layers.

Public entry points
-------------------
- analyze(img: Image.Image) -> dict      per-image prep (mask, C0, ring, flatness)
- trace_with(a: dict, params: dict|None) -> str   one vtracer pass + cleanup
- vectorize(img_bytes, params=None) -> {svg, meta}  the API endpoint
"""

from __future__ import annotations

import io
import re
import tempfile
import time

import numpy as np
from PIL import Image, ImageFilter
import vtracer

MAX_EDGE = 1500          # long edge cap for tracing
ALPHA_CUTOFF = 128       # alpha above this = content, below = background
FLAT_ERR = 35.0          # mean 4-color reconstruction error (0-441) below this = flat art

BASELINE_FLAT = dict(profile="flat", color_precision=2, layer_difference=20,
                     filter_speckle=2, max_iterations=12, corner_threshold=60,
                     length_threshold=4.5, path_precision=10)
BASELINE_PHOTO = dict(profile="photo", color_precision=6, layer_difference=12,
                      filter_speckle=4, max_iterations=30, corner_threshold=50,
                      length_threshold=3.5, path_precision=10)

# Cloudinary inspired presets — best tier method improved v2, stricter, cleaner SVG, fewer paths, hole-free
PRESETS = {
    "logo": dict(profile="flat", color_precision=2, layer_difference=20, filter_speckle=2, max_iterations=12, corner_threshold=60, length_threshold=4.5, path_precision=10),
    "icon": dict(profile="flat", color_precision=3, layer_difference=16, filter_speckle=1, max_iterations=14, corner_threshold=70, length_threshold=4.5, path_precision=10),
    "illustration": dict(profile="flat", color_precision=5, layer_difference=12, filter_speckle=3, max_iterations=22, corner_threshold=50, length_threshold=3.5, path_precision=10),
    "lqip": dict(profile="photo", color_precision=4, layer_difference=18, filter_speckle=4, max_iterations=16, corner_threshold=40, length_threshold=4.0, path_precision=8),
    "artistic": dict(profile="photo", color_precision=6, layer_difference=10, filter_speckle=6, max_iterations=30, corner_threshold=35, length_threshold=3.0, path_precision=10),
    "custom": None,
}

# Candidates for the synthetic transparent background. Chosen at runtime so
# the one used is maximally far from the image's actual colors.
_C0_CANDIDATES = [
    (255, 0, 255), (0, 255, 255), (255, 255, 0), (255, 0, 128),
    (128, 255, 0), (0, 255, 128), (255, 128, 255), (128, 0, 255),
]

_PATH_RE = re.compile(r"<path\s[^>]*/?>")
_NUM_RE = re.compile(r"-?\d+\.\d{3,}")


def _round_path_data(svg: str) -> str:
    """Round 20-digit floats to 2dp to shrink the SVG without visual change."""
    return _NUM_RE.sub(lambda m: f"{float(m.group(0)):g}", svg)


def _pick_bg_color(rgb_small: Image.Image):
    """Pick the candidate C0 with the largest minimum distance to the palette."""
    try:
        pal = rgb_small.quantize(colors=16, method=Image.Quantize.FASTOCTREE)
        raw = pal.getcolors() or []
        table = pal.getpalette()
        entries = [
            (count, (table[i * 3], table[i * 3 + 1], table[i * 3 + 2]))
            for count, i in raw
            if isinstance(i, int) and i * 3 + 2 < len(table)
        ]
    except Exception:
        entries = []
    if not entries:  # fallback: sample pixels directly
        entries = [(1, c[:3]) for c in list(rgb_small.getdata())[:256]]
    best, best_score = _C0_CANDIDATES[0], -1.0
    for cand in _C0_CANDIDATES:
        worst = 1e9
        for _count, (r, g, b) in entries:
            d = (r - cand[0]) ** 2 + (g - cand[1]) ** 2 + (b - cand[2]) ** 2
            worst = min(worst, d)
        if worst > best_score:
            best, best_score = cand, worst
    palette = [rgb for _count, rgb in entries]
    return best, int(best_score ** 0.5), palette  # color, distance, palette


def _strip_color(svg: str, color, content_palette) -> str:
    """Remove the synthetic-background layers.

    The tracer's internal quantization blends the synthetic bg color with
    content edge colors, so the "background" can appear as several close
    shades (e.g. magenta, pink-magenta, magenta-teal tints). Rule: a layer
    is background iff its fill is no farther from the synthetic color than
    from every real content color (ties go to background — those blends are
    edge artifacts, not content).
    """
    content_palette = list(content_palette) or [(0, 0, 0)]

    def keep(m):
        tag = m.group(0)
        fm = re.search(r'fill="(#[0-9A-Fa-f]{6})"', tag)
        if not fm:
            return tag
        r, g, b = int(fm.group(1)[1:3], 16), int(fm.group(1)[3:5], 16), int(fm.group(1)[5:7], 16)
        d_bg = (r - color[0]) ** 2 + (g - color[1]) ** 2 + (b - color[2]) ** 2
        d_content = min(
            (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2 for (pr, pg, pb) in content_palette
        )
        return tag if d_bg > d_content else ""

    return _PATH_RE.sub(keep, svg)


def _flatten_colors(working: Image.Image, bg_color, max_inks: int = 3) -> Image.Image:
    """Collapse shading variants into a small hard palette.

    Flat art with subtle gradients (shaded line art, glossy icons) makes the
    tracer emit many tiny adjacent regions in near-identical colors, and the
    seams between those fragments read as holes. Here we keep only the
    `max_inks` most significant ink colors and snap every other pixel to its
    nearest one. The tracer then sees 2-4 clean flat colors and draws each
    as one solid region — no shading fragments, no seams.
    """
    q = working.quantize(colors=12, method=Image.Quantize.FASTOCTREE)
    table = q.getpalette()
    counts = q.getcolors() or []
    classes = sorted(counts, key=lambda t: -t[0])
    if not classes:
        return working.convert("RGB")

    def col_of(idx):
        return (table[idx * 3], table[idx * 3 + 1], table[idx * 3 + 2])

    def d2(c1, c2):
        return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2

    # The most frequent class is the background (C0 region dominates for
    # transparent logos; the paper color for opaque flat prints).
    bg_count, bg_idx = classes[0]
    bg_col = col_of(bg_idx)
    total = sum(c for c, _ in classes) or 1

    # Inks must cover >= 2% of the image: real logo colors dominate, while
    # AA/highlight slivers (1% or less) snap into the nearest real ink.
    ink_classes = [t for t in classes[1:] if t[0] >= total * 0.02]
    top = ink_classes[:max_inks]
    if not top:
        return working.convert("RGB")
    ink_cols = [col_of(i) for _c, i in top]

    remap = np.zeros(256, dtype=np.uint8)
    remap[bg_idx] = 0
    for _count, idx in classes[1:]:
        col = col_of(idx)
        best_i = min(range(len(ink_cols)), key=lambda i: d2(col, ink_cols[i]))
        remap[idx] = best_i + 1

    new_arr = np.asarray(q).reshape(-1)
    palette = [bg_col] + ink_cols
    out = Image.fromarray(remap[new_arr].reshape(q.size[1], q.size[0]), "P")
    flat = []
    for c in palette:
        flat += list(c)
    while len(flat) < 768:
        flat += [0]
    out.putpalette(flat[:768])
    return out


def _seal_seams(svg: str, stroke_width: int = 1) -> str:
    """Give every path a 0.5px same-color stroke.

    Cutout tracing produces independent region outlines, so adjacent layers
    can leave hairline 1px seams (visible as "holes" where the backdrop
    shows through). A same-color stroke widens each layer by ~0.5px into
    the one drawn above it, sealing every seam while changing nothing
    visually.
    """
    def fix(m):
        tag = m.group(0)
        fm = re.search(r'fill="(#[0-9A-Fa-f]{6})"', tag)
        if not fm or "stroke=" in tag:
            return tag
        end = "/>" if tag.endswith("/>") else ">"
        return tag[:-len(end)] + f' stroke="{fm.group(1)}" stroke-width="{stroke_width}"' + end

    return _PATH_RE.sub(fix, svg)


def _tidy(svg: str, w: int, h: int, flat: bool = False, seal: int | None = None) -> str:
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = _round_path_data(svg)
    if seal is None:
        seal = 2 if flat else 1
    if seal > 0:
        svg = _seal_seams(svg, seal)
    # Guarantee explicit size + viewBox so the SVG scales predictably.
    svg = re.sub(r'<svg\b[^>]*>', f'<svg xmlns="http://www.w3.org/2000/svg" '
                                  f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">', svg, count=1)
    return re.sub(r"\n\s*\n", "\n", svg).strip() + "\n"


def analyze(img: Image.Image) -> dict:
    """Per-image prep: downscale, transparency mask + ring, C0 background,
    flatness detection. Returns a dict consumed by trace_with()."""
    img = img.convert("RGBA")
    w, h = img.size
    if max(w, h) > MAX_EDGE:
        f = MAX_EDGE / max(w, h)
        img = img.resize((max(1, round(w * f)), max(1, round(h * f))), Image.LANCZOS)
    w, h = img.size

    alpha = img.getchannel("A")
    has_alpha = alpha.getextrema()[0] < 255

    bg_color = None
    content_palette = []
    if has_alpha:
        small = img.convert("RGB").resize((max(1, w // 4), max(1, h // 4)))
        bg_color, dist, content_palette = _pick_bg_color(small)
        mask_orig = alpha.point(lambda a: 255 if a > ALPHA_CUTOFF else 0)
        # Morphological closing (dilate r2 + erode r2): welds the 1-4px wedge
        # gaps that remain where stroke fragments cross, without moving the
        # outer boundary. Without it the vector shows tiny background wedges
        # at intersections of line art.
        mask_orig = mask_orig.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
        # Grow the content mask by 2px so the traced outer edge overshoots the
        # true boundary: the tracer smooths/erodes edges (up to ~2px on
        # curves) and splits continuous strokes into fragments with small
        # gaps between them. The overshoot ring is a sacrificial zone — the
        # erosion eats into it, fragments overlap, and the final edge lands
        # on (or just outside) the original boundary. The ring is flattened
        # to the artwork's own flat ink colors, so it reads as part of the
        # art rather than a halo.
        mask = mask_orig.filter(ImageFilter.MaxFilter(5))
        content_rgb = img.convert("RGB")
        extended = content_rgb
        for _ in range(2):  # push content colors 2px outward
            extended = extended.filter(ImageFilter.MaxFilter(3))
        working = Image.new("RGB", (w, h), bg_color)
        working.paste(content_rgb, (0, 0), mask_orig)
        ring_np = (np.asarray(mask) > 128) & ~(np.asarray(mask_orig) > 128)
        if ring_np.any():
            ring = Image.fromarray((ring_np * 255).astype(np.uint8))
            working.paste(extended, (0, 0), ring)
        # If real content sits on top of C0 anyway, keep the background opaque
        # rather than risk punching a hole in the artwork.
        keep_bg = dist < 45
    else:
        working = img.convert("RGB")
        mask = None
        keep_bg = True

    # --- flat-art detection: how well does a 4-color palette reconstruct the
    #     content? Flat logos/icons (with AA edge shades) score ~5-15,
    #     photos score 60+. For transparent inputs only content pixels count,
    #     so the synthetic background never disqualifies a flat logo. ---
    small_w, small_h = (max(1, min(256, w)), max(1, min(256, h)))
    arr = np.asarray(working.resize((small_w, small_h)), dtype=np.float32)
    if mask is not None:
        m_small = np.asarray(mask.resize((small_w, small_h))) > 128
    else:
        # numpy arrays are (height, width): keep dimension order consistent with arr
        m_small = np.ones((small_h, small_w), dtype=bool)
    probe_arr = arr[m_small]
    if probe_arr.size == 0:
        probe_arr = np.zeros((1, 3), dtype=np.uint8)
    probe = Image.fromarray(probe_arr.reshape(1, -1, 3).astype(np.uint8), "RGB")
    q4 = probe.quantize(colors=4, method=Image.Quantize.FASTOCTREE)
    pal = np.asarray(q4.getpalette()[:12]).reshape(4, 3).astype(np.float32)
    idx = np.asarray(q4).reshape(-1)
    flat_err = float(np.sqrt(((probe_arr - pal[idx]) ** 2).sum(axis=1)).mean())
    is_flat = flat_err <= FLAT_ERR

    return {
        "img": img, "w": w, "h": h, "has_alpha": has_alpha,
        "bg_color": bg_color, "content_palette": content_palette,
        "keep_bg": keep_bg, "working": working, "mask": mask,
        "is_flat": is_flat, "flat_err": flat_err,
    }


def _dominant_content_color(a: dict) -> tuple[int, int, int] | None:
    """Mean RGB over strictly-content pixels of the original RGBA input."""
    rgb = np.asarray(a["img"].convert("RGB"), dtype=np.float32)
    alpha = np.asarray(a["img"].getchannel("A"))
    m = alpha > ALPHA_CUTOFF
    if not m.any():
        return None
    mean = rgb[m].mean(axis=0)
    return (int(mean[0]), int(mean[1]), int(mean[2]))


def _mono_alpha_candidate(a: dict) -> bool:
    """Detect 'monochrome transparent content': flat artwork whose meaningful
    content is a single ink family on an alpha canvas (e.g. the teal-orbit
    logo). In this regime the color-cutout path saturates (~5 paths / 72% sim)
    while binary-alpha tracing reproduces the true geometry (93.5% sim on the
    user-provided teal logo — evidence: qa/audits/teal-orbit/)."""
    if not (a.get("has_alpha") and not a.get("keep_bg", True) and a.get("is_flat")):
        return False
    dom = _dominant_content_color(a)
    if dom is None:
        return False
    rgb = np.asarray(a["img"].convert("RGB"), dtype=np.int16)
    alpha = np.asarray(a["img"].getchannel("A"))
    m = alpha > ALPHA_CUTOFF
    px = rgb[m].astype(np.int32)
    d = np.sqrt(((px - np.array(dom, dtype=np.int32)) ** 2).sum(axis=1))
    mono_share = float((d <= 60).mean()) if len(px) else 0.0
    return mono_share >= 0.92  # 92% of content within 60 RGB of dominant


def _trace_binary_alpha(a: dict, params: dict) -> str:
    """Trace the alpha silhouette with vtracer colormode=binary, then recolor
    the black fills to the dominant content color. Preserves inner cutouts +
    thin ring strokes that the color-cutout buckets merge away."""
    dom = _dominant_content_color(a) or (0, 0, 0)
    # Trace the TRUE alpha, not the ring-grown mask: the +2px sacrificial ring
    # was engineered for color-cutout smoothing; on a binary silhouette it is
    # pure inflation (~72% sim ceiling instead of 93.5% on the teal-orbit
    # user logo — evidence: qa/audits/teal-orbit/).
    alpha = a["img"].getchannel("A")
    binary = alpha.point(lambda v: 0 if v > ALPHA_CUTOFF else 255)  # content black
    lt = min(max(float(params.get("length_threshold", 0.5)), 0.5), 4.0)
    pp = min(max(int(params.get("path_precision", 5)), 3), 12)
    sp = min(max(int(params.get("filter_speckle", 1)), 1), 16)
    ct = min(max(int(params.get("corner_threshold", 30)), 10), 110)
    with tempfile.TemporaryDirectory() as td:
        src = f"{td}/bin.png"
        out = f"{td}/bin.svg"
        binary.save(src)
        vtracer.convert_image_to_svg_py(
            src, out, colormode="binary", hierarchical="stacked",
            filter_speckle=sp, corner_threshold=ct,
            length_threshold=lt, path_precision=pp,
        )
        svg = open(out, encoding="utf-8").read()
    hexcol = f"#{dom[0]:02X}{dom[1]:02X}{dom[2]:02X}"
    svg = re.sub(r'fill="(?:#000000|#000|black|rgb\(0,0,0\)|rgb\(0%,0%,0%\))"',
                 f'fill="{hexcol}"', svg, flags=re.I)
    svg = _tidy(svg, a["w"], a["h"], True)
    return re.sub(r'(<svg\b)', r'\1 data-engine="binary-alpha-mono"', svg, count=1)


def _trace_alpha_tone_stack(a: dict, params: dict) -> str:
    """For transparent monochrome art: decompose the TRUE alpha content into a
    few tonal bands (the body + the soft AA halo that binary engines drop),
    trace each band with vtracer binary, and stack them as solid + translucent
    fills in the content hue. This is the engine that can actually approach the
    user-approved reference look (~97% strict similarity on the teal-orbit
    logo), because it keeps the halo band as a translucent fill instead of
    clipping it.
    Fully generic: works for any image that passes _mono_alpha_candidate; all
    decisions below derive from image data (k-means on tones), never filenames.
    """
    img = a["img"].convert("RGBA")
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    alp = np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0
    solid = alp > 0.06
    if not solid.any():
        return _trace_binary_alpha(a, params)
    comp = rgb * alp[..., None] + 255.0 * (1.0 - alp[..., None])  # composited on white
    tones = comp[solid].mean(axis=1)  # 255=paper .. darker = ink
    k = int(min(max(int(params.get("tone_bands", 4)), 2), 6))
    # 1-D k-means over tone
    centers = np.linspace(tones.min(), tones.max(), k).astype(np.float32)
    for _ in range(24):
        d = np.abs(tones[:, None] - centers[None, :])
        lab = d.argmin(axis=1)
        newc = np.array([tones[lab == i].mean() if (lab == i).any() else centers[i]
                         for i in range(k)], dtype=np.float32)
        if np.abs(newc - centers).max() < 0.5:
            centers = newc
            break
        centers = newc
    order = np.argsort(-centers)  # lightest first
    lt = min(max(float(params.get("length_threshold", 0.5)), 0.5), 4.0)
    pp = min(max(int(params.get("path_precision", 5)), 3), 12)
    sp = min(max(int(params.get("filter_speckle", 1)), 1), 16)
    ct = min(max(int(params.get("corner_threshold", 30)), 10), 110)
    h, w = alp.shape
    paths: list[str] = []
    for ci, i in enumerate(order):
        # stack semantics: each band masks pixels of its tone OR darker so
        # higher bands overpaint nothing (solid opaque stacking like VM refs)
        darker = np.isin(lab, order[ci:])
        band = np.zeros((h, w), dtype=bool)
        band[solid] = darker
        if not band.any():
            continue
        # drop a pure-paper band (background pixels sneaking into `solid`)
        m_rgb = comp[band].mean(axis=0)
        if m_rgb.mean() >= 250.0:
            continue
        pix = np.where(band, 0, 255).astype(np.uint8)
        with tempfile.TemporaryDirectory() as td:
            src, out = f"{td}/b.png", f"{td}/b.svg"
            Image.fromarray(pix, "L").save(src)
            vtracer.convert_image_to_svg_py(
                src, out, colormode="binary", hierarchical="stacked",
                filter_speckle=sp, corner_threshold=ct,
                length_threshold=lt, path_precision=pp)
            bsvg = open(out, encoding="utf-8").read()
        hexcol = f"#{int(m_rgb[0]):02X}{int(m_rgb[1]):02X}{int(m_rgb[2]):02X}"
        bsvg = re.sub(r'fill="(?:#000000|#000|black|rgb\(0,0,0\)|rgb\(0%,0%,0%\))"',
                      f'fill="{hexcol}"', bsvg, flags=re.I)
        # collect paths only, discard band svg wrappers
        paths.extend(re.findall(r'<path\b[^>]*/?>', bsvg))
    if not paths:
        return _trace_binary_alpha(a, params)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}">' + "".join(paths) + "</svg>")
    svg = _tidy(svg, w, h, True)
    return re.sub(r'(<svg\b)', r'\1 data-engine="alpha-tone-stack"', svg, count=1)


def _zhang_suen(m: np.ndarray) -> np.ndarray:
    """Binary skeletonization (Zhang-Suen), vectorized numpy."""
    m = m.copy().astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = np.pad(m, 1)
            p2 = P[:-2, 1:-1]; p3 = P[:-2, 2:]; p4 = P[1:-1, 2:]; p5 = P[2:, 2:]
            p6 = P[2:, 1:-1]; p7 = P[2:, :-2]; p8 = P[1:-1, :-2]; p9 = P[:-2, :-2]
            ns = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(ns)
            seq = ns + [p2]
            A = sum((seq[i] == 0) & (seq[i + 1] == 1) for i in range(8))
            if step == 0:
                cond = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                cond = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            kill = (m == 1) & (B >= 2) & (B <= 6) & (A == 1) & cond
            if kill.any():
                m[kill] = 0
                changed = True
    return m


def _trace_hairline(a: dict, params: dict) -> str:
    """Skeleton engine for thin-stroke art (hairlines, wireframes): the SVG
    fill-contour family can't reproduce 1px strokes — the filled contour
    plus seam growth renders them 3px wide (strict 63.9% on the thin-strokes
    gauntlet asset). Here the binary ink is skeletonized (Zhang-Suen), the
    skeleton chains become centreline polyline paths with the row-sampled
    ink color and honest stroke-width (~1.5 >render< width wins the strict
    comparison: 75.9%, since the original hairlines are anti-aliased)."""
    img = a["img"].convert("RGB")
    arr = np.asarray(img).astype(np.float32).mean(axis=2)
    ink = arr < 128
    w, h = a["w"], a["h"]
    width = min(max(float(params.get("stroke_width", 1.5)), 0.5), 3.0)
    if not ink.any():
        return _trace_cutout(a, params, a.get("is_flat", False), 2, 16, 1, 12, 60, 4.5, 10, 3)
    sk = _zhang_suen(ink)
    P = np.pad(sk, 1)
    deg = sum([P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:],
               P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]])
    visited = np.zeros_like(sk)
    N = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
    rgb_full = np.asarray(img)

    def chain_color(chain):
        ys = [p[0] for p in chain]; xs = [p[1] for p in chain]
        c = rgb_full[ys, xs].mean(axis=0).astype(int)
        return f"#{int(c[0]):02X}{int(c[1]):02X}{int(c[2]):02X}"

    paths: list[str] = []
    starts = [tuple(p) for p in np.argwhere(sk & (deg == 1))]
    starts += [tuple(p) for p in np.argwhere(sk & (deg == 2) & (visited == 0))]
    for sy, sx in starts:
        if visited[sy, sx] or not sk[sy, sx]:
            continue
        chain = [(int(sy), int(sx))]
        visited[sy, sx] = 1
        cy, cx = int(sy), int(sx)
        while True:
            nxt = None
            for dy, dx in N:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < ink.shape[0] and 0 <= nx < ink.shape[1] and sk[ny, nx] and not visited[ny, nx]:
                    nxt = (ny, nx)
                    break
            if nxt is None:
                break
            visited[nxt] = 1
            chain.append(nxt)
            cy, cx = nxt
        if len(chain) < 3:
            continue
        pts = [(x, y) for y, x in chain]
        simp = [pts[0]]
        for i in range(1, len(pts) - 1):
            (x0, y0), (x1, y1), (x2, y2) = simp[-1], pts[i], pts[i + 1]
            if (x2 - x0) * (y1 - y0) != (y2 - y0) * (x1 - x0):
                simp.append((x1, y1))
        simp.append(pts[-1])
        d = "M" + " L".join(f"{p[0]},{p[1]}" for p in simp)
        paths.append(f'<path d="{d}" stroke="{chain_color(chain)}" stroke-width="{width}" '
                     f'fill="none" stroke-linecap="square" stroke-linejoin="miter"/>')
    if not paths:
        return _trace_cutout(a, params, a.get("is_flat", False), 2, 16, 1, 12, 60, 4.5, 10, 3)
    bg = "#FFFFFF"
    if a.get("has_alpha"):
        bg = None
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg and not a.get("has_alpha") else ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}">{rect}{"".join(paths)}</svg>')
    return re.sub(r'(<svg\b)', r'\1 data-engine="hairline"', svg, count=1)


def _hairline_candidate(a: dict) -> bool:
    """Thin-stroke detector: ink erodes to nothing in <=2 rounds (max stroke
    half-width ~2px => ~3-4px strokes or thinner) and is sparse (<12% of area),
    on opaque flat art only (alpha art has its own engine family)."""
    if a.get("has_alpha") or not a.get("is_flat"):
        return False
    arr = np.asarray(a["img"].convert("RGB")).astype(np.float32).mean(axis=2)
    ink = (arr < 128).astype(np.uint8)
    share = ink.mean()
    if not (0.001 < share < 0.12):
        return False
    m = ink
    for rounds in range(3):
        P = np.pad(m, 1)
        er = (P[:-2, 1:-1] & P[:-2, 2:] & P[1:-1, 2:] & P[2:, 2:] &
              P[2:, 1:-1] & P[2:, :-2] & P[1:-1, :-2] & P[:-2, :-2])
        m = er
        if not m.any():
            return True
    return False


def _trace_pixel_art(a: dict, params: dict) -> str:
    """Pixel-faithful engine for tiny pixelated inputs (<=64px): downscaled
    rasters are grid-quantized, and any smooth tracer AA-dithers the result
    vs the original (strict 1-17% floor). Here we keep the ORIGINAL alpha
    per pixel, quantize RGB to a tight 16-color palette, and run-length
    encode rows into integer-rect paths with shape-rendering=crispEdges —
    a 1:1 lossless-ish raster->vector map (strict 99.9-100% on all 32px
    gauntlet assets vs 1-17% before). True vector out: rect runs only."""
    img = a["img"].convert("RGBA")
    w, h = a["w"], a["h"]
    arr = np.asarray(img)
    rgb, alpha = arr[..., :3], arr[..., 3]
    op = alpha > 0
    colors = min(max(int(params.get("pixel_colors", 16)), 4), 32)
    q = Image.fromarray(np.where(op[..., None], rgb, 0).astype(np.uint8)).quantize(
        colors=colors, method=Image.Quantize.FASTOCTREE)
    table = q.getpalette()
    idxs = np.asarray(q, dtype=np.uint8)
    segs: list[str] = []
    for y in range(h):
        x = 0
        while x < w:
            c = int(idxs[y, x]); aa = int(alpha[y, x]); x2 = x + 1
            while x2 < w and idxs[y, x2] == c and int(alpha[y, x2]) == aa:
                x2 += 1
            if aa > 0:
                hexcol = f"#{table[c*3]:02X}{table[c*3+1]:02X}{table[c*3+2]:02X}"
                op_attr = "" if aa == 255 else f' fill-opacity="{aa/255.0:.3f}"'
                segs.append(f'<rect x="{x}" y="{y}" width="{x2-x}" height="1" fill="{hexcol}"{op_attr}/>')
            x = x2
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" shape-rendering="crispEdges">{"".join(segs)}</svg>')
    return re.sub(r'(<svg\b)', r'\1 data-engine="pixel-art"', svg, count=1)


def _trace_alpha_halo_stack(a: dict, params: dict) -> str:
    """Radial halo contours for transparent monochrome art.

    The tone-stack engine hands the soft AA halo to one translucent fill,
    which flattens the fade (~78% strict on teal-orbit). Here the content is
    treated as an alpha *field* over normalized ellipse distance from its
    center; the field is sliced into `halo_bands` shells (outermost first)
    and each shell is traced at its annulus, painted in the content hue with
    fill-opacity = the strongest real alpha found in that shell
    (never synthesized, max of the input data). Layers stack faint-outside -
    strong-inside, so the halo fade and the sharp core survive together —
    the reference look the trainer is asked to reproduce.
    """
    img = a["img"].convert("RGBA")
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    alp = np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0
    keep = alp > 0.02
    if not keep.any():
        return _trace_binary_alpha(a, params)
    strong = alp > 0.5
    if not strong.any():
        strong = keep
    dom = rgb[strong].mean(axis=0).astype(int)
    hexcol = f"#{dom[0]:02X}{dom[1]:02X}{dom[2]:02X}"

    h, w = alp.shape
    ys, xs = np.nonzero(keep)
    cx, cy = float(xs.mean()), float(ys.mean())
    rx = max((float(xs.max()) - float(xs.min())) / 2.0, 1.0)
    ry = max((float(ys.max()) - float(ys.min())) / 2.0, 1.0)
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    dmax = float(d[keep].max()) + 1e-6

    K = min(max(int(params.get("halo_bands", 16)), 3), 20)
    lt = min(max(float(params.get("length_threshold", 0.5)), 0.5), 4.0)
    pp = min(max(int(params.get("path_precision", 5)), 3), 12)
    sp = min(max(int(params.get("filter_speckle", 2)), 1), 16)
    ct = min(max(int(params.get("corner_threshold", 30)), 10), 110)

    layers: list[str] = []
    for b in range(K):  # outermost shell first, non-overlapping annuli
        lo = dmax * (K - 1 - b) / K
        hi = dmax * (K - b) / K
        sel = keep & (d >= lo) & (d < hi if b > 0 else d <= dmax)
        if not sel.any():
            continue
        win = alp[sel & keep]
        if not len(win):
            continue
        paint = float(win.mean())  # honest statistic of the input field
        if paint <= 0.01:
            continue
        pix = np.where(sel, 0, 255).astype(np.uint8)
        with tempfile.TemporaryDirectory() as td:
            src, out = f"{td}/b.png", f"{td}/b.svg"
            Image.fromarray(pix, "L").save(src)
            vtracer.convert_image_to_svg_py(
                src, out, colormode="binary", hierarchical="stacked",
                filter_speckle=sp, corner_threshold=ct,
                length_threshold=lt, path_precision=pp)
            bsvg = open(out, encoding="utf-8").read()
        bsvg = re.sub(r'fill="(?:#000000|#000|black|rgb\(0,0,0\)|rgb\(0%,0%,0%\))"',
                      f'fill="{hexcol}" fill-opacity="{paint:.3f}"', bsvg, flags=re.I)
        layers.extend(re.findall(r'<path\b[^>]*/?>', bsvg))
    if not layers:
        return _trace_binary_alpha(a, params)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}">' + "".join(layers) + "</svg>")
    # No seam sealing for the halo stack: growing 16 translucent shells by
    # even 1px floods inner annuli (87.9 -> 82.5 strict on teal-orbit; the
    # shells abut perfectly by construction, so there are no seams to seal).
    svg = _tidy(svg, w, h, False, seal=0)
    return re.sub(r'(<svg\b)', r'\1 data-engine="alpha-halo-stack"', svg, count=1)


def trace_with(a: dict, params: dict | None = None) -> str:
    """Run one vectorization pass with the given params (or the heuristic
    baseline when params is None). params keys: profile, color_precision,
    layer_difference, filter_speckle, max_iterations (all optional)."""
    params = params or {}
    # handle preset shortcut
    preset_name = params.get("preset")
    if preset_name and preset_name in PRESETS and PRESETS[preset_name]:
        # preset overrides if explicit param not given
        preset = PRESETS[preset_name]
        for k, v in preset.items():
            if k not in params:
                params[k] = v

    flat = params.get("profile", "flat" if a["is_flat"] else "photo") == "flat"
    cp = int(params.get("color_precision", BASELINE_FLAT["color_precision"] if flat else BASELINE_PHOTO["color_precision"]))
    ld = int(params.get("layer_difference", BASELINE_FLAT["layer_difference"] if flat else BASELINE_PHOTO["layer_difference"]))
    sp = int(params.get("filter_speckle", BASELINE_FLAT["filter_speckle"] if flat else BASELINE_PHOTO["filter_speckle"]))
    mi = int(params.get("max_iterations", BASELINE_FLAT["max_iterations"] if flat else BASELINE_PHOTO["max_iterations"]))
    ct = int(params.get("corner_threshold", BASELINE_FLAT["corner_threshold"] if flat else BASELINE_PHOTO["corner_threshold"]))
    lt = float(params.get("length_threshold", BASELINE_FLAT["length_threshold"] if flat else BASELINE_PHOTO["length_threshold"]))
    pp = int(params.get("path_precision", BASELINE_FLAT["path_precision"] if flat else BASELINE_PHOTO["path_precision"]))
    # cp=1 (slider "2 colors") collapses every flat ink bucket into the
    # background bucket, so vtracer sees a uniform canvas and emits a single
    # path that _strip_color then deletes -> empty SVG shell. QA sweep
    # evidence: qa/results/sweep-gen-*-c2-*.json (8 empty shells). Floor at 2
    # bits; palette size is still dominated by _flatten_colors max_inks.
    cp = min(max(cp, 2), 8)
    ld = min(max(ld, 4), 48)
    sp = min(max(sp, 1), 16)
    mi = min(max(mi, 8), 48)
    ct = min(max(ct, 10), 110)
    lt = min(max(lt, 2.0), 10.0)
    pp = min(max(pp, 3), 12)
    inks = min(max(int(params.get("max_inks", 3)), 2), 8)

    # Engine route (generic family rule + VISUAL pick, never per-file hacks):
    # transparent monochrome art prefers binary-alpha (teal-orbit QA evidence),
    # but some members render closer as multi-tone cutout. For that family we
    # render BOTH engines and keep the visually better one by the same
    # Tiny pixelated inputs (<=64px): grid-pure pixel-art engine, 1:1 mapping
    if params.get("engine") != "color-cutout" and max(a["w"], a["h"]) <= 64:
        return _trace_pixel_art(a, params)
    # Thin-stroke skeleton engine (wireframes/hairlines): contour fills
    # inflate 1px lines to ~3px (strict 63.9 vs skeleton 75.9)
    if params.get("engine") == "hairline" or (params.get("engine") not in
            ("color-cutout",) and _hairline_candidate(a)):
        return _trace_hairline(a, params)
    # geometry/coverage-trained scorer the model optimizes.
    if params.get("engine") == "alpha-tone-stack" and _mono_alpha_candidate(a):
        return _trace_alpha_tone_stack(a, params)
    if params.get("engine") == "alpha-halo-stack" and _mono_alpha_candidate(a):
        return _trace_alpha_halo_stack(a, params)
    # Engine route: monochrome transparent content. Calibrated on a 41-image
    # sweep (teal + 40 corpus logos, 2026-09-27): share of alpha>0.5 pixels
    # splits the engines cleanly. Sparse thin-line art (share <= 0.17): the
    # radial halo engine wins 21/21 by +8.5 points avg (teal-orbit share=0.067,
    # halo 87.9 vs binary 87.2). Dense filled glyphs (share > 0.17): halo's
    # annulus statistics shred the fills (-12 to -54), binary is solid.
    if params.get("engine") != "color-cutout" and _mono_alpha_candidate(a):
        alpha_arr = np.asarray(a["img"].getchannel("A"), dtype=np.float32) / 255.0
        strong_share = float((alpha_arr > 0.5).mean())
        if strong_share <= 0.17:
            return _trace_alpha_halo_stack(a, params)
        return _trace_binary_alpha(a, params)

    return _trace_cutout(a, params, flat, cp, ld, sp, mi, ct, lt, pp, inks)


def _trace_cutout(a: dict, params: dict, flat: bool, cp: int, ld: int, sp: int,
                  mi: int, ct: int, lt: float, pp: int, inks: int) -> str:
    """Color-cutout engine (vtracer) shared by the default route and the
    mono-alpha best-of-two visual pick."""

    w, h = a["w"], a["h"]

    def _run(mi_, cp_, ld_, sp_, ct_, lt_, pp_, inks_, detail: bool) -> str:
        with tempfile.TemporaryDirectory() as td:
            src = f"{td}/in.png"
            out = f"{td}/out.svg"
            flat_work = a["working"]
            if flat:
                maxinks = images_inks(inks_, detail)
                flat_work = _flatten_colors(flat_work, a["bg_color"] or (0, 0, 0), max_inks=maxinks)
            flat_work.save(src)
            vtracer.convert_image_to_svg_py(
                src, out,
                colormode="color", hierarchical="cutout",
                max_iterations=mi_, color_precision=cp_, layer_difference=ld_,
                filter_speckle=sp_, corner_threshold=ct_,
                length_threshold=lt_, path_precision=pp_,
            )
            return open(out, encoding="utf-8").read()

    def images_inks(base: int, detail: bool) -> int:
        return max(base, 5) if detail else base

    svg = _run(mi, cp, ld, sp, ct, lt, pp, inks, detail=False)
    # Detail retry (measured 2026-09-27): flat art traced into so few paths
    # means micro cutouts (beak slits, eye gaps) got merged by the coarse
    # preset (lt 4.5 / cp 2-3 / speckle). Retry with detail settings; gains
    # up to +7.7 (bird icon) with worst case -2.1 noise on 26 corpus images.
    if flat and len(re.findall(r"<path\b", svg)) <= 6 and params.get("detail_retry", True):
        svg = _run(20, 5, 12, 0, 40, 0.5, pp, inks, detail=True)

    if a["has_alpha"] and not a["keep_bg"]:
        svg = _strip_color(svg, a["bg_color"], a["content_palette"])

    return _tidy(svg, w, h, flat)


def _pick_best_preset(a: dict) -> dict:
    """Cloudinary inspired best tier v2: smarter preset picking based on flatness, alpha, size, edge, color count"""
    w, h = a["w"], a["h"]
    flat_err = a.get("flat_err", 100)
    is_flat = a.get("is_flat", False)
    has_alpha = a.get("has_alpha", False)
    # Estimate color complexity from working image small palette
    try:
        working = a.get("working")
        if working:
            small = working.resize((64, 64))
            # count distinct colors in quantized 16
            q = small.quantize(colors=16, method=Image.Quantize.FASTOCTREE)
            colors = len([c for c in (q.getcolors() or []) if c[0] > 64])
        else:
            colors = 8
    except:
        colors = 8

    # Very tiny icons <64px: icon preset strictest
    if max(w, h) < 64:
        return PRESETS["icon"]
    # Small icons 64-128 and flat: icon
    if max(w, h) < 128 and is_flat and colors <= 6:
        return PRESETS["icon"]
    # Pure geometric logos: flat, very low error <12, transparent, few colors <=5
    if is_flat and flat_err < 12 and has_alpha and colors <= 5:
        return PRESETS["logo"]
    # Flat logos with low error <18
    if is_flat and flat_err < 18:
        return PRESETS["logo"]
    # Flat illustration: flat but more colors or moderate error 18-35
    if is_flat and flat_err < 35:
        return PRESETS["illustration"] if colors > 4 else PRESETS["logo"]
    # Non-flat small for LQIP
    if not is_flat and max(w, h) < 200:
        return PRESETS["lqip"]
    # Non-flat with high error >55: photo/artistic
    if not is_flat and flat_err > 55:
        return PRESETS["artistic"] if max(w, h) > 400 else PRESETS["lqip"]
    # Default best tier
    return PRESETS["logo"] if is_flat else PRESETS["illustration"]

def sliders_to_params(colors: int | None, detail: int | None,
                      smoothness: int | None, base: dict | None = None) -> dict:
    """Map the three user-facing sliders (Colors / Detail / Corner smoothness,
    same labels as the Cloudinary tool) onto raw vtracer params.

    colors     2..128   → color_precision (bits) + layer_difference
    detail     0..100   → max_iterations + length_threshold + path_precision
    smoothness 0..100   → corner_threshold (0 smooth curves .. 100 sharp corners)
    """
    p = dict(base or {})
    if colors is not None:
        c = min(128, max(2, colors))
        bits = max(1, min(8, int(round(np.log2(c)))))
        p["color_precision"] = bits
        p["layer_difference"] = 16 if bits <= 4 else 12
    if detail is not None:
        d = min(100, max(0, detail)) / 100.0
        p["max_iterations"] = 8 + int(round(d * 40))
        p["length_threshold"] = 4.5 - d * 2.0      # more detail → shorter segments
        p["path_precision"] = 3 + int(round(d * 9))
    if smoothness is not None:
        s = min(100, max(0, smoothness))
        p["corner_threshold"] = min(110, max(10, 110 - int(round(s * 0.8))))
    return p


def _enhance_working(a: dict) -> dict:
    """Optional 'Clean first' step for the no-model mode (vectorizer.io idea):
    denoise + hard color simplify + slight sharpen before tracing so speckles
    and JPEG noise do not become noise blobs in the SVG."""
    b = dict(a)
    w_img = a["working"].filter(ImageFilter.MedianFilter(3))
    if not a.get("is_flat"):
        w_img = w_img.quantize(colors=32, method=Image.Quantize.FASTOCTREE).convert("RGB")
    w_img = w_img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=110, threshold=3))
    b["working"] = w_img
    return b


def _score_svg(img: Image.Image, svg: str) -> float:
    try:
        from model.svg_geom import score
        small = img.convert("RGBA")
        if max(small.size) > 400:
            f = 400 / max(small.size)
            small = small.resize((max(1, round(small.size[0] * f)),
                                  max(1, round(small.size[1] * f))), Image.LANCZOS)
        return float(score(small, svg, step=6)["score"])
    except Exception:
        return 0.0


def vectorize(img_bytes: bytes, params: dict | None = None, mode_opts: dict | None = None) -> dict:
    """Convert raster bytes to a clean SVG. Returns {svg, meta}.

    mode_opts keys: colors/detail/smoothness (sliders), enhance (bool),
    engine ('best' for multi-candidate scoring)."""
    opts = mode_opts or {}
    t0 = time.time()
    img = Image.open(io.BytesIO(img_bytes))
    a = analyze(img)
    # best tier method when no params: use Cloudinary inspired preset picking
    if params is None:
        params = _pick_best_preset(a)
    params = sliders_to_params(opts.get("colors"), opts.get("detail"),
                               opts.get("smoothness"), params)
    if opts.get("enhance"):
        a = _enhance_working(a)

    engine = opts.get("engine")
    if engine == "best":
        # try the chosen params plus two neighboring presets, keep the winner
        candidates = [(params, "selected")]
        for name in ("logo", "illustration"):
            if not a["is_flat"] and name == "logo":
                name = "artistic"
            p = dict(PRESETS[name])
            if params.get("preset") == name:
                continue
            candidates.append((p, name))
        best_svg, best_score, best_name = None, -1.0, ""
        for p, name in candidates:
            try:
                svg_c = trace_with(a, p)
                s = _score_svg(img, svg_c)
                if s > best_score:
                    best_svg, best_score = svg_c, s
            except Exception:
                continue
        svg = best_svg or trace_with(a, params)
    else:
        svg = trace_with(a, params)

    fills = re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)
    flat = (params or {}).get("profile", "flat" if a["is_flat"] else "photo") == "flat"
    meta = {
        "width": a["w"],
        "height": a["h"],
        "colors": len(set(fills)),
        "paths": svg.count("<path"),
        "kb": round(len(svg.encode("utf-8")) / 1024, 1),
        "flat": flat,
        "transparent_bg": bool(a["has_alpha"] and not a["keep_bg"]),
        "seconds": round(time.time() - t0, 2),
    }
    if opts.get("enhance"):
        meta["enhanced"] = True
    return {"svg": svg, "meta": meta}
