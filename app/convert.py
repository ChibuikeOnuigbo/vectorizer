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
from PIL import Image, ImageFilter, ImageOps
import vtracer

MAX_EDGE = 1500          # long edge cap for tracing
ALPHA_CUTOFF = 128       # alpha above this = content, below = background
FLAT_ERR = 35.0          # mean 4-color reconstruction error (0-441) below this = flat art

# Hardlocked vtracer tuning (2026-10-05: user decision, data-backed).
# The trained net's numeric head output was sampled over 120 corpus logos:
# cp=3 (62/120), ld=19+-3, fs=2 (109/120), mi=14+-1, profile=flat (85%).
# A 38-row strict A/B of LOCK-medians vs per-image net params: 27 identical
# SVGs, 11 differ by avg +0.65 worst -0.8 — nothing measurable is lost, so
# ui slider numeric knobs, net-emitted numerics, and classic presets are
# all obsolete; every client gets identical behavior (ui == sweep == qa).
LOCK_FLAT = dict(profile="flat", color_precision=3, layer_difference=19,
                 filter_speckle=2, max_iterations=14, corner_threshold=60,
                 length_threshold=4.5, path_precision=10)
LOCK_PHOTO = dict(profile="photo", color_precision=6, layer_difference=12,
                  filter_speckle=4, max_iterations=30, corner_threshold=50,
                  length_threshold=3.5, path_precision=10)
# Numeric keys that were once user/model-tunable; now always locked.
_LOCK_KEYS = ("color_precision", "layer_difference", "filter_speckle",
              "max_iterations", "corner_threshold", "length_threshold",
              "path_precision")
BASELINE_FLAT = LOCK_FLAT
BASELINE_PHOTO = LOCK_PHOTO

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


def _significant_inks(working: Image.Image) -> int:
    """Count non-bg hue buckets with >= 2% coverage (same FASTOCTREE-12
    quantize as _flatten_colors, so the count matches the flattener's own
    vocabulary). Parrot fix (bg-remove-set icon-11, 2026-10-08): flat art
    with 5+ meaningful hues hit the cutout's calibrated max_inks=3 and the
    flattener merged them — black beak vanished into dark blue, white face
    became red/green; structure traced fine, hues wrong. Adaptive inks keep
    every significant hue as its own ink. Measured: parrot ssim 0.381 ->
    0.713 with beak/face/linework back; leaf/anchor/stripes flat trio
    byte-stable (their bucket counts are <= 3, adapt is a no-op).
    Skipped when the user palette knob is explicit (_palette set)."""
    q = working.quantize(colors=12, method=Image.Quantize.FASTOCTREE)
    counts = q.getcolors() or []
    if not counts:
        return 3
    total = sum(c for c, _ in counts) or 1
    classes = sorted(counts, key=lambda t: -t[0])
    return sum(1 for c, _ in classes[1:] if c >= total * 0.02)


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
        # cx-08 salvage (2026-10-08): ultra-low-contrast opaque scans (2%
        # luminance span) are invisible to the 4-bit quantizer AND the
        # tracer's speckle floor — the subject collapses into the bg plate
        # (heart probe: 1 path, 0.4KB, ssim 0.990 lies; heart gone anyway).
        # Gate: opaque AND p1..p99 luminance span in [2,24] -> stretch the
        # WORKING tensor's range to [48,224] (hue-preserving additive map).
        # Calibrated on all 25 probes (15 ladder + 8 complex + 2 uploads):
        # fires only on cx-08; a["img"] untouched so A/B judges score the
        # original; uploads have alpha under 255 (different branch entirely).
        if max(w, h) >= 64:
            L = np.asarray(img.convert("L"), dtype=np.float32)
            p1, p99 = np.percentile(L, (1, 99))
            if 2.0 <= (p99 - p1) <= 24.0:
                scale = (224.0 - 48.0) / max(p99 - p1, 1.0)
                newL = np.clip((L - p1) * scale + 48.0, 0, 255)
                delta = newL - L
                rgb = np.asarray(working, dtype=np.float32)
                working = Image.fromarray(
                    np.clip(rgb + delta[..., None], 0, 255).astype(np.uint8), "RGB")

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


def _texture_bg_regime(img_rgb: Image.Image) -> bool:
    """Calibrated gate (bg-remove-set T3 / icons 07-09, 2026-10-08): dense
    full-bleed LOW-PALETTE texture (kraft paper, denim, halftone) lands the
    band stack in a pathology regime — ~14-16k paths / 7.7MB files editors
    cannot open. Probe: high-frequency energy + palette poverty on a 320px
    downscale. Calibrated on all 15 ladder icons (and their classes):
      lap-mean and distinct-4bit-colors (of 4096 bins) classify 15/15 —
      T3 fires (24.6-131.7 lap / 84-324 bins), T5 maximalist escapes on
      palette (1600-2518 bins), normals escape on lap (2.7-10.6); the only
      bonus hit is prism-stripes (49.8/145, measured harmless: -0.008 ssim).
    Used ONLY to raise the speckle floor (sp 1 -> 6) — geometry-noise
    suppression, inputs/routing untouched."""
    g = img_rgb.resize((320, 320), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    lap = np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1]
                 - a[1:-1, :-2] - a[1:-1, 2:]).mean(2)
    q = (a.astype(np.uint16) >> 4)
    ndist = len(np.unique(q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]))
    return float(lap.mean()) >= 20.0 and ndist <= 400


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


