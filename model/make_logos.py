"""Deterministic synthetic logo generator — improved: supports no-text mode.

Makes 600+ flat, transparent-background logos (256x256 PNG):
- With text: monogram letters (7-segment style), geometric marks, etc.
- No-text: pure geometric marks (star, bolt, ring, wave, mountain, heart, shield, leaf, cloud, infinity, etc.) — no letters at all, as requested for general images.

Usage: python -m model.make_logos [--count 600] [--seed 42] [--out model/data/logos] [--no-text]
"""
from __future__ import annotations

import argparse
import os
import random
import math

from PIL import Image, ImageDraw

SIZE = 256

SEG = {
    "A": "abcdef", "B": "bcdef", "C": "abde", "D": "bcdef", "E": "abced",
    "F": "abce", "H": "abdeg", "L": "de", "O": "abcdef", "P": "abcfg",
    "U": "bcdef", "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd",
    "4": "fgbc", "5": "afgcd", "6": "afgcde", "7": "abc", "8": "abcdefg",
    "9": "abcfgd", "K": "abef", "M": "abcef", "N": "abcef", "R": "abcfg",
    "S": "afgcd", "T": "ab", "V": "bcef", "W": "bcef", "X": "bcef",
    "Y": "bfgc", "Z": "abged",
}

def draw_monogram(img, ch, color, cx, cy, w, h):
    d = ImageDraw.Draw(img)
    thick = w * 0.24
    boxes = {
        "a": (cx - w / 2, cy - h / 2, cx + w / 2, cy - h / 2 + thick),
        "g": (cx - w / 2, cy - thick / 2, cx + w / 2, cy + thick / 2),
        "d": (cx - w / 2, cy + h / 2 - thick, cx + w / 2, cy + h / 2),
        "f": (cx - w / 2, cy - h / 2 + thick / 2, cx - w / 2 + thick, cy),
        "e": (cx - w / 2, cy, cx - w / 2 + thick, cy + h / 2 - thick / 2),
        "b": (cx + w / 2 - thick, cy, cx + w / 2, cy + h / 2 - thick / 2),
        "c": (cx + w / 2 - thick, cy, cx + w / 2, cy + h / 2 - thick / 2),
    }
    for s in SEG.get(ch, "abcdef"):
        if s in boxes:
            d.rounded_rectangle(boxes[s], radius=thick * 0.45, fill=color)

