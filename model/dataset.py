"""Dataset builder: for every training image, run the full pipeline with a
pool of candidate parameter sets, score each with the composite reward
(model.svg_geom.score), and rank them. The top-ranked set becomes the
supervision target for the parameter-prediction model.

Usage:
  PYTHONPATH=vendor:. python -m model.dataset [--images model/data/logos] \
      [--extra model/data/ai] [--out model/data] [--n-cand 24]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.convert import analyze, trace_with, BASELINE_FLAT, BASELINE_PHOTO
from model.features import image_features
from model.svg_geom import score


def systematic_candidates(is_flat: bool) -> list:
    """Hand-picked grid that covers the useful parameter space, now includes corner_threshold, length_threshold, path_precision from Cloudinary analysis."""
    out = []
    if is_flat:
        for cp in [2, 3, 4, 5]:
            for ld in [16, 22, 28]:
                for sp in [1, 2, 4]:
                    for mi in [10, 14, 20]:
                        for ct in [50, 60, 70]:
                            out.append(dict(profile="flat", color_precision=cp,
                                            layer_difference=ld, filter_speckle=sp,
                                            max_iterations=mi, corner_threshold=ct,
                                            length_threshold=4.0, path_precision=8))
        # some photo-mode probes for flat images (sometimes better)
        for cp in [5, 6]:
            for ld in [12, 18]:
                out.append(dict(profile="photo", color_precision=cp,
                                layer_difference=ld, filter_speckle=2,
                                max_iterations=24, corner_threshold=50,
                                length_threshold=3.5, path_precision=8))
    else:
        for cp in [4, 6, 7]:
            for ld in [10, 14, 20]:
                for sp in [2, 4, 8]:
                    for mi in [24, 32, 40]:
                        for ct in [30, 50, 70]:
                            out.append(dict(profile="photo", color_precision=cp,
                                            layer_difference=ld, filter_speckle=sp,
                                            max_iterations=mi, corner_threshold=ct,
                                            length_threshold=3.5, path_precision=8))
        for cp in [3, 4]:
            for ld in [20, 26]:
                out.append(dict(profile="flat", color_precision=cp,
                                layer_difference=ld, filter_speckle=2,
                                max_iterations=16, corner_threshold=60,
                                length_threshold=4.0, path_precision=8))
    return out

def random_candidates(rng: np.random.Generator, is_flat: bool, n: int = 24) -> list:
    out = []
    for _ in range(n):
        p_flat = rng.random() < (0.82 if is_flat else 0.25)
        profile = "flat" if p_flat else "photo"
        if profile == "flat":
            out.append(dict(
                profile=profile,
                color_precision=int(rng.integers(1, 6)),
                layer_difference=int(rng.integers(10, 34)),
                filter_speckle=int(rng.choice([1, 2, 4])),
                max_iterations=int(rng.integers(8, 26)),
                corner_threshold=int(rng.integers(40, 80)),
                length_threshold=float(rng.uniform(3.0, 5.0)),
                path_precision=int(rng.integers(6, 10)),
            ))
        else:
            out.append(dict(
                profile=profile,
                color_precision=int(rng.integers(3, 9)),
                layer_difference=int(rng.integers(8, 32)),
                filter_speckle=int(rng.choice([1, 2, 4, 8])),
                max_iterations=int(rng.integers(16, 49)),
                corner_threshold=int(rng.integers(20, 80)),
                length_threshold=float(rng.uniform(2.5, 5.0)),
                path_precision=int(rng.integers(6, 10)),
            ))
    return out


def build_dataset(image_paths: list, out_dir: str, n_cand: int = 24,
                  seed: int = 7, save_best_svm: bool = True) -> list:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    svgs_dir = out / "svgs"
    svgs_dir.mkdir(exist_ok=True)
    rng = np.random.default_rng(seed)
    records = []
    t0 = time.time()
    for i, p in enumerate(image_paths):
        p = Path(p)
        orig = Image.open(p).convert("RGBA")
        a = analyze(orig)
        feats = image_features(orig)
        baseline = dict(BASELINE_FLAT if a["is_flat"] else BASELINE_PHOTO)
        # combine baseline + systematic grid (sampled) + random
        sys_cands = systematic_candidates(a["is_flat"])
        # sample 20 from systematic to keep runtime reasonable but more coverage, plus random
        if len(sys_cands) > 20:
            idx = rng.choice(len(sys_cands), 20, replace=False)
            sys_cands = [sys_cands[k] for k in idx]
        cands = [baseline] + sys_cands + random_candidates(rng, a["is_flat"], n_cand)
        # dedup including new params
        seen = set()
        uniq = []
        for c in cands:
            key = (c["profile"], c["color_precision"], c["layer_difference"], c["filter_speckle"], c["max_iterations"],
                   c.get("corner_threshold", 60), round(c.get("length_threshold", 4.0),1), c.get("path_precision", 8))
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        cands = uniq
        results = []
        for c in cands:
            svg = trace_with(a, c)
            s = score(orig, svg)
            results.append({**c, **s, "svg_len": len(svg)})
        best_idx = max(range(len(results)),
                       key=lambda k: (results[k]["score"],
                                      -results[k]["paths"],
                                      -results[k]["svg_len"]))
        if save_best_svm:
            (svgs_dir / p.stem).with_suffix(".svg").write_text(
                trace_with(a, results[best_idx]))
        records.append({
            "name": p.name,
            "path": str(p),
            "features": feats.tolist(),
            "candidates": results,
            "best": best_idx,
        })
        if (i + 1) % 20 == 0 or (i+1) == len(image_paths):
            dt = time.time() - t0
            avg_score = sum(r["candidates"][r["best"]]["score"] for r in records[-20:]) / min(20, len(records))
            print(f"  [{i + 1}/{len(image_paths)}] {dt / (i + 1):.2f}s/img "
                  f"last best={results[best_idx]['score']:.1f} avg20={avg_score:.1f}", flush=True)
    (out / "dataset.json").write_text(json.dumps(records))
    print(f"dataset: {len(records)} images, {sum(len(r['candidates']) for r in records)} "
          f"candidates -> {out / 'dataset.json'}  ({time.time() - t0:.0f}s)")
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", action="append", default=[])
    ap.add_argument("--out", default="model/data")
    ap.add_argument("--n-cand", type=int, default=24)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    paths = []
    for d in args.images:
        dd = Path(d)
        if dd.is_dir():
            paths.extend(sorted(dd.glob("*.png")) + sorted(dd.glob("*.jpg")) + sorted(dd.glob("*.jpeg")))
        else:
            paths.append(dd)
    if not paths:
        print("no images found", file=sys.stderr)
        sys.exit(1)
    # dedup paths
    uniq = []
    seen = set()
    for p in paths:
        sp = str(p)
        if sp not in seen:
            seen.add(sp)
            uniq.append(p)
    build_dataset(uniq, args.out, n_cand=args.n_cand, seed=args.seed)


if __name__ == "__main__":
    main()
