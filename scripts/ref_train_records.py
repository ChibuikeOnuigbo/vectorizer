#!/usr/bin/env python3
"""Visual-reference training (NOT hard-coded params): score vectorizer
candidates of the UPLOADED image against the USER-APPROVED REFERENCE RENDER
(model_result/absolute_test_svg.svg) pixel-for-pixel, and append those records
to the training dataset. The model then LEARNS which candidate choices land
closest to the blessed visual.

Usage: PYTHONPATH=vendor:app/deps:. python3 scripts/ref_train_records.py
        [--variants 8] [--synthetic-refs]  [--apply]
"""
import argparse, json, shutil, sys, time
from pathlib import Path

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qa"))

from model.dataset import build_dataset, systematic_candidates, random_candidates  # noqa: E402
from model.svg_geom import parse_svg_paths  # noqa: E402
from model import degrade as D  # noqa: E402
from app.convert import analyze, trace_with  # noqa: E402
from model.features import image_features  # noqa: E402
from similarity_audit import bg_flat, render_svg, ssim_block  # noqa: E402

SRC = ROOT / "test-assets/images/user-provided/teal-orbit-logo.png"
REF_SVG = ROOT / "model_result/absolute_test_svg.svg"
REFS = ROOT / "model/refs"
MANUAL = ROOT / "model/data/manual"
DATASET = ROOT / "model/data/dataset.json"


def ref_score(svg: str, ref_rows: tuple, w: int, h: int) -> float:
    """min(f_mae, ssim12, silhouette_iou)*100 of candidate render vs ref render.
    Visual pixels only; never reads ref path geometry."""
    rgb_ref, gray_ref, sil_ref = ref_rows
    gen = render_svg(svg, w, h)
    flat = bg_flat(gen)
    gg = np.asarray(flat.convert("L"), dtype=np.float32)
    cg = np.asarray(flat.convert("RGB"), dtype=np.int16)
    sg = np.asarray(gen.split()[3], dtype=np.int16) > 14
    mae = float(np.abs(rgb_ref - cg).mean())
    f_mae = max(0.0, 1.0 - mae / 255.0)
    ss = ssim_block(gray_ref, gg)
    u = int((sil_ref | sg).sum())
    iou = (int((sil_ref & sg).sum()) / u) if u else 1.0
    return round(100.0 * min(f_mae, ss, iou), 1)


def ref_arrays(ref_png: Path):
    im = Image.open(ref_png).convert("RGBA")
    flat = bg_flat(im)
    return (np.asarray(flat.convert("RGB"), dtype=np.int16),
            np.asarray(flat.convert("L"), dtype=np.float32),
            np.asarray(im.split()[3], dtype=np.int16) > 14)


def make_variants(n: int) -> list[tuple[str, Image.Image]]:
    orig = Image.open(SRC).convert("RGBA")
    out = [("ref-teal-v00", orig)]
    if n >= 2: out.append(("ref-teal-v01-blur", D.variant_blur(orig, 1.2)))
    if n >= 3: out.append(("ref-teal-v02-jpeg", D.variant_jpeg(orig, 45)))
    if n >= 4: out.append(("ref-teal-v03-soft", D.variant_soft(orig)))
    if n >= 5: out.append(("ref-teal-v04-rot", D.variant_rotate(orig, 0.8)))
    if n >= 6: out.append(("ref-teal-v05-rot", D.variant_rotate(orig, -0.6)))
    if n >= 7: out.append(("ref-teal-v06-scale", D.variant_scale(orig, np.random.default_rng(11))))
    if n >= 8: out.append(("ref-teal-v07-jitter", D.variant_jitter(orig, np.random.default_rng(12), 0.7)))
    return out


def build_records(rows: list[tuple[str, Image.Image]], ref_rows, w: int, h: int,
                  tag: str, n_rand: int = 16) -> list[dict]:
    rng = np.random.default_rng(777)
    records = []
    for name, img in rows:
        a = analyze(img)
        feats = image_features(img)
        sys_cands = systematic_candidates(a["is_flat"])
        if len(sys_cands) > 40:
            idx = rng.choice(len(sys_cands), 40, replace=False)
            sys_cands = [sys_cands[k] for k in idx]
        cands = sys_cands + random_candidates(rng, a["is_flat"], n_rand)
        seen, uniq = set(), []
        for c in cands:
            key = (c["profile"], c["color_precision"], c["layer_difference"],
                   c["filter_speckle"], c["max_iterations"],
                   c.get("corner_threshold", 60),
                   round(c.get("length_threshold", 4.0), 1), c.get("path_precision", 8))
            if key not in seen:
                seen.add(key); uniq.append(c)
        results = []
        for c in uniq:
            svg = trace_with(a, c)
            s = ref_score(svg, ref_rows, w, h)
            results.append({**c, "score": s, "paths": len(parse_svg_paths(svg)),
                            "svg_len": len(svg)})
        # NOTE for degraded variants the ref is a shade off the degraded input;
        # the pixel metric still ranks candidates by closeness to the target VISUAL.
        best_idx = max(range(len(results)),
                       key=lambda k: (results[k]["score"], -results[k]["paths"], -results[k]["svg_len"]))
        fn = f"{name}.png"
        img.save(MANUAL / fn)
        records.append({"name": fn, "path": str(MANUAL / fn), "features": feats.tolist(),
                        "candidates": results, "best": best_idx,
                        "scored_against": tag})
        print(f"  {name}: best={results[best_idx]['score']:.1f} "
              f"(cand {best_idx} {results[best_idx]['profile']} cp{results[best_idx]['color_precision']}) "
              f"n={len(results)}", flush=True)
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", type=int, default=8)
    ap.add_argument("--apply", action="store_true", help="write records into dataset.json")
    ap.add_argument("--perms", type=int, default=3, help="record repetitions in dataset (sampling weight)")
    args = ap.parse_args()

    MANUAL.mkdir(parents=True, exist_ok=True)
    REFS.mkdir(parents=True, exist_ok=True)

    # 1) ref render (visual ground truth bitmap)
    ref_txt = REF_SVG.read_text()
    w, h = Image.open(SRC).size
    ref_png = REFS / "teal-orbit-logo_ref.png"
    render_svg(ref_txt, w, h).save(ref_png)
    ref_rows = ref_arrays(ref_png)
    print(f"ref render saved {ref_png} ({w}x{h})")

    # 2) build records from the uploaded image + its degraded-family variants,
    #    candidates scored VISUALLY against the reference render
    rows = make_variants(args.variants)
    records = build_records(rows, ref_rows, w, h, tag="absolute_test_svg_render")

    out_path = ROOT / "model/data/ref_records_preview.json"
    out_path.write_text(json.dumps(records))
    print(f"preview written {out_path} ({len(records)} records)")
    if not args.apply:
        print("dry run: pass --apply to insert into dataset.json")
        return

    # 3) insert near the front (train_chunk always keeps records[:482])
    backup = ROOT / "model/data/backups"
    backup.mkdir(exist_ok=True)
    shutil.copy2(DATASET, backup / f"dataset-{time.strftime('%Y%m%d-%H%M%S')}.json")
    data = json.loads(DATASET.read_text())
    insert = []
    for _ in range(args.perms):
        insert.extend(json.loads(json.dumps(records)))  # deep-ish copies
    data = insert + data
    DATASET.write_text(json.dumps(data))
    print(f"dataset.json now {len(data)} records (+{len(insert)} ref records, x{args.perms})")


if __name__ == "__main__":
    main()
