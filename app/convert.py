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


def _tidy(svg: str, w: int, h: int, flat: bool = False) -> str:
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = _round_path_data(svg)
    svg = _seal_seams(svg, 2 if flat else 1)
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

    w, h = a["w"], a["h"]
    with tempfile.TemporaryDirectory() as td:
        src = f"{td}/in.png"
        out = f"{td}/out.svg"
        if flat:
            _flatten_colors(a["working"], a["bg_color"] or (0, 0, 0)).save(src)
        else:
            a["working"].save(src)
        vtracer.convert_image_to_svg_py(
            src, out,
            colormode="color", hierarchical="cutout",
            max_iterations=mi, color_precision=cp, layer_difference=ld,
            filter_speckle=sp, corner_threshold=ct,
            length_threshold=lt, path_precision=pp,
        )
        svg = open(out, encoding="utf-8").read()

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
