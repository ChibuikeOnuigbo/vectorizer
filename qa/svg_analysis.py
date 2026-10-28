"""Deterministic SVG static analysis (no AI, no external deps).

OBSERVED_FROM_SVG facts only: parse the actual SVG text with the stdlib
XML parser and count/measure. Nothing here is an interpretation or a guess.

Usage:
  from qa.svg_analysis import analyze_svg
  info = analyze_svg(svg_text)
CLI:
  python3 qa/svg_analysis.py some.svg
"""
from __future__ import annotations

import hashlib
import re
import sys
import xml.dom.minidom  # noqa: F401  (kept for lineage clarity)
import xml.etree.ElementTree as ET
from collections import Counter

SVG_NS = "{http://www.w3.org/2000/svg}"
_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", re.I)
_CMD = re.compile(r"[MmLlHhVvZzCcSsQqTtAa]")
_FILL = re.compile(r'fill\s*[:=]\s*["\']?\s*(#[0-9a-fA-F]{3,8}|\w+)\b')
_STROKE = re.compile(r'stroke\s*[:=]\s*["\']?\s*(#[0-9a-fA-F]{3,8}|\w+)\b')


def _tag(local: str) -> str:
    return local.rsplit("}", 1)[-1]


def path_stats(d: str) -> dict:
    """Facts about a path `d` attribute: commands, points, coordinate ranges."""
    if not d:
        return {"commands": 0, "points": 0, "min_abs_coord": 0.0, "max_abs_coord": 0.0}
    cmds = len(_CMD.findall(d))
    nums = [float(x) for x in _NUM.findall(d)]
    return {
        "commands": cmds,
        "points": max(0, len(nums) // 2),
        "min_abs_coord": min(map(abs, nums)) if nums else 0.0,
        "max_abs_coord": max(map(abs, nums)) if nums else 0.0,
    }


def analyze_svg(svg_text: str) -> dict:
    """Return machine-readable facts about the SVG document."""
    out: dict = {
        "bytes": len(svg_text.encode("utf-8", "ignore")),
        "sha1": hashlib.sha1(svg_text.encode("utf-8", "ignore")).hexdigest()[:12],
        "xml_valid": False,
        "root_is_svg": False,
        "elements": {},
        "counts": {},
        "viewBox": None,
        "width": None,
        "height": None,
        "fills": [],
        "strokes": [],
        "uses_gradients": False,
        "uses_clip": False,
        "uses_mask": False,
        "uses_transform": False,
        "path_total_commands": 0,
        "max_path_commands": 0,
        "empty_elements": 0,
        "duplicate_path_d": 0,
        "extreme_coord_over_1e5": 0,
        "warnings": [],
    }
    try:
        root = ET.fromstring(svg_text)
        out["xml_valid"] = True
    except ET.ParseError as exc:
        out["warnings"].append(f"SVG_PARSE_FAILURE: {exc}")
        return out
    out["root_is_svg"] = _tag(root.tag) == "svg"
    out["viewBox"] = root.attrib.get("viewBox")
    out["width"] = root.attrib.get("width")
    out["height"] = root.attrib.get("height")

    tags: Counter[str] = Counter()
    path_cmds = []
    d_seen: Counter[str] = Counter()
    empty = 0
    extreme = 0
    for el in root.iter():
        t = _tag(el.tag)
        tags[t] += 1
        if t == "path":
            d = el.attrib.get("d", "")
            st = path_stats(d)
            path_cmds.append(st["commands"])
            d_seen[d] += 1
            if st["max_abs_coord"] > 1e5:
                extreme += 1
        if len(list(el)) == 0 and not (el.text or "").strip() and t not in ("path", "rect", "circle", "ellipse", "line", "polygon", "polyline", "use", "stop"):
            if not el.attrib:
                empty += 1
        if "transform" in el.attrib:
            out["uses_transform"] = True
        if t in ("linearGradient", "radialGradient"):
            out["uses_gradients"] = True
        if t == "clipPath":
            out["uses_clip"] = True
        if t == "mask":
            out["uses_mask"] = True

    out["elements"] = dict(tags.most_common(12))
    out["counts"] = {
        "total_elements": sum(tags.values()),
        "paths": tags.get("path", 0),
        "groups": tags.get("g", 0),
        "circles": tags.get("circle", 0),
        "rects": tags.get("rect", 0),
        "ellipses": tags.get("ellipse", 0),
        "polygons": tags.get("polygon", 0),
        "polylines": tags.get("polyline", 0),
        "lines": tags.get("line", 0),
    }
    out["path_total_commands"] = sum(path_cmds)
    out["max_path_commands"] = max(path_cmds) if path_cmds else 0
    out["duplicate_path_d"] = sum(c - 1 for c in d_seen.values() if c > 1)
    out["empty_elements"] = empty
    out["extreme_coord_over_1e5"] = extreme

    fills = Counter(m.group(1).lower() for m in _FILL.finditer(svg_text))
    fills.pop("none", None)
    out["fills"] = [{"color": c, "count": n} for c, n in fills.most_common(8)]
    strokes = Counter(m.group(1).lower() for m in _STROKE.finditer(svg_text))
    strokes.pop("none", None)
    out["strokes"] = [{"color": c, "count": n} for c, n in strokes.most_common(8)]

    if not out["root_is_svg"]:
        out["warnings"].append("root element is not <svg>")
    if out["bytes"] == 0:
        out["warnings"].append("empty file")
    if out["counts"]["total_elements"] <= 1:
        out["warnings"].append("no drawable elements")
    if empty:
        out["warnings"].append(f"{empty} empty elements found")
    if out["duplicate_path_d"]:
        out["warnings"].append(f"{out['duplicate_path_d']} duplicate path geometries")
    if extreme:
        out["warnings"].append(f"{extreme} paths with extreme coordinates (>1e5)")
    if out["bytes"] > 2_000_000:
        out["warnings"].append("file larger than 2MB")
    return out


def compare_stats(ref: dict, gen: dict) -> dict:
    """Facts-only diff between two analysis dicts (reference vs generated)."""
    def _g(d, k):
        return (d or {}).get(k) or 0
    rc, gc = _g(ref.get("counts"), "paths") and ref["counts"], gen.get("counts", {})
    _ = rc  # noqa
    return {
        "ref_paths": ref.get("counts", {}).get("paths", 0),
        "gen_paths": gen.get("counts", {}).get("paths", 0),
        "ref_bytes": ref.get("bytes", 0),
        "gen_bytes": gen.get("bytes", 0),
        "ref_path_commands": ref.get("path_total_commands", 0),
        "gen_path_commands": gen.get("path_total_commands", 0),
        "ref_colors": len(ref.get("fills", [])),
        "gen_colors": len(gen.get("fills", [])),
        "gen_xml_valid": gen.get("xml_valid", False),
        "gen_warnings": gen.get("warnings", []),
    }


if __name__ == "__main__":
    import json
    text = open(sys.argv[1], encoding="utf8").read() if len(sys.argv) > 1 else sys.stdin.read()
    print(json.dumps(analyze_svg(text), indent=2))
