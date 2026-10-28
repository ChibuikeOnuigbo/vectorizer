#!/usr/bin/env python3
"""Regenerate wiped corpus pixels deterministically from seed-namespaced
filenames (logo_e{seed}_{i:04d}.png / text_{seed}_{i:04d}.png) so the
committed dataset records line up with real pixels again after sandbox resets.
Usage: PYTHONPATH=vendor:app/deps:. python3 scripts/regen_pixels.py
"""
import json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "model" / "data"


def main() -> None:
    recs = json.loads((DATA / "dataset.json").read_text())

    def _exists(p: str) -> bool:
        q = Path(p)
        return q.exists() or (ROOT / p).exists()

    missing = [r for r in recs if not _exists(r["path"])]
    print(f"records={len(recs)} missing_pixels={len(missing)}")
    by_key = defaultdict(int)
    legacy = 0
    for r in missing:
        m = re.match(r"(logo|text)_e?(\d+)_(\d{4})\.png", r["name"])
        if not m:
            legacy += 1
            continue
        kind, seed = m.group(1), m.group(2)
        d = Path(r["path"]).parent.name
        by_key[(d, kind, int(seed))] += 1
    for (d, kind, seed), n in sorted(by_key.items()):
        out = DATA / d
        out.mkdir(parents=True, exist_ok=True)
        if kind == "logo":
            cmd = [sys.executable, "-m", "model.make_logos", "--out", str(out),
                   "--count", "600", "--seed", str(seed)]
            if d == "logos_notext":
                cmd.append("--no-text")
        else:
            cmd = [sys.executable, "model/gen_text_no_bg.py", "--out", str(out),
                   "--count", "600", "--seed", str(seed)]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           env={**__import__("os").environ,
                                "PYTHONPATH": "vendor:app/deps:."})
        tag = "ok" if r.returncode == 0 else f"FAIL {r.stderr[-200:]}"
        print(f"regen {d}/seed={seed} (+{n} refs) -> {tag}")
    # degraded variants derive deterministically (rng 99) from clean sources
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "model"))
    import forever_train  # noqa: E402
    counts = forever_train.count_images()
    forever_train.gen_degraded(counts)
    still = sum(1 for r in recs if not _exists(r["path"]))
    print(f"legacy_unregenerable={legacy} after regen still_missing={still}")


if __name__ == "__main__":
    main()
