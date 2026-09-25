"""Dataset step 1-2: obtain + preserve legitimate open-license source SVGs.

Copies Font Awesome Free SVGs (bundled via the `fontawesome-free` pip
package — icons CC BY 4.0, code MIT, fonts SIL OFL) from the locally
installed package into the tracked dataset directory, with per-family
license notes and md5-based dedup. No network access, no site scraping,
no robots circumvention: files come from a package installed via pip.

  PYTHONPATH=. python3 scripts/dataset/extract_pairs.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

FA_LICENSE = """Font Awesome Free License
https://fontawesome.com/license/free
- Icons: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/
- Fonts: SIL OFL 1.1 https://scripts.sil.org/OFL
- Code:  MIT https://opensource.org/licenses/MIT
Source package: fontawesome-free (PyPI), installed locally.
"""

FA_DIR_CANDIDATES = [
    ROOT / "app/deps/fontawesome-free/static/fontawesome_free/js-packages/@fortawesome/fontawesome-free/svgs",
    ROOT / "vendor/fontawesome-free/static/fontawesome_free/js-packages/@fortawesome/fontawesome-free/svgs",
]
OUT = ROOT / "dataset/icons/fontawesome"


def main(limit_per_family: int = 400) -> None:
    src_root = next((p for p in FA_DIR_CANDIDATES if p.is_dir()), None)
    if src_root is None:
        print("FATAL: fontawesome svgs not found locally (deps wiped?). pip install fontawesome-free")
        sys.exit(2)
    (OUT / "licenses").mkdir(parents=True, exist_ok=True)
    (OUT / "licenses/FONT_AWESOME_FREE.txt").write_text(FA_LICENSE)
    index = []
    seen: set[str] = set()
    dupes = 0
    for family in ("solid", "regular", "brands"):
        fam_out = OUT / family
        fam_out.mkdir(parents=True, exist_ok=True)
        count = 0
        for svg in sorted((src_root / family).glob("*.svg")):
            digest = hashlib.md5(svg.read_bytes()).hexdigest()
            kind = "exact_duplicate" if digest in seen else "distinct"
            if digest in seen:
                dupes += 1
                continue
            seen.add(digest)
            if count >= limit_per_family:
                continue
            count += 1
            slug = svg.stem
            ddir = fam_out / slug
            ddir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(svg, ddir / "source.svg")
            index.append({
                "id": f"fa-{family}-{slug}",
                "family": f"fontawesome/{family}",
                "source": "fontawesome-free pip package (bundled Font Awesome Free)",
                "license": "CC BY 4.0 (icon) / MIT (code)",
                "license_file": "dataset/icons/fontawesome/licenses/FONT_AWESOME_FREE.txt",
                "source_svg": str((ddir / "source.svg").relative_to(ROOT)),
                "md5": digest,
                "duplicate_status": kind,
                "asset_kind": "ORIGINAL_ASSET",
            })
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print(f"copied {len(index)} distinct svgs, skipped {dupes} exact duplicates")


if __name__ == "__main__":
    main()
