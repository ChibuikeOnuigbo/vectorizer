"""100-image proof report: real input PNG -> model output SVG -> classic output SVG.

Generates a static HTML gallery (app/static/test-report.html) the user opens
in the browser, checks each pair personally, and clicks Good/Rubbish per row.
Every click POSTs to /api/manual/verdict which APPENDS the verdict to
model_data_snapshot/verdicts.jsonl (committed to git = wipe-proof) so the
verdicts feed back into the forever training data.

The report is reproducible: fresh seeds, never in any training chunk.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "model" / "data"
TEST_DIR = DATA / "test100"
ART = ROOT / "app" / "static" / "testreport"
OUT_HTML = ROOT / "app" / "static" / "test-report.html"
VERDICTS = ROOT / "model_data_snapshot" / "verdicts.jsonl"
REPORT_JSON = ROOT / "app" / "static" / "testreport" / "report.json"

TEST_SEED_BASE = 10_001  # never collides with training seeds (<10_000)


def gen_test_images(n: int = 100) -> list[Path]:
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    from model.make_logos import make_logo
    from model.gen_text_no_bg import gen_one
    import random
    files = []
    rng = random.Random(TEST_SEED_BASE)
    for i in range(n):
        out = TEST_DIR / f"test_{i:03d}.png"
        if out.exists():
            files.append(out)
            continue
        kind = i % 5
        no_text = kind in (0, 1, 2)
        try:
            if kind in (0, 1, 3):
                img = make_logo(rng, i, no_text=no_text)
                img = _maybe_degrade(img, rng, hard=(kind == 1))
            else:
                img = gen_one(TEST_SEED_BASE + i, rng.randint(1, 10**7))
                if not isinstance(img, Image.Image):
                    raise ValueError("bad img")
                if kind == 2:
                    img = _maybe_degrade(img, rng, hard=False)
                if kind == 4:
                    img = _maybe_degrade(img, rng, hard=True)
        except Exception:
            # fallback: simple deterministic geometric logo drawn here
            img = _fallback_logo(i, rng, no_text=no_text)
            if kind in (1, 4):
                img = _maybe_degrade(img, rng, hard=True)
        img.save(out)
        files.append(out)
    return files


def _maybe_degrade(img: Image.Image, rng, hard: bool) -> Image.Image:
    if rng.random() < 0.25:
        img = ImageOps.mirror(img)
    r = rng.uniform(2.0, 6.0) if hard else rng.uniform(0.6, 2.2)
    img = img.filter(ImageFilter.GaussianBlur(r))
    if hard and rng.random() < 0.6:
        import io
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=rng.randint(18, 45))
        buf.seek(0)
        img = Image.open(buf).convert("RGBA")
    return img


def _fallback_logo(i, rng, no_text) -> Image.Image:
    from PIL import ImageDraw
    W = 256
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pal = [(225, 60, 80, 255), (30, 120, 220, 255), (240, 200, 60, 255),
           (40, 180, 110, 255), (90, 60, 200, 255)]
    c1, c2 = rng.sample(pal, 2)
    xs = rng.randint(40, 90)
    d.rounded_rectangle((xs, xs, W - xs, W - xs), 24, fill=c1)
    kind = rng.randint(0, 3)
    if kind == 0:
        d.ellipse((W//2 - 45, W//2 - 45, W//2 + 45, W//2 + 45), fill=c2)
    elif kind == 1:
        d.polygon([(W//2, 70), (W-80, W-70), (80, W-70)], fill=c2)
    elif kind == 2:
        d.rectangle((110, 60, 146, 196), fill=c2)
        d.rectangle((60, 110, 196, 146), fill=c2)
    else:
        d.arc((60, 60, W-60, W-60), 200, 340, fill=c2, width=26)
    if not no_text:
        d.text((W//2 - 40, W - 66), "XEN", fill=(20, 20, 30, 255))
    return img


_ORT_SESSION = None


def _model_params(features: np.ndarray) -> dict:
    global _ORT_SESSION
    from model.features import targets_to_params
    try:
        import onnxruntime as ort
        if _ORT_SESSION is None:
            _ORT_SESSION = ort.InferenceSession(
                str(ROOT / "app" / "static" / "model" / "params.onnx"),
                providers=["CPUExecutionProvider"])
        out = _ORT_SESSION.run(None, {"x": features[None].astype(np.float32)})
        return targets_to_params(out[0][0])
    except Exception:
        # numpy fallback when a fresh params.npz exists (forever checkpoint)
        from model.train import forward  # type: ignore
        z = np.load(ROOT / "model" / "out" / "params.npz")
        net = [z[k] for k in ("W1", "b1", "W2", "b2", "W3", "b3", "W4", "b4")]
        y, _ = forward(net, features[None], training=False)
        return targets_to_params(y[0])


def build_report(n: int = 100) -> dict:
    t0 = time.time()
    from model.features import image_features
    from app.convert import analyze, trace_with, _pick_best_preset, vectorize
    from model.svg_geom import score
    files = gen_test_images(n)
    ART.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, p in enumerate(files):
        img = Image.open(p).convert("RGBA")
        feats = image_features(img)
        a = analyze(img)
        # 1) model path (same as the web Smart Model button)
        m_svg, m_sc = None, None
        m_err = None
        try:
            params = _model_params(feats)
            m_svg = trace_with(a, params)
            m_sc = score(img, m_svg)
        except Exception as e:
            m_err = str(e)[:120]
        # 2) classic best-tier heuristic
        try:
            c_params = _pick_best_preset(analyze(img))
            a2 = analyze(img)
            c_svg = trace_with(a2, c_params)
            c_sc = score(img, c_svg)
        except Exception:
            c_svg, c_sc = None, None
        (ART / f"in_{i:03d}.png").write_bytes(p.read_bytes())
        if m_svg:
            (ART / f"m_{i:03d}.svg").write_text(m_svg)
        if c_svg:
            (ART / f"c_{i:03d}.svg").write_text(c_svg)
        rows.append({
            "i": i, "name": p.name, "file": p.name,
            "m_score": round(m_sc["score"], 1) if m_sc else None,
            "m_paths": m_sc["paths"] if m_sc else None,
            "m_kb": round(len(m_svg.encode())/1024, 1) if m_svg else None,
            "c_score": round(c_sc["score"], 1) if c_sc else None,
            "c_paths": c_sc["paths"] if c_sc else None,
            "c_kb": round(len(c_svg.encode())/1024, 1) if c_svg else None,
            "model_err": m_err,
        })
        if (i + 1) % 20 == 0 or i == len(files) - 1:
            print(f"[report {i+1}/{len(files)}] {time.time()-t0:.0f}s", flush=True)
    summary = {
        "images": len(rows),
        "sec": round(time.time() - t0, 1),
        "m_avg": round(np.mean([r["m_score"] for r in rows if r["m_score"] is not None]), 1),
        "c_avg": round(np.mean([r["c_score"] for r in rows if r["c_score"] is not None]), 1),
        "m_best": max((r["m_score"] or 0) for r in rows),
        "m_worst": min((r["m_score"] or 0) for r in rows),
        "rows": rows,
        "verdicts": load_verdict_map(),
    }
    REPORT_JSON.write_text(json.dumps(summary, indent=1))
    write_html(summary)
    return summary


def load_verdict_map() -> dict:
    out = {}
    if VERDICTS.exists():
        for line in VERDICTS.read_text().strip().splitlines():
            try:
                v = json.loads(line)
                out[f"{v.get('i')}_{v.get('method')}"] = v.get("verdict")
            except Exception:
                pass
    return out


# ---------------------------------------------------------------- HTML
CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: #0c0f14; color: #e8ecf4; }
.head { position: sticky; top: 0; z-index: 50; background: rgba(10,12,17,.92); backdrop-filter: blur(8px); border-bottom: 1px solid #1d2532; padding: 14px 20px; display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.head h1 { font-size: 17px; margin: 0; }
.head .stat { font-size: 13px; color: #9aa7bd; }
.head .stat b { color: #e8ecf4; }
.pill { background: #16202e; border: 1px solid #26344a; border-radius: 999px; padding: 4px 12px; font-size: 12.5px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 16px; }
.row { background: #12161d; border: 1px solid #1d2532; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.row-head { display: flex; justify-content: space-between; font-size: 12.5px; color: #9aa7bd; }
.cols { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.col { display: flex; flex-direction: column; gap: 6px; align-items: center; }
.col label { font-size: 11.5px; color: #7f8da3; }
.imgbox { background: repeating-conic-gradient(#1a2230 0 25%, #141a24 0 50%) 0 0/16px 16px; border-radius: 8px; border: 1px solid #1d2532; width: 100%; aspect-ratio: 1; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.imgbox img { max-width: 96%; max-height: 96%; object-fit: contain; }
.meta { font-size: 11px; color: #7f8da3; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
.verdicts { display: flex; gap: 6px; }
.vbtn { border: 1px solid #2a3a55; background: #141b26; color: #c8d4e8; font-size: 12px; padding: 5px 10px; border-radius: 7px; cursor: pointer; }
.vbtn:hover { border-color: #4f8cff; }
.vbtn.good.active { background: #12351f; border-color: #2f9749; color: #7ae0a1; }
.vbtn.bad.active { background: #3a1520; border-color: #d04868; color: #ff9db3; }
.foot { padding: 20px; color: #9aa7bd; font-size: 13px; }
.toast { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%); background: #16202e; border: 1px solid #2a3a55; color: #e8ecf4; padding: 9px 16px; border-radius: 10px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity .2s; z-index: 60; }
.toast.show { opacity: 1; }
@media (max-width: 980px) { .grid { grid-template-columns: 1fr; } }
"""
JS = """
async function vote(btn, i, method, verdict) {
  const was = btn.classList.contains("active");
  btn.parentElement.querySelectorAll(".vbtn").forEach(b => b.classList.remove("active"));
  if (!was) btn.classList.add("active");
  const rows = btn.closest(".row");
  const extra = rows ? rows.dataset.extra || "{}" : "{}";
  try {
    const res = await fetch("/api/manual/verdict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ i, method, verdict: was ? "none" : verdict, meta: JSON.parse(extra) })
    });
    const d = await res.json();
    const n = document.getElementById("count");
    if (n) n.textContent = d.total;
    toast("saved " + verdict + " for #" + i + " (" + method + "), total " + d.total);
  } catch (e) { toast("failed " + e.message); }
  const done = document.getElementById("done");
  if (done) done.textContent = document.querySelectorAll(".vbtn.active").length;
}
function toast(msg) {
  let t = document.getElementById("toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 1800);
}
"""


