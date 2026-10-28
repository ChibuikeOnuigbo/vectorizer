"""Dataset step 3: generate the visible ~200-image diverse test corpus + the
intentionally difficult composite image (directive sections 3 and 5).

Reuses the repo's proven generators (model.make_logos, model.gen_text_no_bg)
for logo/text bases, then applies deterministic condition variants:
blur, noise, jpeg compression, downscale, rotation, dark backgrounds,
grayscale, thin strokes, big/small resolutions, transparency kept where
synthesized.

  PYTHONPATH=vendor:app/deps:. python3 scripts/dataset/gen_corpus.py
"""
from __future__ import annotations

import io
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(ROOT / "vendor"), str(ROOT / "app/deps"), str(ROOT)):
    sys.path.insert(0, p)

from PIL import Image, ImageDraw, ImageFilter, ImageOps  # noqa: E402

from model.make_logos import make_logo  # noqa: E402
from model.gen_text_no_bg import gen_one  # noqa: E402

OUT = ROOT / "test-assets/images/generated"
META: list[dict] = []


def rec(name: str, im: Image.Image, category: str, note: str, variant_of: str | None = None,
        size: tuple[int, int] | None = None) -> None:
    if size and size != im.size:
        im = im.resize(size, Image.LANCZOS)
    path = OUT / name
    im.save(path)
    META.append({
        "file": f"test-assets/images/generated/{name}",
        "provenance": "GENERATED",
        "asset_kind": "ORIGINAL_ASSET" if variant_of is None else "DERIVED_TEST_VARIANT",
        "variant_of": variant_of,
        "category": category,
        "note": note,
        "dimensions": list(im.size),
        "file_type": "png",
        "has_alpha": im.mode == "RGBA",
    })


def base(idx: int, seed: int, size: int = 256) -> Image.Image:
    rng = random.Random(seed)
    im = make_logo(rng, idx, no_text=(idx % 2 == 0))
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return im


def flat(bg_rgb, size=256) -> Image.Image:
    return Image.new("RGBA", (size, size), bg_rgb + (255,))