def _trace_color_tone_stack(a: dict, params: dict) -> str:
    """EXPERIMENTAL gradient engine (opt-in only, NOT auto-routed — 2026-10-03
    blur calibration: huge wins on some gradient-degraded art (+55 strict)
    but catastrophic misses on others; kept selectable for the training
    candidate space, never silently applied). k-means RGB into `tone_bands`
    tones, trace cumulative darker masks bottom-up, stack as opaque tone
    layers — gradients become smooth bands instead of cutout fragmentation."""
    img = a["img"].convert("RGBA")
    w, h = a["w"], a["h"]
    arr = np.asarray(img)
    rgb = arr[..., :3].astype(np.float32)
    alpha = arr[..., 3].astype(np.float32) / 255.0
    comp = rgb * alpha[..., None] + 255.0 * (1 - alpha[..., None])
    tones = comp.reshape(-1, 3)
    K = min(max(int(params.get("tone_bands", 7)), 3), 10)
    rng = np.random.default_rng(4)
    C = tones[rng.choice(len(tones), K, replace=False)].copy()
    lab = None
    for _ in range(28):
        d = ((tones[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        NC = np.array([tones[lab == i].mean(axis=0) if (lab == i).any() else C[i]
                       for i in range(K)])
        if np.abs(NC - C).max() < 0.6:
            C = NC
            break
        C = NC
    lab_map = lab.reshape(h, w)
    lum = C.mean(axis=1)
    order = np.argsort(-lum)
    lt = min(max(float(params.get("length_threshold", 0.5)), 0.5), 4.0)
    pp = min(max(int(params.get("path_precision", 10)), 3), 12)
    sp = min(max(int(params.get("filter_speckle", 2)), 0), 16)
    ct = min(max(int(params.get("corner_threshold", 40)), 10), 110)
    paths: list[str] = []
    for rank, ci in enumerate(order):
        m_rgb = C[ci].astype(int)
        hexcol = f"#{int(m_rgb[0]):02X}{int(m_rgb[1]):02X}{int(m_rgb[2]):02X}"
        if rank == 0 and m_rgb.mean() >= 249:
            paths.append(f'<rect width="{w}" height="{h}" fill="{hexcol}"/>')
            continue
        darker = np.isin(lab_map, order[rank:])
        pix = np.where(darker, 0, 255).astype(np.uint8)
        with tempfile.TemporaryDirectory() as td:
            src, out = f"{td}/b.png", f"{td}/b.svg"
            Image.fromarray(pix, "L").save(src)
            vtracer.convert_image_to_svg_py(
                src, out, colormode="binary", hierarchical="stacked",
                filter_speckle=sp, corner_threshold=ct,
                length_threshold=lt, path_precision=pp)
            bsvg = open(out, encoding="utf-8").read()
        bsvg = re.sub(r'fill="(?:#000000|#000|black|rgb\(0,0,0\)|rgb\(0%,0%,0%\))"',
                      f'fill="{hexcol}"', bsvg, flags=re.I)
        paths.extend(re.findall(r'<path\b[^>]*/?>', bsvg))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}">' + "".join(paths) + "</svg>")
    svg = _tidy(svg, w, h, False)
    return re.sub(r'(<svg\b)', r'\1 data-engine="color-tone-stack"', svg, count=1)


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


def _soft_alpha_boost(a: dict) -> dict | None:
    """Last-chance salvage for all-soft-alpha inputs (alpha amax < 0.5).

    Every engine collapses on this regime: the strict-audit sweep population
    scored 0.0 on 15/15 such rows (cutout finds no ink; the mono gate needs a
    strong-alpha core). Normalizing alpha to the full range recovers the mono
    ink shape: blur2/3 text probe 0.0-6.0 -> 66.7-85.1 (8/8 wins, mean +78,
    halo on the boosted image); blur5/6 sample 0.0 -> 38.6/67.0.

    Fires ONLY when the boosted image passes _mono_alpha_candidate, so soft
    photographs/gradients/feathered art never enter this path. Returns a
    freshly analyzed dict of the boosted image (or None when inapplicable).
    """
    cached = a.get("_soft_boost", "unset")
    if cached != "unset":
        return cached
    out = None
    alpha = np.asarray(a["img"].getchannel("A"), dtype=np.float32) / 255.0
    if alpha.size:
        amax = float(alpha.max())
        if 0.05 < amax < 0.5 and bool((alpha > 0.05).any()):
            arr = np.array(a["img"]).astype(np.float32)
            arr[..., 3] = np.clip(arr[..., 3] * (255.0 / max(arr[..., 3].max(), 1.0)), 0, 255)
            b = analyze(Image.fromarray(arr.astype(np.uint8), "RGBA"))
            if _mono_alpha_candidate(b):
                out = b
    a["_soft_boost"] = out
    return out


def _trace_boost_halo(b: dict, params: dict) -> str:
    svg = _trace_alpha_halo_stack(b, params)
    return svg.replace('data-engine="alpha-halo-stack"',
                       'data-engine="soft-alpha-boost-halo"', 1)


def _aa_blend_share(a: dict, probe_edge: int = 192) -> float:
    """Share of ALL pixels that are both palette-ambiguous (nearest color >= 8
    away) and near-tied (top-2 margin < 40): the mass of soft boundary/blend
    content. Calibrated 2026-10-04 over 11 archetypes:
      soft app icon 0.302, blur6 melt 0.443, blur4/6 rows 0.19,
      gen-07noise 0.123, clean logos 0.009-0.056, ghost blur2 text 0.000.
    (Normalizing by only-ambiguous pixels inflated clean logos: their few AA
    pixels ARE blended by definition -- 0.32 on crisp art; whole-image share
    keeps them at ~0.02.)"""
    work = np.asarray(a["working"].resize((min(probe_edge, a["w"]),
                                           min(probe_edge, a["h"]))), dtype=np.float32)
    q = Image.fromarray(work.astype(np.uint8)).quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    raw = q.getpalette() or [0, 0, 0]
    k = len(raw) // 3
    if k < 2:
        return 0.0
    pal = np.asarray(raw[: k * 3]).reshape(k, 3).astype(np.float32)
    d = np.sqrt(((work[..., None, :] - pal[None, None, :, :]) ** 2).sum(-1)).reshape(-1, k)
    ds = np.partition(d, 1, axis=-1)
    cand = ds[:, 0] >= 8.0
    tie = (ds[:, 1] - ds[:, 0]) < 40.0
    return float((cand & tie).mean())


def _melt_share(a: dict, probe: int = 256) -> float:
    """Share of content pixels with a strong color-max gradient (>0.098):
    measure of edge sharpness. Guard: luma-only gradients miss 2-tone
    canvases whose bg and ink share one luminance (measured: max grad
    0.008 on a crisp corpus logo)."""
    im = a["working"].resize((min(probe, a["w"]), min(probe, a["h"])))
    g = np.asarray(im, dtype=np.float32) / 255.0
    grad = np.zeros(g.shape[:2], dtype=np.float32)
    for c in range(3):
        gx = np.abs(np.diff(g[..., c], axis=1))
        gy = np.abs(np.diff(g[..., c], axis=0))
        grad[:, 1:] = np.maximum(grad[:, 1:], gx)
        grad[1:, :] = np.maximum(grad[1:, :], gy)
    if a["has_alpha"]:
        am = np.asarray(a["img"].getchannel("A").resize(im.size)) > 25
        sub = grad[am]
    else:
        sub = grad
    if not sub.size:
        return 1.0
    return float((sub > 25 / 255.0).mean())


def _melt_candidate(a: dict) -> bool:
    """Melted/deep-blur content (partial gradients, rich ink population):
    0.012 < strong-grad share < 0.12 AND quantized-ink bins >= 18.
    Calibrated 2026-10-04 (19 archetypes + 24 blur4-6 sweep rows):
      winners blur4-6 melt 0.019-0.074 inks 21-77 (soft-stack direct avg
      81.4 vs old-route 47.1); excluded: crisp 0.000-0.0067, gen-noise/jit
      0.21-0.23, teal-crisp 0.38, near-empty 2-ink canvases (edge-big1024:
      melt 0.06 but inks 13 -> soft-stack 35 vs cutout 87.5).
    is_flat intentionally NOT required: heavy blur inflates flat_err to
    38-50 exactly where the salvage matters most."""
    share = _melt_share(a)
    if not (0.012 < share < 0.12):
        return False
    im = a["working"].resize((min(256, a["w"]), min(256, a["h"])))
    rgb = np.asarray(im, np.uint8).reshape(-1, 3)
    q = (rgb // 8)
    keys = (q[:, 0].astype(np.int32) * 65536 + q[:, 1].astype(np.int32) * 256
            + q[:, 2])
    _, cnt = np.unique(keys, return_counts=True)
    inks = int((cnt > rgb.shape[0] * 0.001).sum())
    return inks >= 18


def _ab_svg_score(inp: Image.Image, svg: str, size: int = 128) -> float:
    """Cheap in-process A/B score for engine adjudication when the heuristic
    gate can't separate (melt family, 2026-10-04): rasterize ALL paths with
    PIL polygons at ~128px (vtracer output: absolute d + one translate each;
    curves approximated by anchor+control points), compare silhouette IoU
    (alpha>0.1) and white-flattened MAE against the input; composite
    0.4*IoU + 0.6*(1-mae). Calibrated: LOSE melts (rot/jpeg/pixel/blur2) sit
    -28..-59 vs cutout, WIN melts (blur4-6) +8.4..+23; swap margin +5."""
    from PIL import ImageDraw
    m = re.search(r'viewBox="([^"]+)"', svg)
    if not m:
        return 0.0
    vb = [float(x) for x in m.group(1).split()]
    vw, vh = vb[2] or 1.0, vb[3] or 1.0
    scale = size / max(vw, vh)
    W, H = max(2, int(vw * scale)), max(2, int(vh * scale))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(out)
    for pth in re.findall(r'<path\b[^>]*>', svg):
        f = re.search(r'fill="(#[0-9A-Fa-f]{6})"', pth)
        d = re.search(r'd="([^"]+)"', pth)
        if not f or not d:
            continue
        t = re.search(r'translate\(([-0-9.]+)[, ]+([-0-9.]+)\)', pth)
        tx = float(t.group(1)) if t else 0.0
        ty = float(t.group(2)) if t else 0.0
        nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', d.group(1))]
        fo = re.search(r'fill-opacity="([\d.]+)"', pth)
        op = int(255 * float(fo.group(1))) if fo else 255
        pts = [((nums[i] + tx) * scale, (nums[i + 1] + ty) * scale)
               for i in range(0, len(nums) - 1, 2)]
        if len(pts) >= 3:
            r_, g_, b_ = (int(f.group(1)[j:j + 2], 16) for j in (1, 3, 5))
            dr.polygon(pts, fill=(r_, g_, b_, op), outline=(r_, g_, b_, op))
    o = np.asarray(out, np.float32)
    arr = np.asarray(inp.resize((W, H), Image.LANCZOS).convert("RGBA"), np.float32)
    ai, ao = arr[..., 3] / 255.0, o[..., 3] / 255.0
    mi, mo = ai > 0.1, ao > 0.1
    uni = float((mi | mo).sum())
    iou = float((mi & mo).sum()) / uni if uni else 1.0
    fa = arr[..., :3] * ai[..., None] + 255.0 * (1 - ai[..., None])
    fb = o[..., :3] * ao[..., None] + 255.0 * (1 - ao[..., None])
    mae = float(np.abs(fa - fb).mean()) / 255.0
    return iou * 40.0 + (1.0 - min(mae * 2.0, 1.0)) * 60.0


def _color_soft_candidate(a: dict) -> bool:
    """Soft-blend color art (glow/AA-gradient icons): multi-color (mono gate
    already diverted), small palette error, large boundary-blend share.
    Photos (flat_err) and pure noise (small share) stay out; all-soft alpha
    is owned by the boost salvage."""
    if not a.get("is_flat"):
        return False
    if a["has_alpha"]:
        alp = np.asarray(a["img"].getchannel("A"), dtype=np.float32) / 255.0
        if not float((alp > 0.5).mean()) >= 0.002:
            return False
    return _aa_blend_share(a) >= 0.15



def _trace_color_soft_stack(a: dict, params: dict) -> str:  # noqa: C901 - engine body
    """Soft-art full-fidelity stack: vtracer full-color STACKED cutout over
    the bg-flattened canvas (photo-grade plates, cp8 by default), with the
    flattened bg plate removed (geometry-detected, not color-matched) and
    the input's original alpha glow re-attached as honest-mean band plates.

    Evidence chain on download.png (strict/verdict):
      cutout                      58.8 FAIL  (hard aliases destroy banding)
      level-set soft plates       ~56 FAIL   (flat plates have zero interior
                                   variance; block-SSIM reads input banding)
      stacked cp4                 63.5 FAIL  (bg plate floods canvas: IoU .63)
      stacked cp8 ld4             63.5 FAIL  (ssim .804 / mae 1.97 / IoU .63)
      + geometry bg-strip         68.9 FAIL  (faint outer glow died with bg)
      + honest glow bands x2      74.5 WEAK  (IoU .98 / ssim .75 / mae 1.46)
    Remaining gap is intra-block banding texture around micro figures;
    logged in model_result/README.md, to be pushed by training data.
    """
    img = a["img"].convert("RGBA")
    alp = np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0
    h, w = alp.shape

    if max(w, h) > 640:
        max_down = 640.0 / max(w, h)
        work_img = img.resize((max(1, round(w * max_down)), max(1, round(h * max_down))),
                              Image.LANCZOS)
        alp_s = np.asarray(work_img.getchannel("A"), dtype=np.float32) / 255.0
        hs, ws = work_img.size[1], work_img.size[0]
    else:
        work_img, alp_s, hs, ws = img, alp, h, w

    # User palette knob: fewer/more inks than the full-fidelity default.
    # Quantize inks in the opacity region before flattening (REquantize is
    # only applied at explicit high-low request; default path untouched).
    pal_inks = int(params.get("max_inks") or 0)
    if pal_inks:
        pal_inks = min(max(pal_inks, 2), 12)
        rgb = work_img.convert("RGB")
        mask = (np.asarray(work_img.getchannel("A"), dtype=np.float32) / 255.0) > 0.004
        q = rgb.quantize(colors=pal_inks, method=Image.Quantize.MEDIANCUT)
        qa = np.asarray(q.convert("RGB"), dtype=np.uint8).copy()
        src_rgb = np.asarray(rgb, dtype=np.uint8)
        qa[~mask] = src_rgb[~mask]
        work_img = Image.fromarray(qa, "RGB").convert("RGBA")
        work_img.putalpha(Image.fromarray((alp_s * 255).astype(np.uint8), "L"))

    canvas = Image.new("RGBA", (ws, hs), (255, 255, 255, 255))
    canvas.paste(work_img, (0, 0), work_img)
    sent = None
    if a["has_alpha"]:
        # Sentinel-flood ONLY the border-disconnected transparent cavities
        # (interior holes): vtracer fills them with near-white plates that
        # inflate the silhouette (teal ring interior = +9.8k px, IoU 0.66;
        # direct soft-stack 66.1 FAIL -> 85.8 PASS). Flooding border-
        # connected outer regions is skipped: a saturated 33%-mass blob
        # adjacent to content distorts vtracer's cp8 bucket allocation
        # (0171 regressed 85.3 PASS -> 57.7 FAIL with full-canvas flood).
        zero = alp_s < 0.008
        if zero.any():
            from collections import deque
            border = np.zeros_like(zero)
            q = deque()
            H_, W_ = zero.shape
            for x in range(W_):
                for y in (0, H_ - 1):
                    if zero[y, x] and not border[y, x]:
                        border[y, x] = True
                        q.append((y, x))
            for y in range(H_):
                for x in (0, W_ - 1):
                    if zero[y, x] and not border[y, x]:
                        border[y, x] = True
                        q.append((y, x))
            while q:
                y, x = q.popleft()
                for dy, dx_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx_ = y + dy, x + dx_
                    if 0 <= ny < H_ and 0 <= nx_ < W_ and zero[ny, nx_] and not border[ny, nx_]:
                        border[ny, nx_] = True
                        q.append((ny, nx_))
            inner = zero & ~border
            if inner.any():
                sent = (255, 0, 255)
                rgb_arr = np.asarray(canvas, dtype=np.uint8).copy()
                inp_hit = np.asarray(work_img.convert("RGB"), dtype=np.int16)
                if (np.abs(inp_hit - np.array(sent, dtype=np.int16)).sum(-1) < 96).any():
                    sent = (57, 255, 20)  # avoid colliding with real content
                rgb_arr[inner, :3] = sent
                rgb_arr[inner, 3] = 255
                canvas = Image.fromarray(rgb_arr, "RGBA")

    # cp is load-bearing, not a taste knob: this family dies at cp<=6
    # (measured: blur6 ring 85.2 PASS @cp8 -> 9.2 FAIL @cp6 with 359 junk
    # plates; bird 74.5 -> 60.8). The engine owns 8-bit color fidelity;
    # user/model color_precision applies to the cutout engines only.
    cp = 8
    sp = min(max(int(params.get("filter_speckle", 1)), 1), 16)
    # T3 textured-bg adapt (bg-remove-set 2026-10-08, pre-registered): when
    # the calibrated texture gate fires, raise the speckle floor 1 -> 6.
    # Measured on icons 07/08/09/12: paths -60..-66%, bytes -26..-40%,
    # ssim 0.672->0.588, 0.610->0.529, 0.878->0.896 (gain), 0.895->0.888.
    # sp=8/10 REJECTED by the rule (07/08 drop >0.08; icon-09's halftone
    # dots die at sp=10: -0.37 ssim). Gate provably cannot touch the
    # calibrated bird-class rows: probe fires on none of them (opaque
    # uploads byte-identical before/after — regression gate below).
    if sp < 6 and not a["has_alpha"] and _texture_bg_regime(work_img.convert("RGB")):
        sp = 6
    ct = min(max(int(params.get("corner_threshold", 30)), 10), 110)
    lt = min(max(float(params.get("length_threshold", 1.0)), 0.5), 10.0)
    pp = min(max(int(params.get("path_precision", 4)), 3), 12)
    mi = min(max(int(params.get("max_iterations", 48)), 8), 48)

    with tempfile.TemporaryDirectory() as td:
        src, out = f"{td}/in.png", f"{td}/out.svg"
        canvas.convert("RGB").save(src)
        vtracer.convert_image_to_svg_py(
            src, out, colormode="color", hierarchical="stacked",
            max_iterations=mi, color_precision=cp, layer_difference=4,
            filter_speckle=sp, corner_threshold=ct,
            length_threshold=lt, path_precision=pp)
        svg = open(out, encoding="utf-8").read()

    # Pop the flattened canvas' bg mass: plates whose bbox spans ~ the whole
    # viewBox AND whose fill is near-white (the synthetic flatten color).
    kept = []
    for pth in re.findall(r'<path\b[^>]*>', svg):
        f = re.search(r'fill="(#[0-9A-Fa-f]{6})"', pth)
        d = re.search(r'd="([^"]+)"', pth)
        t = re.search(r'translate\(([-0-9.]+)[, ]+([-0-9.]+)\)', pth)
        if f and d:
            r, g, b = (int(f.group(1)[i:i + 2], 16) for i in (1, 3, 5))
            nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', d.group(1))]
            if sent is not None:
                # sentinel-flooded inner cavities: drop vtracer buckets that
                # landed near the sentinel color (the hole floods)
                if abs(r - sent[0]) + abs(g - sent[1]) + abs(b - sent[2]) <= 96:
                    continue
            near_bg = abs(r - 255) + abs(g - 255) + abs(b - 255) <= 40
            if near_bg and len(nums) >= 4:
                xs, ys = nums[0::2], nums[1::2]
                tx = float(t.group(1)) if t else 0.0
                ty = float(t.group(2)) if t else 0.0
                bw = (max(xs) + tx) - (min(xs) + tx)
                bh = (max(ys) + ty) - (min(ys) + ty)
                if bw / max(ws, 1) >= 0.94 and bh / max(hs, 1) >= 0.94:
                    continue
        kept.append(pth)

    # Re-attach the original alpha glow as honest-mean band plates UNDER the
    # stack: recovers the input silhouette extent the bg-pop removes, with
    # tint strength matched to the real alpha field (opacity = band mean;
    # fixed stronger values visibly tint edge blocks, measured on bird).
    glow_layers: list[str] = []
    for lo, hi in ((0.055, 0.25), (0.25, 0.60)):
        m = alp_s >= lo
        inner = (alp_s >= lo) & (alp_s < hi)
        if int(m.sum()) < 16 or not inner.any():
            continue
        rgb_s = np.asarray(work_img.convert("RGB"), dtype=np.float32)
        gc = rgb_s[inner & (alp_s > 0.0)].mean(0)
        hexg = "#%02X%02X%02X" % tuple(gc.astype(int))
        op = float(alp_s[inner].mean())
        pix = np.where(m, 0, 255).astype(np.uint8)
        with tempfile.TemporaryDirectory() as td:
            src, out = f"{td}/m.png", f"{td}/m.svg"
            Image.fromarray(pix, "L").save(src)
            vtracer.convert_image_to_svg_py(
                src, out, colormode="binary", hierarchical="stacked",
                filter_speckle=sp, corner_threshold=ct,
                length_threshold=lt, path_precision=pp)
            bsvg = open(out, encoding="utf-8").read()
        for pth in re.findall(r'<path\b[^>]*/?>', bsvg):
            pth = re.sub(r'fill="(?:#000000|#000|black)"', f'fill="{hexg}"',
                         pth, flags=re.I)
            if "fill-opacity" not in pth:
                pth = pth.replace("/>", f' fill-opacity="{op:.3f}"/>')
            glow_layers.append(pth)

    body = "".join(glow_layers + kept)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ws}" height="{hs}" '
           f'viewBox="0 0 {ws} {hs}">' + body + "</svg>")
    # _tidy normalizes the <svg> tag to the (ws, hs) frame: passing original
    # (w, h) here mismatches width/height vs viewBox for >640px inputs and
    # the rendered surface zoom-clips 1.6x (edge-big1024 scored 56.1 FAIL on
    # a faithful geometry until this was fixed).
    svg = _tidy(svg, ws, hs, False, seal=0)
    # User-facing dims stamp (bg-remove-set finding 2026-10-08): the working
    # frame is capped at 640px for speed, but a 1024px upload then ships as a
    # 640px SVG while meta.width/height report 1024 — UI previews and Figma
    # imports land at the wrong size. Keep the 640-frame viewBox (SVG scales
    # losslessly) and stamp the INPUT dims; geometry untouched.
    if (ws, hs) != (a["w"], a["h"]):
        svg = svg.replace(f'width="{ws}" height="{hs}" viewBox',
                          f'width="{a["w"]}" height="{a["h"]}" viewBox', 1)
    return re.sub(r'(<svg\b)', r'\1 data-engine="color-soft-stack"', svg, count=1)

def _mono_route(a: dict) -> str:
    """Calibrated mono-alpha routing via radial statistics (2026-10-03,
    72-image calibration set): strong_share splits sparse from dense;
    radial center-of-mass (mean ellipse-normalized distance of strong
    pixels) splits ring/halo art from scattered glyphs.
      share <=0.02                        -> binary (ultra-sparse text/lines:
                                             halo's window means starve the
                                             few pixels; binary +13 avg, halo
                                             losses to -78 on text corpus)
      0.02<share<=0.17 & mean_d>=0.68     -> halo (ring-halo art: 6/6 wins
                                             +5.6 avg, teal 87.9 vs 87.2)
      0.02<share<=0.17 & mean_d<=0.56     -> halo (compact halo glyphs: 3/3)
      0.02<share<=0.17 & 0.56<mean_d<0.68 -> binary (mixed zone: 3/3)
      share > 0.17                        -> binary (dense fills: +12..+54)
    """
    alpha = np.asarray(a["img"].getchannel("A"), dtype=np.float32) / 255.0
    strong = alpha > 0.5
    share = float(strong.mean())
    if share <= 0.02:
        # sparse ink: a pixel-hard skirt (alpha>0.05 spread / alpha>0.5 core
        # ~1-3) keeps binary ahead (Round-9 no-re-gate on jit/scale rows), but
        # a melted skirt ratio >= 10 (blur2-3, jpeghard, heavy-posterize)
        # scores 1.7-24.5 under binary while halo recovers 78-90. Measured on
        # 12 corpus rows in this build: 11 wins / 1 loss (+65 mean) -> halo.
        skirt = float((alpha > 0.05).mean())
        if skirt / max(share, 1e-6) >= 10.0:
            return "halo"
        return "binary"
    if share > 0.17:
        return "binary"
    ys, xs = np.nonzero(alpha > 0.02)
    cx, cy = float(xs.mean()), float(ys.mean())
    rx = max((float(xs.max()) - float(xs.min())) / 2.0, 1.0)
    ry = max((float(ys.max()) - float(ys.min())) / 2.0, 1.0)
    yy, xx = np.mgrid[0:alpha.shape[0], 0:alpha.shape[1]]
    d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    mean_d = float(d[strong].mean())
    if mean_d >= 0.68 or mean_d <= 0.56:
        return "halo"
    return "binary"


def trace_with(a: dict, params: dict | None = None) -> str:
    """Run one vectorization pass. Vtracer tuning numerics are HARDLOCKED
    (LOCK_FLAT/LOCK_PHOTO; see calibration note) — incoming numeric keys are
    ignored unless params['_unlock'] is set (QA/experiments only). Only
    profile may be overridden ("flat"/"photo"); engine routing stays smart."""
    params = params or {}
    # HARDLOCK: strip every free tuning key (incl. the engine-shared ones:
    # filter_speckle/corner_threshold/length_threshold/path_precision/
    # max_iterations/tone_bands/halo_bands/pixel_colors/stroke_width/max_inks)
    # so external input can never perturb the traced geometry. Engines keep
    # their calibrated defaults; vtracer numerics resolve from LOCK_* below.
    # QA/experiment callers pass _unlock=True to bypass this.
    if not params.get("_unlock"):
        pal = params.get("_palette")  # {"cp": n, "max_inks": n} from the one user knob
        # _palette must survive too: downstream routes (soft-stack pal_inks,
        # the fallback A/B skip) read it — the strip used to drop it, which
        # contradicted the "survives the hardlock strip" contract documented
        # in vectorize() (latent until routes started reading it 2026-10-07).
        params = {k: v for k, v in params.items() if k in ("engine", "profile", "_palette")}
        if pal:
            params["color_precision"] = pal["cp"]
            params["max_inks"] = pal["max_inks"]
            # banding-family sibling of the same knob: tone/soft-stack read
            # tone_bands from params (defaults are the calibrated constants)
            params["tone_bands"] = pal["tone_bands"]
    base = LOCK_FLAT if params.get("profile", "flat" if a["is_flat"] else "photo") == "flat" else LOCK_PHOTO
    flat = base["profile"] == "flat"
    if params.get("_unlock"):
        cp = int(params.get("color_precision", base["color_precision"]))
        ld = int(params.get("layer_difference", base["layer_difference"]))
        sp = int(params.get("filter_speckle", base["filter_speckle"]))
        mi = int(params.get("max_iterations", base["max_iterations"]))
        ct = int(params.get("corner_threshold", base["corner_threshold"]))
        lt = float(params.get("length_threshold", base["length_threshold"]))
        pp = int(params.get("path_precision", base["path_precision"]))
    else:
        cp, ld, sp, mi = (base["color_precision"], base["layer_difference"],
                          base["filter_speckle"], base["max_iterations"])
        ct, lt, pp = (base["corner_threshold"], base["length_threshold"],
                      base["path_precision"])
        # one-way palette override from the user knob (cutout-ish families)
        if "color_precision" in params:
            cp = int(params["color_precision"])
    # cp=1 collapses every ink bucket into the bg bucket -> empty shell; the
    # known floor lives in the locks but keep the guard for _unlock callers.
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
    if params.get("engine") == "alpha-halo-stack":
        b = _soft_alpha_boost(a)
        if b is not None:
            return _trace_boost_halo(b, params)
    if params.get("engine") == "binary-alpha-mono" and _mono_alpha_candidate(a):
        return _trace_binary_alpha(a, params)
    if params.get("engine") == "color-tone-stack":
        return _trace_color_tone_stack(a, params)
    if params.get("engine") == "pixel-art":
        return _trace_pixel_art(a, params)
    # soft-blend color art (glow/AA icons) FIRST: bird-class rows melt-band
    # falsely too, and their A/B judge at 128px favors aliased cutouts
    # (measured: ss 74.6 lost to cutout 57.4); they own this route.
    if params.get("engine") == "color-soft-stack" or (
            params.get("engine") not in ("color-cutout",)
            and _color_soft_candidate(a)):
        return _trace_color_soft_stack(a, params)
    # Melted-content route (deep-blur salvage): BEFORE the mono gate, because
    # blurred mono melts score 15-58 under binary-alpha but 59-87 under the
    # full-fidelity stack (measured on 19 blur4-6 sweep FAILs: family avg
    # 47.1 -> 81.4). The gate alone over-fires on rot/jpeg/pixel partial
    # melts (sweep regressions -10..-35), so the final call is a raster A/B
    # vs the cutout default with +5 margin (see _ab_svg_score calibration).
    if (params.get("engine") not in ("color-cutout",)
            and not a.get("_melt_route_seen")
            and _melt_candidate(a)
            and _soft_alpha_boost(a) is None):
        ss_svg = _trace_color_soft_stack(a, params)
        # the honest BASE candidate is the whole fall-through chain (mono
        # gate included): heavy/jit mono-elems sit in the melt band too and
        # binary-alpha owns them (v3 sweep: 8 rows won -4..-15 when judging
        # vs plain cutout only; recursing once with a re-entry guard fixes).
        a["_melt_route_seen"] = True
        base_svg = trace_with(a, params)
        del a["_melt_route_seen"]
        if _ab_svg_score(a["img"], ss_svg) > _ab_svg_score(a["img"], base_svg) + 5.0:
            return ss_svg
        return base_svg
    # Engine route: monochrome transparent content via the calibrated
    # radial gate (see _mono_route). Applies to every caller that did not
    # explicitly force color-cutout (incl. model mode).
    if params.get("engine") != "color-cutout" and _mono_alpha_candidate(a):
        if _mono_route(a) == "halo":
            return _trace_alpha_halo_stack(a, params)
        return _trace_binary_alpha(a, params)
    # all-soft-alpha salvage (measured regime: 15/15 sweep rows score 0.0
    # here; boost+halo recovers 38-85%). Mono-candidate-checked on the boosted
    # image only, so photos/gradients cannot enter.
    if params.get("engine") != "color-cutout":
        b = _soft_alpha_boost(a)
        if b is not None:
            return _trace_boost_halo(b, params)
        if not params.get("_palette"):
            # (_palette = explicit user palette-size request: the knob's color
            # bound is a cutout-family contract the soft-stack's re-attached
            # glow bands cannot honor — palette checks measured 35 colors at
            # colors=4 when the A/B below swapped the route. Knobbed requests
            # keep the historical path: engine gates above, then cutout.)
            # Plain-fallback A/B (v6 wall evidence 2026-10-07): rows that reach
            # this point were claimed by NO family gate, and the v6 sweep's 55
            # strict-FAILs clustered exactly here — the default 3-ink cutout
            # merged distinct brand colors (IoU 0.65-0.69) while forced
            # color-soft-stack flipped 22/55 FAIL->PASS and 12/55 FAIL->WEAK
            # (mean +15.2). The probe's only losses sat in the mono-alpha
            # family, which the gates ABOVE divert before this point, so they
            # cannot be reached here. Render both candidates and keep the
            # soft-stack only when the calibrated judge (_ab_svg_score,
            # IoU*40+color*60) prefers it by the melt route's +5 margin;
            # measured per image, never fixed.
            ss_svg = _trace_color_soft_stack(a, params)
            base_svg = _trace_cutout(a, params, flat, cp, ld, sp, mi, ct, lt, pp, inks)
            if _ab_svg_score(a["img"], ss_svg) > _ab_svg_score(a["img"], base_svg) + 5.0:
                return ss_svg
            return base_svg

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

    # Parrot-hue fix (bg-remove-set icon-11): raise the ink budget to the
    # image's own significant-hue count unless the user palette knob pinned
    # it explicitly (_palette: knob is a contract; honor it verbatim).
    if flat and not params.get("_palette"):
        inks = min(12, max(inks, _significant_inks(a["working"])))
    svg = _run(mi, cp, ld, sp, ct, lt, pp, inks, detail=False)
    stamp = "color-cutout"
    # Detail retry (measured 2026-09-27): flat art traced into so few paths
    # means micro cutouts (beak slits, eye gaps) got merged by the coarse
    # preset (lt 4.5 / cp 2-3 / speckle). Retry with detail settings; gains
    # up to +7.7 (bird icon) with worst case -2.1 noise on 26 corpus images.
    if flat and len(re.findall(r"<path\b", svg)) <= 6 and params.get("detail_retry", True):
        svg_detail = _run(20, 5, 12, 0, 40, 0.5, pp, inks, detail=True)
        # Scorer-judged A/B (2026-10-05): retry rescued thin-detail classes in
        # the classic-preset era (bird 57.7 fix), but gen-07/08 families lose
        # 3-8 strict points (LOCK era fires the trigger more often). Compare
        # both candidates with the trained geometry scorer; detail needs a
        # +0.4 margin (its precision bias), else keep the primary cutout.
        img = a["img"]
        p_score = _score_svg(img, svg)
        d_score = _score_svg(img, svg_detail)
        if d_score > p_score + 0.4:
            svg, stamp = svg_detail, "color-cutout-detail"

    if a["has_alpha"] and not a["keep_bg"]:
        svg = _strip_color(svg, a["bg_color"], a["content_palette"])

    # attribution (after _tidy, which rewrites the opening tag): engine :=
    # actual route (was '?' in gallery/index mixes)
    svg = _tidy(svg, w, h, flat)
    return re.sub(r'(<svg\b)', rf'\1 data-engine="{stamp}"', svg, count=1)


def _collapse_palette(svg: str, tol: int = 14) -> str:
    """Collapse near-duplicate output fills (bg-remove-set T5 finding
    2026-10-08): full-bleed maximalist art traced at cp6 produces ~8k
    distinct fills ≈ one per path — meta.colors is meaningless and editors
    choke. Greedy frequency-ordered clustering rewrites paths to a few
    hundred cluster centers. tol calibrated against renders of icons 13-15
    (ssim of collapsed render vs uncollapsed, pre-registered floor 0.995):
      tol=9  min-ssim 0.9982 (≈1.0-1.5k fills)
      tol=14 min-ssim 0.9953 (414-636 fills)  <- shipped
      tol=20 min-ssim 0.9900 (179-292 fills)  rejected: below floor
    Applied only when the output exceeds 512 distinct fills, so normal
    icons are untouched."""
    fills = re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)
    from collections import Counter
    freq = Counter(fills)
    centers: list[list[int]] = []   # [r, g, b] hex ints of cluster centers
    cmap: dict[str, str] = {}
    for col, _n in sorted(freq.items(), key=lambda kv: -kv[1]):
        r, g, b = (int(col[i:i+2], 16) for i in (1, 3, 5))
        hit = None
        for c in centers:
            if abs(c[0] - r) <= tol and abs(c[1] - g) <= tol and abs(c[2] - b) <= tol:
                hit = c
                break
        if hit is None:
            centers.append([r, g, b])
            hit = centers[-1]
        cmap[col] = f'#{hit[0]:02X}{hit[1]:02X}{hit[2]:02X}'
    def _sub(m):
        key = '#' + m.group(1)
        return f'fill="{cmap.get(key, key)}"'
    return re.sub(r'fill="#([0-9A-Fa-f]{6})"', _sub, svg)


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

    mode_opts keys (the only user-visible variability, vectorizer.ai-style):
    colors (palette size 2..128) and engine (forced engine name, QA)."""
    opts = mode_opts or {}
    t0 = time.time()
    img = Image.open(io.BytesIO(img_bytes))
    # EXIF orientation is display metadata, not pixels (vet round 3, F1):
    # phones store sensor orientation and a rotate tag; tracing the stored
    # tensor silently vectorizes the user's picture sideways. Transpose to
    # the DISPLAYED orientation first (no-op when no tag is present).
    img = ImageOps.exif_transpose(img)
    a = analyze(img)
    params = params or {}
    if opts.get("colors") is not None:
        # The one user-facing knob: palette size. Narrow one-way channel —
        # survives the trace_with hardlock strip, influences palette only.
        c = min(128, max(2, int(opts["colors"])))
        bits = int(round(np.log2(c)))
        params["_palette"] = {"cp": max(2, min(8, bits)),
                              "max_inks": min(12, max(2, c)),
                              "tone_bands": max(3, min(10, bits))}

    engine = opts.get("engine")
    if engine:
        params = dict(params or {})
        params["engine"] = engine
    svg = trace_with(a, params)
    fills = re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)
    if len(set(fills)) > 512:
        svg = _collapse_palette(svg)
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
