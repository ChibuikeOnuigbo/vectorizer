"""Extract Heroicons from the official npm package (MIT license).

Heroicons (tailwindlabs/heroicons) is published on npm as `heroicons` v2 —
official Tailwind Labs package, MIT (LICENSE inside the tarball). One
`npm pack heroicons` tarball from the public registry, no auth or
rate-limit circumvention. Each size/style directory is copied
byte-for-byte as preserved originals into dataset/icons/hero/<slug>/ —
styles are namespaced with size+style suffixes (24-outline / 24-solid /
20-solid / 16-solid); same-concept icons across sizes/styles are distinct
drawn assets (like tabler outline vs filled), near-dup detection groups
them for training-split hygiene instead of pretending either count is
different from what it is.

  npm pack heroicons; tar xzf heroicons-*.tgz
  PYTHONPATH=. python3 scripts/dataset/extract_hero.py package
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_bootstrap import svg_ok  # shared validator (§10 reuse)

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "dataset/icons/hero"

STYLES = {
    "24/outline": "24outline",
    "24/solid": "24solid",
    "20/solid": "20solid",
    "16/solid": "16solid",
}

LICENSE_HEADER = """Heroicons — MIT License
https://heroicons.com | https://github.com/tailwindlabs/heroicons
Obtained from the official npm package `heroicons` (public registry,
single `npm pack` tarball, no access-control circumvention). MIT text below.
"""


def main() -> None:
    src_root = Path(sys.argv[1] if len(sys.argv) > 1 else "package").resolve()
    lic_src = src_root / "LICENSE"
    if not lic_src.is_file() or not (src_root / "24/outline").is_dir():
        print("run from an extracted `npm pack heroicons` tarball (needs 24/outline)")
        sys.exit(1)
    pkg_json = json.loads((src_root / "package.json").read_text()) \
        if (src_root / "package.json").is_file() else {}
    ver = pkg_json.get("version", "unknown")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "licenses").mkdir(exist_ok=True)
    (OUT / "licenses/HEROICONS.txt").write_text(
        LICENSE_HEADER + f"npm package version: {ver}\n\n" + lic_src.read_text())

    index = []
    seen: dict[str, str] = {}
    dupes = invalid = 0
    per_style: dict[str, int] = {}
    for style_dir, suffix in STYLES.items():
        sdir = src_root / style_dir
        if not sdir.is_dir():
            continue
        for f in sorted(sdir.glob("*.svg")):
            slug = f"{f.stem.lower()}-{suffix}"
            ok, why = svg_ok(f)
            if not ok:
                invalid += 1
                continue
            raw = f.read_bytes()
            digest = hashlib.md5(raw).hexdigest()
            if digest in seen:
                dupes += 1
                continue
            seen[digest] = slug
            d = OUT / slug
            d.mkdir(exist_ok=True)
            shutil.copyfile(f, d / "source.svg")
            per_style[style_dir] = per_style.get(style_dir, 0) + 1
            index.append({
                "id": f"hero-{slug}",
                "family": "hero",
                "style": style_dir,
                "source": f"npm/heroicons {ver} {style_dir} (official)",
                "license": "MIT (https://github.com/tailwindlabs/heroicons/blob/master/LICENSE)",
                "license_file": "dataset/icons/hero/licenses/HEROICONS.txt",
                "source_svg": str((d / "source.svg").relative_to(ROOT)),
                "md5": digest,
                "duplicate_status": "distinct",
                "asset_kind": "ORIGINAL_ASSET",
            })
    (OUT / "index.json").write_text(json.dumps({
        "family": "hero",
        "source": f"npm package heroicons {ver} (official Tailwind Labs)",
        "license": "MIT",
        "count": len(index),
        "per_style": per_style,
        "duplicates_skipped": dupes,
        "invalid_skipped": invalid,
        "style_policy": "size+style namespaced; same concept across styles = distinct drawn asset",
        "items": index,
    }, indent=1))
    print(f"heroicons: {len(index)} unique {per_style}, {dupes} md5 dupes, {invalid} invalid")


if __name__ == "__main__":
    main()