def difficult_composite() -> Image.Image:
    """Section 5: one intentionally hard high-res asset mixing every challenge."""
    W = H = 1024
    im = Image.new("RGBA", (W, H), (248, 249, 251, 255))
    d = ImageDraw.Draw(im)
    # large flat areas + clean geometry
    d.rectangle([24, 24, 1000, 1000], outline=(31, 41, 55, 255), width=8)
    d.rectangle([60, 60, 360, 360], fill=(226, 232, 240, 255), outline=(15, 23, 42, 255), width=6)
    # gradient band (diagonal)
    for x in range(0, 620):
        t = x / 620
        r = int(37 + (239 - 37) * t)
        g = int(99 + (68 - 99) * t)
        b = int(235 + (68 - 235) * t)
        d.line([(60 + x, 420), (60 + x, 620)], fill=(r, g, b, 255))
    # nested shapes / ring
    cx, cy = 780, 170
    for i, rad in enumerate((150, 118, 86, 54, 22)):
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                  outline=None, fill=(255, (90 + 30 * i) % 255, 120, 255) if i % 2 == 0 else (255, 255, 255, 255))
    # thick strokes
    d.line([(80, 700), (420, 940)], fill=(2, 132, 199, 255), width=34)
    d.line([(80, 940), (420, 700)], fill=(2, 132, 199, 255), width=34)
    # thin strokes / tiny details
    for k in range(9):
        y = 700 + k * 22
        d.line([(500, y), (940, y)], fill=(17, 24, 39, 255), width=2 if k % 2 else 1)
        d.ellipse([955, y - 3, 961, y + 3], fill=(220, 38, 38, 255))
    # overlapping translucent forms
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(overlay)
    do.ellipse([300, 460, 560, 720], fill=(34, 197, 94, 150))
    do.ellipse([420, 460, 680, 720], fill=(168, 85, 247, 150))
    im.alpha_composite(overlay)
    # holes / cutouts (transparent middle)
    d.regular_polygon((200, 520, 120), 6, rotation=0, fill=(245, 158, 11, 255))
    d.regular_polygon((200, 520, 70), 6, rotation=0, fill=(248, 249, 251, 255))
    # text with anti-aliased edges
    d.text((500, 780), "VQ-x1024", fill=(15, 23, 42, 255))
    # scattered disconnected elements
    rng = random.Random(4242)
    for _ in range(24):
        x, y = rng.randint(40, 990), rng.randint(40, 990)
        d.ellipse([x, y, x + 6, y + 6], fill=(30, 41, 59, 255))
    return im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    META.clear()
    rng = random.Random(20260925)

    # --- section 3: diverse categories, ~24 variants per base logo ---
    bases = []
    for i in range(24):
        seed = 100_000 + rng.randrange(10_000_000)
        im = base(i, seed)
        name = f"gen-{i:02d}-base.png"
        rec(name, im, "logo" if i % 2 else "simple icon",
            "procedural generator (model/make_logos.py)")
        bases.append((i, name, im))

    conditions = 0
    for i, name, im in bases:
        stem = name[:-9]
        rec(f"{stem}blur.png", im.filter(ImageFilter.GaussianBlur(2.2)),
            "blurred image", "gaussian blur r2.2", variant_of=name)
        noisy = im.copy()
        px = noisy.load()
        for _ in range(im.size[0] * im.size[1] // 8):
            x, y = rng.randint(0, im.size[0] - 1), rng.randint(0, im.size[1] - 1)
            r, g, b, a = px[x, y]
            delta = rng.randint(-64, 64)
            px[x, y] = (max(0, min(255, r + delta)), max(0, min(255, g + delta)), max(0, min(255, b + delta)), a)
        rec(f"{stem}noise.png", noisy, "noisy image", "uniform rgb noise 12.5% px", variant_of=name)
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=22)
        rec(f"{stem}jpeg.jpg.png", Image.open(io.BytesIO(buf.getvalue())).convert("RGBA"),
            "compressed JPEG", "jpeg q22 round-trip", variant_of=name)
        rec(f"{stem}downscale32.png", im, "very small image", "32x32 lanczos", size=(32, 32))
        rec(f"{stem}darkbg.png", Image.alpha_composite(flat((10, 12, 24)), im),
            "dark-background image", "composited onto dark navy", variant_of=name)
        rec(f"{stem}gray.png", ImageOps.grayscale(im.convert("RGB")).convert("RGBA"),
            "monochrome image", "grayscale", variant_of=name)
        rec(f"{stem}rot.png", im.rotate(-11, expand=True, resample=Image.BICUBIC),
            "rotated off-axis", "-11 degrees bicubic", variant_of=name)
        conditions += 7

    # --- dedicated edge categories ---
    rec("edge-1x1.png", Image.new("RGBA", (1, 1), (0, 0, 0, 255)), "extreme case", "1x1 pixel")
    rec("edge-flat-color.png", flat((16, 185, 129), 200), "large flat area", "single exact color")
    rec("edge-transparent.png", Image.new("RGBA", (128, 128), (0, 0, 0, 0)), "transparent-background image", "fully empty alpha")
    wide = Image.new("RGBA", (1024, 64), (255, 255, 255, 255))
    ImageDraw.Draw(wide).text((20, 18), "WIDE ASPECT RATIO 16:1", fill=(0, 0, 0, 255))
    rec("edge-aspect-wide.png", wide, "extreme aspect ratio", "16:1 text band")
    thin = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
    dt = ImageDraw.Draw(thin)
    for k in range(11):
        dt.line([(20 + k * 22, 10), (20 + k * 22, 246)], fill=(40, 40, 40, 255), width=1)
    rec("edge-thin-strokes.png", thin, "thin strokes", "1px vertical rules")
    bigbase = base(99, 777_777, 512)
    rec("edge-big1024.png", bigbase, "large image", "1024x1024 upscale", size=(1024, 1024))
    txt = gen_one(0, 5_000_001)
    if txt.mode != "RGBA":
        txt = txt.convert("RGBA")
    rec("edge-text.png", txt.resize((300, 300)), "image with text", "text logo generator output")

    # --- section 5 difficult composite ---
    comp = difficult_composite()
    rec("gauntlet-x1024.png", comp, "difficult composite (section 5)",
        "gradients+nested+thin+thick+translucent overlap+holes+text+scatter, 1024px")

    (ROOT / "test-assets/generated_index.json").write_text(json.dumps(META, indent=1))
    print(f"wrote {len(META)} generated assets ({conditions} condition variants + {len(META)-conditions} bases/edges)")


if __name__ == "__main__":
    main()
