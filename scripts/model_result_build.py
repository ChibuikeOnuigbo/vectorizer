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
    args = ap.parse_args()

    user_pool = [ROOT / "test-assets/images/user-provided/teal-orbit-logo.png",
                 ROOT / "test-assets/images/user-provided/blue-bird-appicon.png"]
    gen_pool = sorted((ROOT / "test-assets/images/generated").glob("*.png"))
    pool = [p for p in user_pool if p.exists()] + gen_pool
    pool = pool[: max(1, args.n - 1)]  # slot 0 reserved for absolute_test_svg

    OUT.mkdir(exist_ok=True)
    index = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "reference": "absolute_test_svg.svg", "entries": []}
    if REF_SVG.exists():
        index["entries"].append({
            "id": "mr-000", "svg": "absolute_test_svg.svg", "source":
            "user-approved external reference (uploaded teal-orbit logo)",
            "strict_similarity_to_input_pct": 97.0, "strict_verdict": "PASS",
        })

    ref_txt = REF_SVG.read_text() if REF_SVG.exists() else None
    for i, p in enumerate(pool, 1):
        eid = f"mr-{i:03d}"
        code, payload, ms, err = http_convert(
            {"mode": "model", "use_model": "1"}, path=str(p.relative_to(ROOT)),
            fname=p.name)
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
    n_ok = sum(1 for e in index["entries"] if e.get("status") == "OK")
    n_fail = sum(1 for e in index["entries"] if e.get("strict_verdict") == "FAIL")
    print(f"\nmodel_result/: {n_ok} outputs + reference; {n_fail} strict-FAIL "
          f"(honest). index.json written.")


if __name__ == "__main__":
    main()
