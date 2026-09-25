"""Extract Lucide icons from the repo's own ISC-licensed bundle.

app/static/lucide/lucide.min.js is the official UMD build (v1.47.0, ISC,
header retained in the same file). The bundle embeds every icon's node data
as arrays of [tag,{attrs}] children. We parse the JS AST-ish structure with a
balanced-bracket scanner (regexes alone are brittle on nested d attributes),
rebuild standard 24x24 stroke SVG documents, dedupe by md5, and write
dataset/icons/lucide/<slug>/source.svg + licenses/LUCIDE.txt.

  PYTHONPATH=. python3 scripts/dataset/extract_lucide.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLE = ROOT / "app/static/lucide/lucide.min.js"
OUT = ROOT / "dataset/icons/lucide"

LICENSE = """Lucide Icons — ISC License
https://lucide.dev/license
Obtained from the application's own bundled app/static/lucide/lucide.min.js
(official UMD build, ISC license header included in the same file).
"""

ICON_ATTRS = {
    "xmlns": "http://www.w3.org/2000/svg",
    "width": "24",
    "height": "24",
    "viewBox": "0 0 24 24",
    "fill": "none",
    "stroke": "currentColor",
    "stroke-width": "2",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
}


def parse_values(s: str, i: int):
    """Parse a JS value at position i in minified source. Returns (value, next_i)."""
    ch = s[i]
    if ch == '"':
        j = i + 1
        esc = False
        while j < len(s):
            c = s[j]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                break
            j += 1
        return s[i + 1 : j], j + 1
    if ch == "[":
        items = []
        i += 1
        while True:
            while i < len(s) and s[i] in " \n\t,":
                i += 1
            if s[i] == "]":
                return items, i + 1
            v, i = parse_values(s, i)
            items.append(v)
    if ch == "{":
        obj = {}
        i += 1
        while True:
            while i < len(s) and s[i] in " \n\t,":
                i += 1
            if s[i] == "}":
                return obj, i + 1
            if s[i] == '"':
                key, i = parse_values(s, i)
                key = json.loads(key)
            else:
                m = re.match(r"[A-Za-z_$][\w$]*", s[i:])
                key = m.group(0)
                i += len(key)
            while i < len(s) and s[i] in " \n\t:":
                i += 1
            val, i = parse_values(s, i)
            obj[key] = val
    # bare words: numbers, booleans, identifiers
    m = re.match(r"-?[\d.]+(?:e[+-]?\d+)?|true|false|null|[A-Za-z_$][\w$]*", s[i:])
    if m:
        tok = m.group(0)
        i += len(tok)
        if tok in ("true", "false", "null"):
            return json.loads(tok.replace("null", "None") if tok == "null" else tok), i
        try:
            return float(tok), i
        except ValueError:
            return ("__ident__", tok), i
    raise ValueError(f"cannot parse at {i}: {s[i:i+40]!r}")


def camel_to_slug(name: str) -> str:
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name).replace("Icon", "").lower().strip("-")
    return t or name.lower()


def main() -> None:
    src = BUNDLE.read_text(encoding="utf8")
    m = re.search(r'@license lucide ([v\d.]+) - ISC', src)
    ver = m.group(1) if m else "unknown"
    # minified: `<ident>=[[...]]` array defs + final frozen exports map of
    # `IconName:ident` pairs. Parse arrays by ident, then attach export names.
    arr_pat = re.compile(r'[\s,;{]([$\w]{1,4})=(\[\[)', re.M)
    arrays = {}
    for mm in arr_pat.finditer(src):
        ident = mm.group(1)
        if ident in arrays:
            continue
        try:
            val, _ = parse_values(src, mm.start(2))
        except Exception:
            continue
        if (isinstance(val, list) and val and isinstance(val[0], list)
                and len(val[0]) >= 2 and isinstance(val[0][1], dict)
                and isinstance(val[0][0], str) and val[0][0].strip('"') in
                ("path", "circle", "rect", "ellipse", "line", "polygon", "polyline")):
            arrays[ident] = val
    freeze = src.find("Object.freeze({")
    if freeze == -1:
        print("no exports map found"); sys.exit(3)
    # aliases can point to other idents (`AlarmCloc…:C` where C is a naked
    # `circle` array like C="circle",{...}? no: ident arrays only). Also allow
    # idents that are themselves re-aliases of arrays: `Name:X` -> `X=Ya`-style
    alias_pat = re.compile(r'([A-Z][A-Za-z0-9]{2,40}):([$\w]{1,4})[,}]')
    entries: dict[str, list] = {}
    for mm in alias_pat.finditer(src, freeze, min(len(src), freeze + 200_000)):
        name, ident = mm.group(1), mm.group(2)
        if name not in entries and ident in arrays:
            entries[name] = arrays[ident]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "licenses").mkdir(exist_ok=True)
    (OUT / "licenses/LUCIDE.txt").write_text(LICENSE + f"Bundle version: lucide {ver}\n")
    index = []
    seen: dict[str, str] = {}
    dupes = 0
    for name, val in sorted(entries.items()):
        slug = camel_to_slug(name)
        if (OUT / slug).exists():
            slug2 = slug + "-" + re.sub(r"^.*?(?=\d+$)", "", slug)
        children = []
        for node in val:
            if len(node) < 2 or not isinstance(node[1], dict):
                continue
            tag_raw, attrs_raw = node[0], node[1]
            tag = tag_raw.strip('"') if isinstance(tag_raw, str) else str(tag_raw)
            attr_pairs = []
            for k, v in attrs_raw.items():
                vv = v.strip('"') if isinstance(v, str) else v
                attr_pairs.append(f'{k}="{vv}"')
            attr_str = " ".join(attr_pairs)
            children.append(f"<{tag} {attr_str}/>")
        svg = "<svg " + " ".join(f'{k}="{v}"' for k, v in ICON_ATTRS.items()) + ">" + "".join(children) + "</svg>"
        digest = hashlib.md5(svg.encode()).hexdigest()
        if digest in seen:
            dupes += 1
            continue
        seen[digest] = slug
        d = OUT / slug
        d.mkdir(exist_ok=True)
        (d / "source.svg").write_text(svg, encoding="utf8")
        index.append({
            "id": f"lucide-{slug}",
            "family": "lucide",
            "source": "app/static/lucide/lucide.min.js bundle (lucide %s)" % ver,
            "license": "ISC (https://lucide.dev/license)",
            "license_file": "dataset/icons/lucide/licenses/LUCIDE.txt",
            "source_svg": str((d / "source.svg").relative_to(ROOT)),
            "md5": digest,
            "duplicate_status": "distinct",
            "asset_kind": "ORIGINAL_ASSET",
        })
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print(f"lucide {ver}: extracted {len(index)} icons, {dupes} md5 duplicates skipped")


if __name__ == "__main__":
    if not BUNDLE.exists():
        print("bundle missing"); sys.exit(2)
    main()
