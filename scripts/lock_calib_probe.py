#!/usr/bin/env python3
"""Recalibrate LOCK_* vtracer constants empirically (simplification mandate:
fewer knobs -> constants must be optimal). Scores candidate LOCK numerics on
every color-cutout row of the generated+user pool with the SHIPPED strict
audit scorer (qa/similarity_audit) so numbers line up with model_result sweeps.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "qa"))
sys.path.insert(0, str(ROOT / "app"))

from PIL import Image  # noqa: E402
import convert as C  # noqa: E402
from similarity_audit import audit  # noqa: E402

CANDS = [
    ("cur cp3 ld19 sp2", dict()),
    ("cp2 ld19 sp2", dict(color_precision=2)),
    ("cp4 ld19 sp2", dict(color_precision=4)),
    ("cp2 ld19 sp4", dict(color_precision=2, filter_speckle=4)),
    ("cp3 ld19 sp4", dict(filter_speckle=4)),
    ("cp2 ld12 sp2", dict(color_precision=2, layer_difference=12)),
]

idx = json.load(open(ROOT / "model_result/index.json"))
rows = []
for r in idx["entries"]:
    if r.get("status") == "OK" and str(r.get("engine", "")).startswith("color-cutout"):
        p = ROOT / r["source"]
        if ("generated" in r["source"] or "user-provided" in r["source"]) and p.exists():
            rows.append(p)
print(f"probe pool: {len(rows)} cutout rows", flush=True)

totals = {name: 0.0 for name, _ in CANDS}
counts = {name: 0 for name, _ in CANDS}
per_file = {}
for i, p in enumerate(rows):
    a = C.analyze(Image.open(p))
    line = [f"[{i+1}/{len(rows)}] {p.name}"]
    per_file[p.name] = {}
    for name, over in CANDS:
        params = {"_unlock": True, **over} if over else None
        try:
            svg = C.trace_with(a, params)
            s = audit(str(p), {"m": svg}, save_composite=False)["engines"]["m"]["visual_similarity_pct"]
        except Exception as e:
            s = 0.0; line.append(f"{name}=ERR({e})")
            continue
        totals[name] += s; counts[name] += 1
        per_file[p.name][name] = round(s, 1)
        line.append(f"{name.split(' ')[0]}={s:.1f}")
    print(" ".join(line), flush=True)

print("\n=== MEANS over", len(rows), "files ===")
for name, _ in CANDS:
    if counts[name]:
        print(f"{name}: {totals[name]/counts[name]:.2f}")
(ROOT / "scripts/lock_calib_probe.json").write_text(json.dumps(per_file, indent=1))
