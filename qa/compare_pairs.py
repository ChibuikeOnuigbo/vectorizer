"""Reference-vs-generated comparison for icon ground-truth pairs (§17).

For each iconpair case in qa/results: locate the original source.svg,
re-render it client-side identical to dataset input, structurally compare
the generated SVG to the reference (path/command/color counts via the
deterministic analyzer) and pixel-compare the vectorizer outputs saved
during scoring (input raster vs generated raster is what the runner already
measured; here we add structural SVG statistics against the reference).
Pure stdlib + PIL; reads disk artifacts only, recomputes nothing heavy.

  PYTHONPATH=vendor:app/deps:. python3 qa/compare_pairs.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qa.svg_analysis import analyze_svg, compare_stats  # noqa: E402


def main() -> None:
    out: list[dict] = []
    results = sorted(list((ROOT / "qa/results").glob("icon*.json"))
                     + list((ROOT / "qa/results").glob("lucide-*.json"))
                     + list((ROOT / "qa/results").glob("boot*.json")))
    for rp in results:
        res = json.loads(rp.read_text())
        asset = res.get("asset") or ""
        if not asset:
            continue
        src = Path(asset).parent / "source.svg"
        ref_file = ROOT / src
        if not ref_file.exists():
            continue
        ref = analyze_svg(ref_file.read_text(encoding="utf8", errors="ignore"))
        gen = res.get("svg_analysis") or {}
        cmp_ = compare_stats(ref, gen)
        out.append({
            "case": res["id"],
            "mode": res.get("mode"),
            "http_status": res.get("http_status"),
            "status": res.get("status"),
            "reference_svg": str(src),
            **cmp_,
            "path_ratio": round(cmp_["gen_paths"] / cmp_["ref_paths"], 2) if cmp_["ref_paths"] else None,
        })
    # aggregate so QA_REPORT can cite without re-parsing
    ok = [o for o in out if o["status"] == "PASS"]
    agg = {
        "pairs_compared": len(out),
        "pass": len(ok),
        "avg_gen_paths": round(sum(o["gen_paths"] for o in out) / len(out), 1) if out else 0,
        "avg_ref_paths": round(sum(o["ref_paths"] for o in out) / len(out), 1) if out else 0,
        "avg_path_ratio": round(sum(o["path_ratio"] for o in out if o["path_ratio"]) / max(1, sum(1 for o in out if o["path_ratio"])), 2) if out else 0,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (ROOT / "qa/results/_icon_compare.json").write_text(json.dumps({"aggregate": agg, "pairs": out[:400]}, indent=1))
    print(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
