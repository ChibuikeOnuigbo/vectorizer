"""Manifest builder (directive sections 2-4, 9, 32).

Merges every asset source into test-assets/manifest.json with visible
provenance sections: USER_PROVIDED / GENERATED / OPEN_LICENSE_SOURCE and
ORIGINAL_ASSET vs DERIVED_TEST_VARIANT. Counts are computed from files on
disk only - never fabricated.

  PYTHONPATH=vendor:app/deps:. python3 scripts/dataset/build_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent.parent
for p in (str(ROOT / "vendor"), str(ROOT / "app/deps")):
    sys.path.insert(0, p)

from PIL import Image  # noqa: E402

UP = ROOT / "test-assets/images/user-provided"


def dims(p: Path):
    try:
        im = Image.open(p)
        return {"width": im.size[0], "height": im.size[1], "mode": im.mode, "file_type": (p.suffix or "?")[1:].lower()}
    except Exception:
        return {}


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def build() -> dict:
    entries: list[dict] = []
    seen_md5: dict[str, str] = {}
    dup_notes = []

    usr_meta = {
        "blue-bird-appicon.png": ("user attachment 'download.png' 2026-09-25",
                                  "app icon with soft glow + gradients, transparent bg; HARD case"),
        "teal-orbit-logo.png": ("user attachment 'image-removebg-preview.png' 2026-09-25",
                                "clean one-color teal orbit logo, transparent bg"),
        "teal-orbit-logo-dup.png": ("user attachment 'image-removebg-preview (1).png' 2026-09-25",
                                    "EXACT BYTE DUPLICATE of teal-orbit-logo.png (md5 match), kept as dedup evidence"),
    }
    for f in sorted(UP.glob("*.png")):
        h = md5(f)
        src, note = usr_meta.get(f.name, ("user upload", ""))
        dup_of = seen_md5.get(h)
        if dup_of:
            dup_notes.append(f"{f.name} == {dup_of}")
        else:
            seen_md5[h] = f.name
        entries.append({
            "id": f"user-{f.stem}", "provenance": "USER_PROVIDED",
            "asset_kind": "ORIGINAL_ASSET" if not dup_of else "EXACT_DUPLICATE_KEPT_AS_EVIDENCE",
            "duplicate_of": dup_of,
            "image_path": str(f.relative_to(ROOT)), "source": src,
            "category": "real user image", "expected_characteristics": note,
            "md5": h, **dims(f),
            "test_status": "processed in qa/runner.py (user-* cases)",
        })

    gen_meta = json.loads((ROOT / "test-assets/generated_index.json").read_text())
    for g in gen_meta:
        f = ROOT / g["file"]
        svgo = ROOT / f"test-assets/svg/{f.stem}.svg"
        entries.append({
            "id": f"gen-{f.stem}", "provenance": "GENERATED",
            "asset_kind": g["asset_kind"], "variant_of": g["variant_of"],
            "image_path": g["file"],
            "svg_path": str(svgo.relative_to(ROOT)) if svgo.exists() else None,
            "source": "repo procedural generators (model/make_logos.py, gen_text_no_bg.py) + deterministic PIL conditions",
            "license": "generated in-repo, CC0-equivalent (no external imagery)",
            "category": g["category"], "expected_characteristics": g["note"],
            "md5": md5(f), **dims(f),
            "test_status": "processed in qa/runner.py (gen-* cases)",
        })

    families = ["fontawesome"]
    for fam in ("lucide", "bootstrap", "tabler", "hero"):
        if (ROOT / f"dataset/icons/{fam}/index.json").exists():
            families.append(fam)
    fa = []
    rendered = []
    for fam in families:
        fam_root = ROOT / f"dataset/icons/{fam}"
        raw_i = json.loads((fam_root / "index.json").read_text())
        fa.extend(raw_i["items"] if isinstance(raw_i, dict) else raw_i)
        rf = fam_root / "renders.json"
        if rf.exists():
            rendered.extend(json.loads(rf.read_text()))
    ren_by_id: dict[str, list[dict]] = {}
    for r_ in rendered:
        ren_by_id.setdefault(r_["id"], []).append(r_)
    for rec in fa:
        rel = rec["source_svg"]
        inp = ren_by_id.get(rec["id"], [])
        entries.extend([
            {
                "id": rec["id"], "provenance": "OPEN_LICENSE_SOURCE",
                "asset_kind": "ORIGINAL_ASSET",
                "source": rec["source"], "license": rec["license"],
                "image_path": None,
                "svg_path": rel,
                "md5": rec["md5"],
                "category": f"open-license icon ({rec['family']})",
                "expected_characteristics": "authored vector ground truth (single-color iconography)",
                "reference_svg": rel,
                "duplicate_status": rec["duplicate_status"],
                "test_status": "rendered + vectorized in qa/runner.py (icon-* cases)" if inp else "extracted, pending render",
            },
            *[
                {
                    "id": f"{rec['id']}-{Path(r_['file']).stem}", "provenance": "OPEN_LICENSE_SOURCE",
                    "asset_kind": "DERIVED_TEST_VARIANT", "variant_of": rec["id"],
                    "image_path": r_["file"],
                    "svg_path": rel,
                    "reference_svg": rel,
                    "source": rec["source"], "license": rec["license"],
                    "category": "rendered icon input (ground-truth pair)",
                    "transformation_applied": r_["condition"],
                    "md5": md5(ROOT / r_["file"]), **dims(ROOT / r_["file"]),
                    "test_status": "vectorized in qa/runner.py",
                } for r_ in inp
            ],
        ])

    counts: dict[str, int] = {}
    for e in entries:
        counts[e["provenance"]] = counts.get(e["provenance"], 0) + 1
    kinds: dict[str, int] = {}
    for e in entries:
        kinds[e["asset_kind"]] = kinds.get(e["asset_kind"], 0) + 1
    manifest = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generator": "scripts/dataset/build_manifest.py (counts computed from files on disk)",
        "totals": {
            "entries": len(entries),
            "by_provenance": counts,
            "by_asset_kind": kinds,
            "unique_md5": len({e["md5"] for e in entries}),
            "visible_test_image_files": len(entries_counts := [
                e for e in entries if e.get("image_path") and e.get("provenance") in ("USER_PROVIDED", "GENERATED")]),
        },
        "dedup": {
            "method": "md5 exact + same-source derivatives tracked via variant_of + perceptual near-dup",
            "notes": dup_notes,
            "perceptual": json.loads((ROOT / "test-assets/near_dup.json").read_text())["near_dup_group_count"]
            if (ROOT / "test-assets/near_dup.json").exists() else None,
            "perceptual_file": "test-assets/near_dup.json",
        },
        "qa": "qa/results/_summary.json (updated by qa/runner.py); verdicts: model_data_snapshot/verdicts.jsonl",
        "entries_file": "test-assets/manifest.entries.json.gz",
        "entries_note": "full entry list lives gzipped beside this file (67MB+ "
                        "plaintext would exceed GitHub's 50MB page limit; unzip to read)",
    }
    # heavy entries -> gzip artifact so manifest.json stays GitHub-visible (directive 30)
    import gzip
    with gzip.open(ROOT / "test-assets/manifest.entries.json.gz", "wt", encoding="utf8") as gz:
        json.dump(entries, gz, separators=(",", ":"))
    slim = dict(manifest)
    slim["entries"] = entries[:50]  # head sample for immediate inspection
    slim["entries_sample_only"] = 50
    (ROOT / "test-assets/manifest.json").write_text(json.dumps(slim, indent=1))
    print(json.dumps(manifest["totals"], indent=1))
    return manifest


if __name__ == "__main__":
    build()
