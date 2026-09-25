"""Extract Bootstrap Icons from the official npm package (MIT license).

Bootstrap Icons (twbs/icons) is published on npm as `bootstrap-icons`
https://www.npmjs.com/package/bootstrap-icons — official package of the
Bootstrap Authors, MIT licensed (LICENSE file inside the tarball). We fetch
exactly one tarball via `npm pack bootstrap-icons` (public registry, no
auth/rate-limit circumvention), extract it, and copy each icons/*.svg
byte-for-byte as the preserved original (directive section 7) into
dataset/icons/bootstrap/<slug>/source.svg with an index + copied MIT text.

  npm pack bootstrap-icons; tar xzf bootstrap-icons-*.tgz   # -> package/
  PYTHONPATH=. python3 scripts/dataset/extract_bootstrap.py package
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "dataset/icons/bootstrap"

LICENSE_HEADER = """Bootstrap Icons — MIT License
https://icons.getbootstrap.com/ | https://github.com/twbs/icons
Obtained from the official npm package `bootstrap-icons` (public registry,
single `npm pack` tarball, no access-control circumvention). MIT text below.
"""


def svg_ok(path: Path) -> tuple[bool, str]:
    try:
        root = ET.parse(path).getroot()
    except Exception as e:  # malformed XML
        return False, f"xml-parse:{e}"
    tag = root.tag.split("}")[-1].lower()
    if tag != "svg":
        return False, "root-not-svg"
    if "viewBox" not in root.attrib:
        return False, "no-viewBox"
    if len(list(root)) == 0:
        return False, "empty-svg"
    return True, "ok"


def main() -> None:
    src_root = Path(sys.argv[1] if len(sys.argv) > 1 else "package").resolve()
    icons_dir = src_root / "icons"
    lic_src = src_root / "LICENSE"
    if not icons_dir.is_dir() or not lic_src.is_file():
        print("run from an extracted `npm pack bootstrap-icons` tarball; "
              f"missing {icons_dir if not icons_dir.is_dir() else lic_src}")
        sys.exit(1)
    pkg_json = json.loads((src_root / "package.json").read_text()) \
        if (src_root / "package.json").is_file() else {}
    ver = pkg_json.get("version", "unknown")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "licenses").mkdir(exist_ok=True)
    (OUT / "licenses/BOOTSTRAP_ICONS.txt").write_text(
        LICENSE_HEADER + f"npm package version: {ver}\n\n" + lic_src.read_text())

    index = []
    seen: dict[str, str] = {}
    dupes = invalid = 0
    reasons: dict[str, int] = {}
    for f in sorted(icons_dir.glob("*.svg")):
        slug = f.stem.lower()
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
        index.append({
            "id": f"bootstrap-{slug}",
            "family": "bootstrap",
            "source": f"npm/bootstrap-icons {ver} (official twbs package)",
            "license": "MIT (https://github.com/twbs/icons/blob/main/LICENSE.md)",
            "license_file": "dataset/icons/bootstrap/licenses/BOOTSTRAP_ICONS.txt",
            "source_svg": str((d / "source.svg").relative_to(ROOT)),
            "md5": digest,
            "duplicate_status": "distinct",
            "asset_kind": "ORIGINAL_ASSET",
        })
    (OUT / "index.json").write_text(json.dumps({
        "family": "bootstrap",
        "source": f"npm package bootstrap-icons {ver} (official)",
        "license": "MIT",
        "count": len(index),
        "duplicates_skipped": dupes,
        "invalid_skipped": invalid,
        "invalid_reasons": reasons,
        "items": index,
    }, indent=1))
    print(f"bootstrap icons: {len(index)} unique, {dupes} md5 dupes skipped, "
          f"{invalid} invalid skipped {reasons}")


if __name__ == "__main__":
    main()
