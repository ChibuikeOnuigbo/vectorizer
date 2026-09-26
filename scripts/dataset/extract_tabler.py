"""Extract Tabler Icons from the official npm package (MIT license).

Tabler Icons (github.com/tabler/tabler-icons) is published on npm as
`@tabler/icons` — official package, MIT license (LICENSE file inside).
One `npm pack @tabler/icons` tarball from the public registry, no auth or
rate-limit circumvention. Each icons/outline/*.svg and icons/filled/*.svg is
copied byte-for-byte as the preserved original (directive section 7) into
dataset/icons/tabler/<slug>/source.svg — filled entries are namespaced
`<slug>-filled` so style variants of the same base icon stay distinct real
assets (NOT duplicates; the drawn geometry differs).

  npm pack @tabler/icons; tar xzf tabler-icons-*.tgz
  PYTHONPATH=. python3 scripts/dataset/extract_tabler.py package
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_bootstrap import svg_ok  # shared validator (§10: reuse, don't duplicate)

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "dataset/icons/tabler"

LICENSE_HEADER = """Tabler Icons — MIT License
https://tabler.io/icons | https://github.com/tabler/tabler-icons
Obtained from the official npm package `@tabler/icons` (public registry,
single `npm pack` tarball, no access-control circumvention). MIT text below.
"""


def main() -> None:
    src_root = Path(sys.argv[1] if len(sys.argv) > 1 else "package").resolve()
    lic_src = src_root / "LICENSE"
    styles = {d: s for d, s in (("outline", ""), ("filled", "-filled"))}
    if not lic_src.is_file() or not all((src_root / "icons" / d).is_dir() for d in styles):
        print("run from an extracted `npm pack @tabler/icons` tarball (needs icons/outline + icons/filled)")
        sys.exit(1)
    pkg_json = json.loads((src_root / "package.json").read_text()) \
        if (src_root / "package.json").is_file() else {}
    ver = pkg_json.get("version", "unknown")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "licenses").mkdir(exist_ok=True)
    (OUT / "licenses/TABLER_ICONS.txt").write_text(
        LICENSE_HEADER + f"npm package version: {ver}\n\n" + lic_src.read_text())

    index = []
    seen: dict[str, str] = {}
    dupes = invalid = 0
    reasons: dict[str, int] = {}
    per_style: dict[str, int] = {}
    for style_dir, suffix in styles.items():
        for f in sorted((src_root / "icons" / style_dir).glob("*.svg")):
            slug = f.stem.lower() + suffix
            ok, why = svg_ok(f)
            if not ok:
                invalid += 1
                reasons[why.split(":")[0]] = reasons.get(why.split(":")[0], 0) + 1
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
                "id": f"tabler-{slug}",
                "family": "tabler",
                "style": style_dir,
                "source": f"npm/@tabler/icons {ver} icons/{style_dir} (official)",
                "license": "MIT (https://github.com/tabler/tabler-icons/blob/main/LICENSE)",
                "license_file": "dataset/icons/tabler/licenses/TABLER_ICONS.txt",
                "source_svg": str((d / "source.svg").relative_to(ROOT)),
                "md5": digest,
                "duplicate_status": "distinct",
                "asset_kind": "ORIGINAL_ASSET",
            })
    (OUT / "index.json").write_text(json.dumps({
        "family": "tabler",
        "source": f"npm package @tabler/icons {ver} (official)",
        "license": "MIT",
        "count": len(index),
        "per_style": per_style,
        "duplicates_skipped": dupes,
        "invalid_skipped": invalid,
        "invalid_reasons": reasons,
        "style_policy": "outline + filled are distinct drawn assets; filled slug-suffixed -filled",
        "items": index,
    }, indent=1))
    print(f"tabler icons: {len(index)} unique {per_style}, {dupes} md5 dupes skipped, "
          f"{invalid} invalid skipped {reasons}")


if __name__ == "__main__":
    main()
