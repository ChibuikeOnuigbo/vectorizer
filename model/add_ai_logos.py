"""Turn the AI-generated white-background logos into clean transparent PNGs.

Near-white pixels (min channel >= 235) become fully transparent with a soft
200..235 edge ramp; everything else stays. Max edge is capped at 384px for
fast training. Output: model/data/ai/ai_logo_XX.png

Usage: PYTHONPATH=vendor python -m model.add_ai_logos
"""
from __future__ import annotations

import numpy as np
from pathlib import Path
from PIL import Image

SRC = Path("model/data")
OUT = Path("model/data/ai")


def clean(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    if max(w, h) > 384:
        f = 384 / max(w, h)
        img = img.resize((max(1, int(w * f)), max(1, int(h * f))), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float32)
    mn = arr[..., :3].min(axis=2)
    a = np.clip((235.0 - mn) / 35.0, 0.0, 1.0) * 255.0
    arr[..., 3] = a
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(SRC.glob("ai_logo_*.png")):
        if p.parent == OUT:
            continue
        clean(Image.open(p)).save(OUT / p.name)
        n += 1
    print(f"cleaned {n} AI logos -> {OUT}")


if __name__ == "__main__":
    main()
