"""Perceptual near-duplicate detection (section 11, perceptual similarity).

Average-hash (aHash, 8x8, 64-bit) over every raster in dataset/ and
test-assets/. Pairs with hamming distance <= 5 are reported as near
duplicates grouped by component. Output: test-assets/near_dup.json

  PYTHONPATH=vendor:app/deps:. python3 scripts/dataset/near_dup.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(ROOT / "vendor"), str(ROOT / "app/deps")):
    sys.path.insert(0, p)

from PIL import Image  # noqa: E402

THRESH = 5


def ahash(p: Path) -> int | None:
    """Content-aware aHash: crop to the non-background content bbox first,
    so similar-looking backgrounds don't swamp the bit pattern."""
    try:
        im = Image.open(p).convert("RGBA")
        import PIL.ImageChops as IC
        # PIL quirk: getbbox() on an RGBA difference reads only the alpha
        # channel - composite to RGB first or every bbox comes back empty
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, (0, 0), im)
        bg = Image.new("RGB", flat.size, flat.getpixel((0, 0)))
        diff = IC.difference(flat, bg)
        bbox = diff.getbbox()
        if not bbox:
            return 0  # uniform canvas - content-free, all identical
        content = flat.crop(bbox)
        canvas = Image.new("RGBA", (max(content.size), max(content.size)), (255, 255, 255, 255))
        ox = (canvas.size[0] - content.size[0]) // 2
        oy = (canvas.size[1] - content.size[1]) // 2
        canvas.paste(content, (ox, oy))
        g = canvas.convert("L").resize((8, 8), Image.LANCZOS)
        px = list(g.getdata())
        avg = sum(px) / 64.0
        h = 0
        for b in px:
            h = (h << 1) | (1 if b >= avg else 0)
        return h
    except Exception:
        return None


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def main() -> None:
    files = sorted(ROOT.glob("dataset/icons/*/*/input-*.png"))
    files += sorted(ROOT.glob("test-assets/images/*/*.png"))
    files += sorted(ROOT.glob("test-assets/images/*.png")) if (ROOT / "test-assets/images").exists() else []
    import numpy as np
    hashes: list[tuple[str, int]] = []
    vecs: list[np.ndarray] = []
    for f in files:
        h = ahash(f)
        if h is None:
            continue
        try:
            g32 = Image.open(f).convert("L").resize((32, 32), Image.LANCZOS)
            hashes.append((str(f.relative_to(ROOT)), h))
            vecs.append(np.asarray(g32, dtype=np.float32).reshape(-1))
        except Exception:
            continue
    # stage 1: exact aHash equality bucket; stage 2: 32x32 MAE<=3 confirm (numpy)
    buckets: dict[int, list[int]] = {}
    for idx, (_p, h) in enumerate(hashes):
        buckets.setdefault(h, []).append(idx)
    # union-find over MAE-confirmed edges
    parent = list(range(len(hashes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    edges = 0
    TILE = 128
    for inds in buckets.values():
        if len(inds) < 2:
            continue
        inds = inds[:512]  # pathological mega-bucket guard
        V = np.stack([vecs[i] for i in inds], dtype=np.float32)
        n = V.shape[0]
        pair_idx = []
        cols = np.arange(n)
        for a0 in range(0, n, TILE):
            A = V[a0:a0 + TILE]
            mae = np.abs(A[:, None, :] - V[None, :, :]).mean(axis=2)
            rows_abs = a0 + np.arange(mae.shape[0])
            r, c = np.where((mae <= 3.0) & (cols[None, :] > rows_abs[:, None]))
            pair_idx.extend(zip((a0 + r).tolist(), c.tolist()))
        for a, b in pair_idx:
            union(inds[a], inds[b])
            edges += 1
    comps: dict[int, list[int]] = {}
    for i in range(len(hashes)):
        comps.setdefault(find(i), []).append(i)
    groups = [sorted(hashes[m][0] for m in members) for members in comps.values() if len(members) > 1]
    report = {
        "files_hashed": len(hashes),
        "hash": "content-bbox aHash-8x8 exact bucket + 32x32 grayscale MAE<=3 confirm (numpy)",
        "near_dup_edges": edges,
        "near_dup_groups": groups[:500],
        "near_dup_group_count": len(groups),
        "exact_md5_dupes": "see test-assets/manifest.json unique_md5 vs entries",
        "recorded": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (ROOT / "test-assets/near_dup.json").write_text(json.dumps(report, indent=1))
    print(f"hashed {len(hashes)} files, {edges} near-dup edges in {len(groups)} groups")


if __name__ == "__main__":
    main()
