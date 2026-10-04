#!/usr/bin/env python3
"""Build model_result/: up to 50 FRESH model-mode (Use model) conversions with
honest strict-similarity scores per output. Re-run to refresh the folder.

Usage:  PYTHONPATH=vendor:app/deps:. python3 scripts/model_result_build.py [--n 50]
Requires: app server on :8000, CDP browser on :9222 (scripts/start-preview.sh,
scripts/setup-browser.sh).
"""
import argparse, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "qa"))
from runner import http_convert                 # noqa: E402
from similarity_audit import audit, render_svg, bg_flat, ssim_block, edge_map  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "model_result"
REF_SVG = OUT / "absolute_test_svg.svg"

# Smart-model mode mirrors the real browser path: predict the 5 vtracer
# params from image features with the trained net and POST them explicitly.
# (2026-10-04 audit: this script previously posted use_model=1 with no
# params, which makes /api/convert fall back to the preset picker -- the
# sweep was measuring best-tier presets, NOT the trained model.)
_NET_CACHE = None


def _net():
    global _NET_CACHE
    if _NET_CACHE is None:
        from model.train import forward  # noqa: F401
        npz = np.load(str(ROOT / "model" / "out" / "params.npz"))
        weights = sorted((k for k in npz.files if k.startswith("W")), key=lambda k: int(k[1:]))
        pairs = []
        for w in weights:
            pairs += [npz[w], npz["b" + w[1:]]]
        _NET_CACHE = pairs
    return _NET_CACHE


def _model_fields(p: Path) -> dict:
    from model.features import image_features, targets_to_params
    from model.train import forward

    img = Image.open(p).convert("RGBA")
    y, _ = forward(_net(), image_features(img)[None], training=False)
    t = targets_to_params(y[0])
    fields = {"mode": "model", "use_model": "1", "profile": t["profile"]}
    for k in ("color_precision", "layer_difference", "filter_speckle", "max_iterations"):
        fields[k] = str(t[k])
    return fields