def draw_mark(img, kind, color, cx, cy, s, color2=None):
    d = ImageDraw.Draw(img)
    if kind == "star":
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = s / 2 if i % 2 == 0 else s / 4.6
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        d.polygon(pts, fill=color)
    elif kind == "ring":
        t = int(max(4, s * 0.16))
        d.ellipse([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2],
                  outline=color, width=t)
    elif kind == "disc":
        d.ellipse([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2], fill=color)
    elif kind == "diamond":
        d.polygon([(cx, cy - s / 2), (cx + s / 2, cy), (cx, cy + s / 2),
                   (cx - s / 2, cy)], fill=color)
    elif kind == "bolt":
        pts = [(cx + s * 0.12, cy - s / 2), (cx - s * 0.28, cy + s * 0.08),
               (cx - s * 0.02, cy + s * 0.08), (cx - s * 0.14, cy + s / 2),
               (cx + s * 0.3, cy - s * 0.1), (cx + s * 0.04, cy - s * 0.1)]
        d.polygon(pts, fill=color)
    elif kind == "triangle":
        d.polygon([(cx, cy - s / 2), (cx + s / 2, cy + s / 2),
                   (cx - s / 2, cy + s / 2)], fill=color)
    elif kind == "cross":
        t = s * 0.24
        d.rounded_rectangle([cx - t / 2, cy - s / 2, cx + t / 2, cy + s / 2],
                            radius=t * 0.4, fill=color)
        d.rounded_rectangle([cx - s / 2, cy - t / 2, cx + s / 2, cy + t / 2],
                            radius=t * 0.4, fill=color)
    elif kind == "heart":
        r = s * 0.27
        d.ellipse([cx - s / 2, cy - s * 0.42, cx - s / 2 + 2 * r, cy - s * 0.42 + 2 * r], fill=color)
        d.ellipse([cx + s / 2 - 2 * r, cy - s * 0.42, cx + s / 2, cy - s * 0.42 + 2 * r], fill=color)
        d.polygon([(cx - s / 2 + r * 0.15, cy - s * 0.12),
                   (cx + s / 2 - r * 0.15, cy - s * 0.12),
                   (cx, cy + s / 2)], fill=color)
    elif kind == "arrow":
        t = s * 0.2
        d.rounded_rectangle([cx - t / 2, cy - s / 2, cx + t / 2, cy + s * 0.25],
                            radius=t * 0.4, fill=color)
        d.polygon([(cx - s * 0.34, cy + s * 0.05), (cx + s * 0.34, cy + s * 0.05),
                   (cx, cy + s / 2)], fill=color)
    elif kind == "crescent":
        r = s / 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        off = r * 0.55
        d.ellipse([cx - r + off, cy - r - r * 0.12, cx + r + off, cy + r - r * 0.12],
                  fill=(0, 0, 0, 0))
    elif kind == "wave":
        t = int(max(4, s * 0.17))
        d.arc([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2], 200, 340,
              fill=color, width=t)
        d.arc([cx - s / 2, cy - s * 0.15, cx + s / 2, cy + s * 0.85], 200, 340,
              fill=color, width=t)
    elif kind == "bars":
        bw, t = s * 0.7, s * 0.16
        for k, yy in enumerate((cy - s * 0.32, cy - t / 2, cy + s * 0.32)):
            d.rounded_rectangle([cx - bw / 2 + k * s * 0.08, yy - t / 2,
                                 cx + bw / 2 - (2 - k) * s * 0.08, yy + t / 2],
                                radius=t / 2, fill=color)
    elif kind == "chevron":
        t = s * 0.2
        for k in range(3):
            yy = cy - s * 0.34 + k * s * 0.34
            d.polygon([(cx - s * 0.34, yy), (cx, yy + s * 0.2),
                       (cx + s * 0.34, yy), (cx + s * 0.34, yy + t * 0.7),
                       (cx, yy + s * 0.2 + t * 0.7), (cx - s * 0.34, yy + t * 0.7)],
                      fill=color)
    elif kind == "mountain":
        d.polygon([(cx - s * 0.48, cy + s / 2), (cx - s * 0.05, cy - s * 0.42),
                   (cx + s * 0.3, cy + s / 2)], fill=color)
        d.polygon([(cx - s * 0.05, cy + s / 2), (cx + s * 0.18, cy - s * 0.1),
                   (cx + s * 0.48, cy + s / 2)],
                  fill=color2 or color)
    elif kind == "drop":
        r = s * 0.26
        d.ellipse([cx - r, cy - r * 0.4, cx + r, cy + r * 1.6], fill=color)
        d.polygon([(cx, cy - s / 2), (cx - r * 0.95, cy + r * 0.55),
                   (cx + r * 0.95, cy + r * 0.55)], fill=color)
    elif kind == "sun":
        r = s * 0.26
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        for i in range(8):
            ang = i * math.pi / 4
            x0, y0 = cx + (r + s * 0.08) * math.cos(ang), cy + (r + s * 0.08) * math.sin(ang)
            x1, y1 = cx + (r + s * 0.2) * math.cos(ang), cy + (r + s * 0.2) * math.sin(ang)
            d.line([x0, y0, x1, y1], fill=color, width=int(max(3, s * 0.07)))
    elif kind == "hex":
        pts = [(cx + s / 2 * math.cos(a), cy + s / 2 * math.sin(a))
               for a in (math.pi / 2 + i * math.pi / 3 for i in range(6))]
        d.polygon(pts, outline=color, width=int(max(4, s * 0.15)))
    elif kind == "square":
        d.rounded_rectangle([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2],
                            radius=s * 0.18, fill=color)
    elif kind == "circle_dot":
        d.ellipse([cx - s/2, cy - s/2, cx + s/2, cy + s/2], fill=color)
        d.ellipse([cx - s*0.15, cy - s*0.15, cx + s*0.15, cy + s*0.15], fill=color2 or (255,255,255,255))
    elif kind == "shield":
        d.polygon([(cx - s*0.4, cy - s*0.4), (cx + s*0.4, cy - s*0.4),
                   (cx + s*0.4, cy + s*0.1), (cx, cy + s*0.5),
                   (cx - s*0.4, cy + s*0.1)], fill=color)
    elif kind == "leaf":
        d.ellipse([cx - s*0.35, cy - s*0.45, cx + s*0.35, cy + s*0.25], fill=color)
        d.polygon([(cx, cy - s*0.45), (cx - s*0.1, cy + s*0.45), (cx + s*0.1, cy + s*0.45)], fill=color2 or color)
    elif kind == "cloud":
        r = s * 0.18
        for dx, dy, rr in [(0,0,r*1.5), (-r*1.2, r*0.3, r), (r*1.2, r*0.3, r), (0, -r*0.6, r*1.2)]:
            d.ellipse([cx + dx - rr, cy + dy - rr, cx + dx + rr, cy + dy + rr], fill=color)
    elif kind == "infinity":
        t = int(max(4, s*0.12))
        d.ellipse([cx - s*0.25, cy - s*0.18, cx, cy + s*0.18], outline=color, width=t)
        d.ellipse([cx, cy - s*0.18, cx + s*0.25, cy + s*0.18], outline=color, width=t)
    else:
        d.rounded_rectangle([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2],
                            radius=s * 0.18, fill=color)


