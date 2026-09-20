"""Generate images with text and no background — transparent PNGs for training"""
import random
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path("model/data/logos_text")
OUT.mkdir(parents=True, exist_ok=True)

WORDS = ["LOGO", "ICON", "SVG", "ART", "DESIGN", "VECTOR", "BRAND", "MARK", "GEO", "STAR", "BOLT", "WAVE", "CLOUD", "HEART", "SHIELD", "LEAF", "SUN", "MOON", "DROP", "MOUNT", "A", "B", "C", "X", "Y", "Z", "AB", "CD", "XY", "123", "GO", "UP", "OK", "HI", "NO", "YES", "ONE", "TWO"]

def gen_one(idx, seed):
    rng = random.Random(seed + idx)
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # random background shapes no text
    # pick colors
    import colorsys
    hue = rng.uniform(0, 360)
    sat = rng.uniform(0.6, 0.95)
    val = rng.uniform(0.5, 0.9)
    r, g, b = colorsys.hsv_to_rgb(hue/360, sat, val)
    color = (int(r*255), int(g*255), int(b*255), 255)
    # draw text
    text = rng.choice(WORDS)
    # try to use default font, size random
    size = rng.randint(40, 110)
    try:
        # use a basic font
        font = ImageFont.load_default()
        # scale via image resize trick
        # create small image with text then resize
        txt_img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt_img)
        # estimate position
        # use textbbox if available
        try:
            bbox = td.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except:
            tw, th = len(text)*20, 30
        x = (256 - tw)//2 + rng.randint(-20, 20)
        y = (256 - th)//2 + rng.randint(-20, 20)
        td.text((x, y), text, fill=color, font=font)
        # upscale
        if size > 30:
            factor = size / 30
            txt_img = txt_img.resize((int(256*factor), int(256*factor)), Image.LANCZOS)
            # center crop back to 256
            left = (txt_img.width - 256)//2
            top = (txt_img.height - 256)//2
            txt_img = txt_img.crop((left, top, left+256, top+256))
        img = Image.alpha_composite(img, txt_img)
    except Exception as e:
        # fallback simple
        d.text((60, 100), text, fill=color)
    # add some geometric accent with no bg
    if rng.random() < 0.5:
        # add a small shape
        cx, cy = rng.randint(40, 216), rng.randint(40, 216)
        s = rng.randint(20, 60)
        hue2 = (hue + 180) % 360
        r2, g2, b2 = colorsys.hsv_to_rgb(hue2/360, sat, val)
        color2 = (int(r2*255), int(g2*255), int(b2*255), 180)
        d.ellipse([cx-s//2, cy-s//2, cx+s//2, cy+s//2], fill=color2)
    return img

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=500)
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--out", default="model/data/logos_text")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(args.count):
        img = gen_one(i, args.seed)
        img.save(out / f"text_{args.seed}_{i:04d}.png")
    print(f"wrote {args.count} text no bg to {out}")

if __name__ == "__main__":
    main()
