"""Create degraded training variants with increasing hardness over time — STRICT HARD MODE.

Each source image gets up to 15 variants with increasing difficulty (curriculum):
  v01 soft     — downscale 40% and back (easy)
  v02 jpeg     — JPEG q38 (easy)
  v03 rotate   — small rotation ±12° (easy)
  v04 blur1    — Gaussian blur r=1.2 (easy) — start blur
  v05 scale    — random scale 0.6-0.9 + pad (medium)
  v06 jit1     — color jitter strength 1.0 (medium)
  v07 blur2    — Gaussian blur r=2.5 (medium) — increasing hardness
  v08 blur3    — Gaussian blur r=4.0 (hard) — more blur over time
  v09 jit2     — jitter strength 1.5 (hard)
  v10 blur4    — Gaussian blur r=6.0 (very hard) — strict
  v11 jpeghard — JPEG q15 + blur 1.5 (very hard)
  v12 heavy    — blur 2.0 + jitter 2.0 + JPEG q25 (hardest)
  v13 pixel    — pixelate 15% + blur 1.0 (hard, for no-text general)
  v14 blur5    — Gaussian blur r=8.0 (extreme hard) — increase hardness with time
  v15 blur6    — Gaussian blur r=10.0 (extreme hardest) — be strict, max hardness

The blur increases with time/variant index to implement curriculum learning:
time increases → hardness increases → model must be more robust.
General images have NO TEXT (pure geometric, 1000 no-text logos).

Usage: PYTHONPATH=vendor python -m model.degrade --hardness 1-4 (4=strictest, blur up to 10.0)
"""
from __future__ import annotations

import io
import random
from pathlib import Path
import argparse

from PIL import Image, ImageFilter, ImageEnhance

SRC = [Path("model/data/logos"), Path("model/data/logos_notext"), Path("model/data/ai")]
OUT = Path("model/data/degraded")

def variant_soft(img: Image.Image) -> Image.Image:
    w, h = img.size
    small = img.resize((max(8, int(w * 0.4)), max(8, int(h * 0.4))), Image.BICUBIC)
    return small.resize((w, h), Image.BICUBIC)

def variant_jpeg(img: Image.Image, q: int = 38) -> Image.Image:
    rgba = img.convert("RGBA")
    rgb = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    rgb.paste(rgba, (0, 0), rgba)
    rgb = rgb.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=q)
    buf.seek(0)
    out = Image.open(buf).convert("RGBA")
    out.putalpha(rgba.getchannel("A"))
    return out

def variant_rotate(img: Image.Image, ang: float) -> Image.Image:
    return img.rotate(ang, resample=Image.BICUBIC, expand=False)

def variant_blur(img: Image.Image, radius: float) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius=radius))

def variant_scale(img: Image.Image, rng) -> Image.Image:
    w, h = img.size
    scale = rng.uniform(0.6, 0.9)
    nw, nh = int(w*scale), int(h*scale)
    small = img.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0,0,0,0))
    out.paste(small, ((w-nw)//2, (h-nh)//2), small)
    return out

def variant_jitter(img: Image.Image, rng, strength=1.0) -> Image.Image:
    rgba = img.convert("RGBA")
    rgb = rgba.convert("RGB")
    b_factor = rng.uniform(1.0 - 0.15*strength, 1.0 + 0.15*strength)
    c_factor = rng.uniform(1.0 - 0.3*strength, 1.0 + 0.3*strength)
    enhancer = ImageEnhance.Brightness(rgb)
    rgb = enhancer.enhance(b_factor)
    enhancer = ImageEnhance.Color(rgb)
    rgb = enhancer.enhance(c_factor)
    out = Image.new("RGBA", rgba.size)
    out.paste(rgb, (0,0))
    out.putalpha(rgba.getchannel("A"))
    w, h = out.size
    if rng.random() < 0.5 + 0.1*strength:
        sf = max(0.5, 0.85 - 0.05*strength)
        out = out.resize((int(w*sf), int(h*sf)), Image.BILINEAR).resize((w,h), Image.BILINEAR)
    return out

def variant_pixelate(img: Image.Image, factor=0.2) -> Image.Image:
    w, h = img.size
    small = img.resize((max(4, int(w*factor)), max(4, int(h*factor))), Image.NEAREST)
    return small.resize((w, h), Image.NEAREST)

def variant_heavy(img: Image.Image, rng, blur=2.0, jpeg_q=25) -> Image.Image:
    out = variant_blur(img, blur)
    out = variant_jitter(out, rng, strength=2.0)
    out = variant_jpeg(out, q=jpeg_q)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hardness", type=int, default=4, help="1=easy 6 variants, 2=medium 9 variants, 3=hard 13 variants, 4=strictest 15 variants blur up to 10.0")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(99)
    n = 0
    for d in SRC:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.png")):
            img = Image.open(p).convert("RGBA")
            variant_soft(img).save(OUT / f"{p.stem}_v01_soft.png")
            variant_jpeg(img, q=38).save(OUT / f"{p.stem}_v02_jpeg.png")
            variant_rotate(img, rng.uniform(-12, 12)).save(OUT / f"{p.stem}_v03_rot.png")
            variant_blur(img, radius=1.2).save(OUT / f"{p.stem}_v04_blur1.png")
            variant_scale(img, rng).save(OUT / f"{p.stem}_v05_scale.png")
            variant_jitter(img, rng, strength=1.0).save(OUT / f"{p.stem}_v06_jit1.png")
            n += 6
            if args.hardness >= 2:
                variant_blur(img, radius=2.5).save(OUT / f"{p.stem}_v07_blur2.png")
                variant_blur(img, radius=4.0).save(OUT / f"{p.stem}_v08_blur3.png")
                variant_jitter(img, rng, strength=1.5).save(OUT / f"{p.stem}_v09_jit2.png")
                n += 3
            if args.hardness >= 3:
                variant_blur(img, radius=6.0).save(OUT / f"{p.stem}_v10_blur4.png")
                variant_jpeg(variant_blur(img, 1.5), q=15).save(OUT / f"{p.stem}_v11_jpeghard.png")
                variant_heavy(img, rng, blur=2.0, jpeg_q=25).save(OUT / f"{p.stem}_v12_heavy.png")
                variant_pixelate(variant_blur(img, 1.0), factor=0.15).save(OUT / f"{p.stem}_v13_pixel.png")
                n += 4
            if args.hardness >= 4:
                variant_blur(img, radius=8.0).save(OUT / f"{p.stem}_v14_blur5.png")
                variant_blur(img, radius=10.0).save(OUT / f"{p.stem}_v15_blur6.png")
                n += 2
    print(f"wrote {n} degraded variants (hardness={args.hardness}) -> {OUT} — blur increasing 1.2→2.5→4.0→6.0→8.0→10.0 with time, strict, no-text general")

if __name__ == "__main__":
    main()
