#!/usr/bin/env python3
"""Generate model_result/index.html — a browsable side-by-side gallery of the
folder's fresh model results (input vs output SVG, honest strict scores).
Reads model_result/index.json (from model_result_build.py) and copies each
source image into model_result/inputs/ so the page is fully self-contained.
Usage: PYTHONPATH=vendor:app/deps:. python3 scripts/model_result_gallery.py
"""
import html, json, shutil, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "model_result"

CSS = """
body{font-family:system-ui,Arial,sans-serif;margin:24px;background:#0f1115;color:#e8eaed}
h1{font-size:20px} .sub{color:#9aa0a6;font-size:13px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}
.card{background:#171a21;border:1px solid #2a2f3a;border-radius:10px;padding:12px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.box{background:#fff;border-radius:8px;min-height:140px;display:flex;align-items:center;justify-content:center;overflow:hidden}
.box img{max-width:100%;max-height:180px}
.box.check{background-image:linear-gradient(45deg,#ddd 25%,transparent 25%,transparent 75%,#ddd 75%),linear-gradient(45deg,#ddd 25%,transparent 25%,transparent 75%,#ddd 75%);background-size:16px 16px;background-position:0 0,8px 8px}
.meta{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:13px}
.badge{font-weight:700;padding:3px 10px;border-radius:12px;font-size:12px}
.PASS{background:#134e2e;color:#9ff5c0}.WEAK{background:#5c4408;color:#ffd98a}.FAIL{background:#5c1616;color:#ffb4b4}
small{color:#9aa0a6;display:block;margin-top:4px;font-size:11px}
a{color:#8ab4f8;text-decoration:none}
.name{font-size:12px;color:#c9cdd4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px}
"""


def ladder_cards() -> tuple[str, list[dict]]:
    """Teal-lineage ladder: every engine route on the uploaded image, scored
    pixel-for-pixel against the user-approved reference render. Purely visual
    comparison - the training target made visible."""
    import sys
    sys.path.insert(0, str(ROOT / "qa"))
    from app.convert import analyze, trace_with
    from PIL import Image
    from similarity_audit import audit  # noqa: E402

    inp = ROOT / "test-assets/images/user-provided/teal-orbit-logo.png"
    im = Image.open(inp).convert("RGBA")
    a = analyze(im)
    ref_txt = (OUT / "absolute_test_svg.svg").read_text()
    variants = [
        ("reference (target)", "absolute_test_svg.svg", None),
        ("binary-alpha-mono (auto route)", None, {}),
        ("alpha-tone-stack (multi-tone engine)", None, {"engine": "alpha-tone-stack"}),
        ("color-cutout (classic engine)", None, {"engine": "color-cutout"}),
    ]
    cards, meta = [], []
    for label, svg_file, params in variants:
        svg = ref_txt if svg_file else trace_with(a, params)
        vs_in = audit(str(inp), {"x": svg}, save_composite=False)["engines"]["x"][
            "visual_similarity_pct"]
        W, H = im.size
        # closeness to the reference >render< (still pixels-only)
        from model_result_build import ref_similarity  # noqa: E402
        vs_ref = ref_similarity(svg, ref_txt, W, H)
        if not svg_file:
            svg_file = f"ladder-{label.split()[0].split('(')[0]}.svg".replace('/', '')
            (OUT / svg_file).write_text(svg)
        vs = vs_ref if label != "reference (target)" else 100.0
        meta.append({"label": label, "vs_input": vs_in, "vs_reference": vs_ref, "file": svg_file})
        tgt = ' <span style="color:#9ff5c0">(training target)</span>' if vs_ref == 100.0 else ""
        cards.append(f'''<div class="card">
<div class="pair"><div class="box check"><img loading="lazy" src="inputs/teal-orbit-logo.png"></div>
<div class="box check"><img loading="lazy" src="{svg_file}"></div></div>
<div class="meta"><span class="badge {'PASS' if vs_ref >= 85 else ('WEAK' if vs_ref >= 70 else 'FAIL')}">
{label.split('(')[0].strip()}{' ' if vs_ref < 85 else ''}vs-ref {vs_ref}%</span></div>
<small>{label}{tgt} · vs input (strict): {vs_in}%</small></div>''')
    return "\n".join(cards), meta


def main() -> None:
    idx = json.loads((OUT / "index.json").read_text())
    (OUT / "inputs").mkdir(exist_ok=True)
    cards = []
    n_pass = n_weak = n_fail = 0
    for e in idx["entries"]:
        svg_f = e.get("svg")
        if e.get("status") not in ("OK",) and e.get("id") != "mr-000":
            continue
        if e.get("id") == "mr-000":
            verdict, pct = "PASS", e.get("strict_similarity_to_input_pct")
            n_pass += 1
            input_rel = None
            title = "REFERENCE (approved by you)"
        else:
            verdict, pct = e["strict_verdict"], e["strict_similarity_pct"]
            n_pass += verdict == "PASS"; n_weak += verdict == "WEAK"; n_fail += verdict == "FAIL"
            src = OUT.parent / e["source"]
            th = "inputs/" + src.name
            shutil.copy2(src, OUT / th)
            input_rel = th
            title = Path(e["source"]).name
        extra = ""
        if "similarity_to_reference_pct" in e:
            extra = f' · vs reference <b>{e["similarity_to_reference_pct"]}%</b>'
        ch = e.get("channels") or {}
        chan = (f'mae {ch.get("mae")}, ssim {ch.get("ssim12")}, iou {ch.get("silhouette_iou")}'
                if ch else "")
        engine = e.get("engine", "")
        left = (f'<div class="box check"><img loading="lazy" src="{input_rel}"></div>' if input_rel
                else '<div class="box check"><img loading="lazy" src="' + svg_f + '" alt=""></div>')
        cards.append(f'''<div class="card" id="{e["id"]}">
<div class="pair">{left}<div class="box check"><img loading="lazy" src="{svg_f}"></div></div>
<div class="meta"><span class="badge {verdict}">{verdict} {pct}%</span>
<span class="name" title="{html.escape(title)}">{e["id"]} · {html.escape(title)}</span></div>
<small>left: input&nbsp;·&nbsp;right: model SVG &nbsp;|&nbsp; engine: {engine or "reference"}{extra}<br>{chan}</small>
</div>''')

    ladder_html, ladder_meta = ladder_cards()
    idx["ladder"] = ladder_meta
    (OUT / "index.json").write_text(json.dumps(idx, indent=1))
    page = f"""<!doctype html><meta charset="utf-8">
<title>model_result — fresh model outputs (strict-audited)</title>
<style>{CSS}
.fit{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-bottom:28px}}</style>
<h1>model_result/ — {n_pass} PASS · {n_weak} WEAK · {n_fail} FAIL over {len(cards)} rows</h1>
<div class="sub">Generated {idx.get("generated_utc","?")} · refreshed against live code ·
strict audit authority qa/similarity_audit.py ·
<a href="index.json">index.json</a> · <a href="README.md">README</a></div>
<h2 style="font-size:15px;color:#c9cdd4">Teal-orbit ladder — engines vs your approved reference</h2>
<div class="fit">{ladder_html}</div>
<h2 style="font-size:15px;color:#c9cdd4">Full sweep (every test asset, model mode)</h2>
<div class="grid">{''.join(cards)}</div>
"""
    (OUT / "index.html").write_text(page)
    print(f"index.html written: {len(cards)} cards -> {OUT}/index.html")


if __name__ == "__main__":
    main()