MARKS = ["star", "ring", "disc", "diamond", "bolt", "triangle", "cross",
         "heart", "arrow", "crescent", "wave", "bars", "chevron", "mountain",
         "drop", "sun", "hex", "square", "circle_dot", "shield", "leaf",
         "cloud", "infinity"]
# Only geometric, no text
MARKS_NOTEXT = ["star", "ring", "disc", "diamond", "bolt", "triangle", "cross",
                "heart", "arrow", "crescent", "wave", "chevron", "mountain",
                "drop", "sun", "hex", "square", "circle_dot", "shield", "leaf",
                "cloud", "infinity"]

LETTERS = list(SEG.keys())

def make_logo(rng, idx, no_text=False) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hue = rng.uniform(0, 360)
    sat = rng.uniform(0.55, 0.95)
    val = rng.uniform(0.45, 0.95)
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(hue / 360, sat, val)
    color = (int(r * 255), int(g * 255), int(b * 255), 255)
    hue2 = (hue + rng.choice([0, 120, 150, 180, 200, 240, 300])) % 360
    sat2 = rng.uniform(0.5, 0.95)
    val2 = rng.uniform(0.35, 0.9)
    r2, g2, b2 = colorsys.hsv_to_rgb(hue2 / 360, sat2, val2)
    color2 = (int(r2 * 255), int(g2 * 255), int(b2 * 255), 255)
    hue3 = (hue + 60) % 360
    r3, g3, b3 = colorsys.hsv_to_rgb(hue3 / 360, sat, max(0.25, val - 0.15))
    color3 = (int(r3 * 255), int(g3 * 255), int(b3 * 255), 255)

    if no_text:
        # Pure geometric, no letters, no bars that look like text
        style = idx % 6  # only geometric styles
        s = rng.uniform(110, 180)
        cx, cy = SIZE / 2 + rng.uniform(-12, 12), SIZE / 2 + rng.uniform(-14, 10)
        marks_pool = MARKS_NOTEXT
        if style == 0:
            draw_mark(img, rng.choice(marks_pool), color, cx, cy, s, color2)
        elif style == 1:
            draw_mark(img, "ring", color, cx, cy - 6, s * 1.35)
            draw_mark(img, rng.choice(marks_pool), color2, cx, cy - 6, s * 0.62)
        elif style == 2:
            # triple mark composition — pure geometry
            for k, (cc, ss, dx, dy) in enumerate([
                (color, s*0.6, -s*0.3, -s*0.1),
                (color2, s*0.5, s*0.25, -s*0.15),
                (color3, s*0.4, 0, s*0.35)
            ]):
                draw_mark(img, rng.choice(marks_pool), cc, cx+dx, cy+dy, ss, color)
        elif style == 3:
            d = ImageDraw.Draw(img)
            d.ellipse([cx - s*0.7, cy - s*0.7, cx + s*0.7, cy + s*0.7], fill=color, outline=color2, width=4)
            draw_mark(img, rng.choice(marks_pool), color2, cx, cy, s*0.6, color)
        elif style == 4:
            # two overlapping shapes
            draw_mark(img, rng.choice(marks_pool), color, cx - s*0.2, cy, s*0.7, color2)
            draw_mark(img, rng.choice(marks_pool), color2, cx + s*0.2, cy, s*0.6, color)
        else:
            # single large mark
            draw_mark(img, rng.choice(marks_pool), color, cx, cy, s*1.1, color2)
        return img

    # Original with text allowed
    style = idx % 10
    s = rng.uniform(110, 180)
    cx, cy = SIZE / 2 + rng.uniform(-12, 12), SIZE / 2 + rng.uniform(-14, 10)

    if style == 0:
        ch = rng.choice(LETTERS)
        draw_monogram(img, ch, color, cx, cy, s * 0.9, s * 1.15)
    elif style == 1:
        draw_mark(img, rng.choice(MARKS), color, cx, cy, s, color2)
    elif style == 2:
        draw_mark(img, "ring", color, cx, cy - 6, s * 1.35)
        draw_mark(img, rng.choice(["disc", "diamond", "triangle", "bolt", "star", "shield", "leaf"]),
                  color2, cx, cy - 6, s * 0.62)
    elif style == 3:
        draw_mark(img, rng.choice(MARKS), color, cx, cy - 26, s * 0.95)
        d = ImageDraw.Draw(img)
        t = 12
        d.rounded_rectangle([cx - s * 0.42, cy + 52, cx + s * 0.42, cy + 52 + t],
                            radius=t / 2, fill=color)
        d.rounded_rectangle([cx - s * 0.26, cy + 74, cx + s * 0.26, cy + 74 + t],
                            radius=t / 2, fill=color2)
    elif style == 4:
        ch = rng.choice(LETTERS)
        draw_monogram(img, ch, color, cx, cy - 18, s * 0.85, s * 1.05)
        d = ImageDraw.Draw(img)
        t = 14
        d.rounded_rectangle([cx - s * 0.4, cy + 56, cx + s * 0.4, cy + 56 + t],
                            radius=t / 2, fill=color2)
    elif style == 5:
        ch1, ch2 = rng.choice(LETTERS), rng.choice(LETTERS)
        draw_monogram(img, ch1, color, cx - s * 0.42, cy, s * 0.72, s * 0.95)
        draw_monogram(img, ch2, color2, cx + s * 0.42, cy, s * 0.72, s * 0.95)
    elif style == 6:
        for k, (cc, ss, dx, dy) in enumerate([
            (color, s*0.6, -s*0.3, -s*0.1),
            (color2, s*0.5, s*0.25, -s*0.15),
            (color3, s*0.4, 0, s*0.35)
        ]):
            draw_mark(img, rng.choice(MARKS), cc, cx+dx, cy+dy, ss, color)
    elif style == 7:
        d = ImageDraw.Draw(img)
        d.ellipse([cx - s*0.7, cy - s*0.7, cx + s*0.7, cy + s*0.7], fill=color, outline=color2, width=4)
        draw_mark(img, rng.choice(MARKS), color2, cx, cy, s*0.6, color)
    elif style == 8:
        d = ImageDraw.Draw(img)
        for k in range(3):
            yy = cy - s*0.35 + k * s*0.35
            d.rounded_rectangle([cx - s*0.4, yy - s*0.08, cx + s*0.4, yy + s*0.08],
                                radius=s*0.08, fill=[color, color2, color3][k])
        draw_mark(img, rng.choice(MARKS), (255,255,255,255), cx, cy - s*0.35, s*0.3)
    else:
        draw_mark(img, rng.choice(["disc", "square", "diamond", "shield", "hex"]), color, cx, cy, s*1.2, color2)
        ch = rng.choice(LETTERS)
        draw_monogram(img, ch, (255,255,255,255), cx, cy, s*0.55, s*0.75)
    return img

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="model/data/logos")
    ap.add_argument("--no-text", action="store_true", help="Generate pure geometric logos with no text/letters")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)
    for i in range(args.count):
        make_logo(rng, i, no_text=args.no_text).save(f"{args.out}/logo_e{args.seed}_{i:04d}.png")
    print(f"wrote {args.count} logos (no_text={args.no_text}) to {args.out}")

if __name__ == "__main__":
    main()