def write_html(summary: dict):
    rows_html = []
    for r in summary["rows"]:
        vm = summary["verdicts"].get(f"{r['i']}_model", "")
        vc = summary["verdicts"].get(f"{r['i']}_classic", "")
        m_active_g = "good active" if vm == "good" else "good"
        m_active_b = "bad active" if vm == "bad" else "bad"
        c_active_g = "good active" if vc == "good" else "good"
        c_active_b = "bad active" if vc == "bad" else "bad"
        extra = json.dumps({"m_score": r["m_score"], "c_score": r["c_score"]}).replace('"', "&quot;")
        model_err = f"<div class='meta' style='color:#ff9db3'>model error: {r['model_err']}</div>" if r.get("model_err") else ""
        m_img = f'<img src="/static/testreport/m_{r["i"]:03d}.svg">' if Path(ART / f"m_{r['i']:03d}.svg").exists() else "<div class='meta'>no output</div>"
        c_img = f'<img src="/static/testreport/c_{r["i"]:03d}.svg">' if Path(ART / f"c_{r['i']:03d}.svg").exists() else "<div class='meta'>no output</div>"
        rows_html.append(f"""
<div class="row" data-extra="{extra}">
  <div class="row-head"><span>#{r['i']:02d} · {r['file']}</span>
    <span>model <b style="color:#e8ecf4">{r['m_score']}</b> · classic <b style="color:#e8ecf4">{r['c_score']}</b></span></div>
  <div class="cols">
    <div class="col"><label>input raster</label><div class="imgbox"><img src="/static/testreport/in_{r['i']:03d}.png"></div></div>
    <div class="col"><label>model output (Smart Model)</label><div class="imgbox">{m_img}</div>
      <div class="meta">{r['m_score']} pts · {r['m_paths']} paths · {r['m_kb']} KB</div>{model_err}
      <div class="verdicts">
        <button class="vbtn {m_active_g}" onclick="vote(this,{r['i']},'model','good')">Good</button>
        <button class="vbtn {m_active_b}" onclick="vote(this,{r['i']},'model','bad')">Rubbish</button>
      </div></div>
    <div class="col"><label>classic output (No model)</label><div class="imgbox">{c_img}</div>
      <div class="meta">{r['c_score']} pts · {r['c_paths']} paths · {r['c_kb']} KB</div>
      <div class="verdicts">
        <button class="vbtn {c_active_g}" onclick="vote(this,{r['i']},'classic','good')">Good</button>
        <button class="vbtn {c_active_b}" onclick="vote(this,{r['i']},'classic','bad')">Rubbish</button>
      </div></div>
  </div>
</div>""")
    n_verdicts = len(summary.get("verdicts", {}))
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vectorizer proof report — {summary['images']} images in/out</title><style>{CSS}</style></head>
<body>
<div class="head">
  <h1>Proof report: {summary['images']} test images — input / model / classic</h1>
  <span class="pill">model avg <b>{summary['m_avg']}</b> pts</span>
  <span class="pill">classic avg <b>{summary['c_avg']}</b> pts</span>
  <span class="pill">best/worst model {summary['m_best']} / {summary['m_worst']}</span>
  <span class="pill">built in {summary['sec']}s</span>
  <span class="pill">verdicts saved <b id="count">{n_verdicts}</b></span>
  <span class="pill">buttons clicked <b id="done">—</b></span>
  <span class="stat">Click Good/Rubbish per row. Every click is APPENDED to
  <code>model_data_snapshot/verdicts.jsonl</code> (committed to git). You can
  also reply in chat with your notes and they get merged the same way.</span>
</div>
<div class="grid">{''.join(rows_html)}</div>
<div class="foot">Fresh seeds, never used in training chunks. Scores are the composite coverage/precision/color metric (0-100, 100 = perfect).
Rebuild: POST /api/test/rebuild. Data feeds the forever training program.</div>
<script>{JS}</script>
</body></html>"""
    OUT_HTML.write_text(html)


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    s = build_report(n)
    print("model avg", s["m_avg"], "| classic avg", s["c_avg"], "| built", s["sec"], "s")
    print("html ->", OUT_HTML)