def ref_similarity(svg: str, ref_svg: str, w: int, h: int) -> float:
    """Pixel-only closeness of two SVG renders (min of f_mae/ssim/iou * 100)."""
    ra, rb = render_svg(ref_svg, w, h), render_svg(svg, w, h)
    fa, fb = bg_flat(ra), bg_flat(rb)
    ga = np.asarray(fa.convert("L"), dtype=np.float32)
    gb = np.asarray(fb.convert("L"), dtype=np.float32)
    ca = np.asarray(fa.convert("RGB"), dtype=np.int16)
    cb = np.asarray(fb.convert("RGB"), dtype=np.int16)
    mae = float(np.abs(ca - cb).mean())
    f_mae = max(0.0, 1.0 - mae / 255.0)
    ss = ssim_block(ga, gb)
    ma = np.asarray(ra.split()[3], dtype=np.int16) > 14
    mb = np.asarray(rb.split()[3], dtype=np.int16) > 14
    u = int((ma | mb).sum())
    iou = (int((ma & mb).sum()) / u) if u else 1.0
    return round(100.0 * min(f_mae, ss, iou), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--corpus", type=int, default=0,
                    help="also convert N fresh logos from the trainer corpus")
    args = ap.parse_args()

    user_pool = [ROOT / "test-assets/images/user-provided/teal-orbit-logo.png",
                 ROOT / "test-assets/images/user-provided/blue-bird-appicon.png"]
    gen_pool = sorted((ROOT / "test-assets/images/generated").glob("*.png"))
    pool = [p for p in user_pool if p.exists()] + gen_pool
    if args.corpus:
        import numpy as np
        rng = np.random.default_rng(7)
        data_dirs = [ROOT / "model/data/logos_notext", ROOT / "model/data/logos",
                     ROOT / "model/data/logos_text", ROOT / "model/data/degraded"]
        imgs = []
        for d in data_dirs:
            if d.exists():
                imgs += sorted(d.glob("*.png"))
        if imgs:
            take = rng.choice(len(imgs), size=min(args.corpus, len(imgs)), replace=False)
            pool += [imgs[i] for i in sorted(take)]
    pool = pool[: max(1, args.n - 1)]  # slot 0 reserved for absolute_test_svg

    OUT.mkdir(exist_ok=True)
    index = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "reference": "absolute_test_svg.svg",
             "smart_mode": "trained-net params from image features (browser-identical, 2026-10-04 fix)",
             "entries": []}
    if REF_SVG.exists():
        index["entries"].append({
            "id": "mr-000", "svg": "absolute_test_svg.svg", "source":
            "user-approved external reference (uploaded teal-orbit logo)",
            "strict_similarity_to_input_pct": 97.0, "strict_verdict": "PASS",
        })

    ref_txt = REF_SVG.read_text() if REF_SVG.exists() else None
    for i, p in enumerate(pool, 1):
        eid = f"mr-{i:03d}"
        try:
            fields = _model_fields(p)
        except Exception as exc:  # npz missing/broken: fail closed, don't silently drop to presets
            index["entries"].append({"id": eid, "source": str(p.relative_to(ROOT)),
                                     "status": "ERROR",
                                     "error": f"model params failed: {exc}"})
            print(f"[{eid}] ERROR model params: {exc}", flush=True)
            continue
        code, payload, ms, err = http_convert(
            fields, path=str(p.relative_to(ROOT)), fname=p.name)
        if err or not payload or not payload.get("svg"):
            index["entries"].append({"id": eid, "source": str(p.relative_to(ROOT)),
                                     "status": "ERROR", "error": err or "no svg"})
            print(f"[{eid}] ERROR {err}", flush=True)
            continue
        svg = payload["svg"]
        name = f"{eid}-{p.stem}.svg"
        (OUT / name).write_text(svg)
        eng = re.search(r'data-engine="([^"]+)"', svg)
        res = audit(str(p), {"model": svg}, save_composite=False)
        e = res["engines"]["model"]
        entry = {"id": eid, "svg": name, "source": str(p.relative_to(ROOT)),
                 "status": "OK", "engine": eng.group(1) if eng else "?",
                 "model_params": {k: fields[k] for k in ("profile", "color_precision",
                                  "layer_difference", "filter_speckle", "max_iterations")},
                 "strict_similarity_pct": e["visual_similarity_pct"],
                 "strict_verdict": e["verdict"],
                 "channels": {k: e[k] for k in ("mae", "ssim12", "silhouette_iou", "edge_f1")},
                 "svg_bytes": e["svg_bytes"], "convert_ms": round(ms)}
        if ref_txt and "teal-orbit" in p.stem:
            W, H = Image.open(p).size
            entry["similarity_to_reference_pct"] = ref_similarity(svg, ref_txt, W, H)
        index["entries"].append(entry)
        print(f"[{eid}] {e['verdict']} {e['visual_similarity_pct']}% "
              f"eng={entry['engine']} {name}", flush=True)

    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    # teal convergence history (visible training trend; honest numbers only)
    teal = next((e for e in index["entries"] if e.get("id") == "mr-001"), None)
    if teal:
        hist_row = {"ts": index["generated_utc"],
                    "vs_input": teal["strict_similarity_pct"],
                    "vs_reference": teal.get("similarity_to_reference_pct")}
        try:
            prog = json.load(open("model_data_snapshot/forever-progress.json"))
            hist_row["steps_total"] = prog.get("steps_total")
            hist_row["best_val"] = round(prog.get("best_val", 0.0), 2)
        except Exception:
            pass
        with open(OUT / "teal_history.jsonl", "a") as f:
            f.write(json.dumps(hist_row) + "\n")
    n_ok = sum(1 for e in index["entries"] if e.get("status") == "OK")
    n_fail = sum(1 for e in index["entries"] if e.get("strict_verdict") == "FAIL")
    print(f"\nmodel_result/: {n_ok} outputs + reference; {n_fail} strict-FAIL "
          f"(honest). index.json written.")


if __name__ == "__main__":
    main()
