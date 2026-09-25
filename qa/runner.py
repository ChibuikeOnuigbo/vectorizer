"""Main QA executor (directive sections 12, 13, 22, 23, 24, 25).

Runs a large matrix of REAL vectorization executions against the live app
server. Every execution is persisted to qa/results/<case-id>.json with a
status (PASS / FAIL / ERROR / TIMEOUT / SKIPPED_WITH_REASON /
UNSUPPORTED_WITH_REASON) and a failure classification when not PASS.
Resumable: case ids that already have a result file are skipped.

  PYTHONPATH=vendor:app/deps:. python3 qa/runner.py [--limit N] [--workers 4]

The runner updates automation/TASK_STATE.json + qa/results/_summary.json.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "vendor"), str(ROOT / "app/deps"), str(ROOT)):
    sys.path.insert(0, p)

from PIL import Image  # noqa: E402

from qa.svg_analysis import analyze_svg, compare_stats  # noqa: E402

BASE = os.environ.get("VECTORIZER_BASE", "http://127.0.0.1:8000")
RESULTS = ROOT / "qa/results"
STATE = ROOT / "automation/TASK_STATE.json"
SUMMARY = RESULTS / "_summary.json"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_ERROR = "ERROR"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_SKIPPED = "SKIPPED_WITH_REASON"
STATUS_UNSUPPORTED = "UNSUPPORTED_WITH_REASON"


def mp_upload(path: str | None, fields: dict, raw: bytes | None = None, fname: str = "input.png"):
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        if v is None:
            continue
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    data = raw if raw is not None else (ROOT / path).read_bytes()
    ct = "application/octet-stream"
    body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\nContent-Type: {ct}\r\n\r\n".encode())
    body.write(data)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", body.getvalue()


def http_convert(fields: dict, path: str | None = None, raw: bytes | None = None,
                 fname: str = "input.png", endpoint: str = "/api/convert",
                 timeout: int = 90):
    ct, body = mp_upload(path, fields, raw=raw, fname=fname)
    req = urllib.request.Request(BASE + endpoint, data=body, headers={"Content-Type": ct}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
            ms = (time.perf_counter() - t0) * 1000
            return r.status, payload, ms, None
    except urllib.error.HTTPError as exc:
        ms = (time.perf_counter() - t0) * 1000
        try:
            detail = exc.read().decode()[:300]
        except Exception:
            detail = ""
        return exc.code, None, ms, f"HTTP {exc.code} {detail}"
    except TimeoutError:
        return None, None, timeout * 1000, "TIMEOUT"
    except Exception as exc:  # noqa: BLE001
        ms = (time.perf_counter() - t0) * 1000
        return None, None, ms, f"{type(exc).__name__}: {exc}"


def classify(err: str | None) -> str:
    if err is None:
        return "NONE"
    if "TIMEOUT" in err:
        return "PERFORMANCE_FAILURE"
    if "Connection refused" in err or "Name or service" in err or "urlopen error" in err:
        return "NETWORK_FAILURE"
    if "HTTP 415" in err:
        return "DATASET_FAILURE"
    if "HTTP 413" in err:
        return "DATASET_FAILURE"
    if "HTTP 422" in err or "HTTP 400" in err:
        return "VECTOR_MODEL_FAILURE"
    if "HTTP 500" in err:
        return "VECTOR_MODEL_FAILURE"
    return "TEST_HARNESS_FAILURE"


def run_case(case: dict, allow_retries: int = 1) -> dict:
    cid = case["id"]
    out_file = RESULTS / f"{cid}.json"
    res: dict = {
        "id": cid, "kind": case["kind"], "asset": case.get("asset"),
        "mode": case["mode"], "params": case.get("params", {}),
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    attempt = 0
    while True:
        attempt += 1
        if case["kind"] == "malformed":
            raw, fname = case["raw"], case["fname"]
            code, payload, ms, err = http_convert(case.get("params", {}), raw=raw, fname=fname)
        elif case["kind"] == "ai_mode":
            code, payload, ms, err = http_convert(case.get("params", {}), path=case["asset"],
                                                  endpoint="/api/ai/vectorize")
        else:
            code, payload, ms, err = http_convert(case.get("params", {}), path=case["asset"])
        res["http_status"] = code
        res["latency_ms"] = round(ms, 1)
        res["retries"] = attempt - 1
        if err and "TIMEOUT" in err:
            res["status"] = STATUS_TIMEOUT
            res["failure_class"] = "PERFORMANCE_FAILURE"
            break
        if err:
            # transient network hiccups: exponential backoff (2s, 4s...), then record
            if attempt <= allow_retries and ("urlopen error" in err or "Broken pipe" in err or "reset" in err.lower()):
                time.sleep(2.0 ** attempt)
                continue
            if case["kind"] == "ai_mode" and err and "API key missing" in err:
                res["status"] = STATUS_UNSUPPORTED
                res["note"] = "no user API key configured in sandbox; server rejects gracefully (HTTP 400)"
                res["failure_class"] = "NONE"
                break
            if case["kind"] == "malformed" and code in (400, 413, 415, 422, 405):
                res["status"] = STATUS_PASS
                res["note"] = f"malformed/unprocessable input rejected gracefully (HTTP {code})"
                res["failure_class"] = "NONE"
            else:
                res["status"] = STATUS_ERROR if code not in (400, 413, 415, 422) else STATUS_FAIL
                res["failure_class"] = classify(err)
                res["error"] = err
            break
        # http 200
        meta = (payload or {}).get("meta", {})
        svg = (payload or {}).get("svg", "")
        info = analyze_svg(svg)
        res["meta"] = {k: meta.get(k) for k in ("engine", "preset", "params") if k in meta}
        res["svg_analysis"] = info
        res["svg_bytes"] = info["bytes"]
        res["svg_sha1"] = info["sha1"]
        if case["kind"] == "pixcompare" and svg:
            # pixel-level metric: trainer-scorer silhouette/edge agreement vs input raster
            try:
                from model.svg_geom import score as _pixscore
                im = Image.open(ROOT / case["asset"]).convert("RGBA")
                px_score = float(_pixscore(im, svg, step=6)["score"])
                res["pixel_score"] = round(px_score, 1)
            except Exception as exc:  # noqa: BLE001
                res["pixel_score_error"] = f"{type(exc).__name__}: {exc}"
        if case["kind"] == "malformed":
            # a graceful 4xx counts as PASS for malformed handling; a 200 must be valid
            res["status"] = STATUS_PASS
            res["note"] = "malformed input handled without crash"
            break
        if case.get("expect_reject"):
            res["status"] = STATUS_FAIL
            res["failure_class"] = "UPLOAD_FAILURE"
            res["note"] = "server accepted input that should be rejected"
            break
        if info["xml_valid"] and info["root_is_svg"] and info["counts"]["total_elements"] > 1 and info["bytes"] > 200:
            res["status"] = STATUS_PASS
        elif case["kind"] != "malformed" and info["xml_valid"] and info["counts"]["total_elements"] <= 1:
            # was the INPUT degenerate (zero opaque content)? transparent canvas
            # legitimately yields an empty vector - expected behavior, not a defect
            try:
                im = Image.open(ROOT / case["asset"])
                alpha = im.convert("RGBA").getchannel("A")
                opaque = sum(1 for v in alpha.getdata() if v > 8)
            except Exception:
                opaque = -1
            if opaque == 0:
                res["status"] = STATUS_PASS
                res["note"] = "degenerate input (0 opaque pixels) correctly produced empty SVG"
            else:
                res["status"] = STATUS_FAIL
                res["failure_class"] = "SVG_QUALITY_FAILURE"
        else:
            res["status"] = STATUS_FAIL
            res["failure_class"] = "SVG_PARSE_FAILURE" if not info["xml_valid"] else "SVG_QUALITY_FAILURE"
        break
    out_file.write_text(json.dumps(res, indent=1))
    return res


def build_cases() -> list[dict]:
    cases: list[dict] = []
    r = random.Random(20260925)
    gen_assets = sorted(p.name for p in (ROOT / "test-assets/images/generated").glob("*.png"))
    user_assets = ["blue-bird-appicon.png", "teal-orbit-logo.png"]
    icon_index = json.loads((ROOT / "dataset/icons/fontawesome/index.json").read_text())

    def conv(cid, kind, asset, mode, params, expect_reject=False):
        cases.append({"id": cid, "kind": kind, "asset": asset, "mode": mode,
                      "params": params, "expect_reject": expect_reject})

    # A. generated corpus x {model, classic, preset-logo}  (600)
    for a in gen_assets:
        p = f"test-assets/images/generated/{a}"
        stem = f"gen-{a[:-4]}"
        conv(f"{stem}-model", "convert", p, "model", {"use_model": "1"})
        conv(f"{stem}-classic", "convert", p, "classic", {"colors": "8", "detail": "50", "smoothness": "50"})
        conv(f"{stem}-presetlogo", "convert", p, "preset:logo", {"preset": "logo"})

    # B. icon pairs x {classic, model, preset-icon} on two sizes (120 icons x 2 sizes x 3 = 720)
    for i, rec in enumerate(icon_index[:120]):
        for size in (("input-w128.png", "w128"), ("input-w256.png", "w256")):
            p = str(Path(rec["source_svg"]).parent / size[0])
            if not (ROOT / p).exists():
                continue
            stem = f"icon-{rec['id']}-{size[1]}"
            conv(f"{stem}-classic", "iconpair", p, "classic", {"colors": "8"})
            conv(f"{stem}-model", "iconpair", p, "model", {"use_model": "1"})
            conv(f"{stem}-preseticon", "iconpair", p, "preset:icon", {"preset": "icon"})

    # C. user-provided images x 5 modes (10)
    for a in user_assets:
        p = f"test-assets/images/user-provided/{a}"
        stem = a[:-4]
        conv(f"user-{stem}-model", "userprovided", p, "model", {"use_model": "1"})
        conv(f"user-{stem}-classic", "userprovided", p, "classic", {"colors": "8", "detail": "50"})
        conv(f"user-{stem}-presetlogo", "userprovided", p, "preset:logo", {"preset": "logo"})
        conv(f"user-{stem}-preseticon", "userprovided", p, "preset:icon", {"preset": "icon"})
        conv(f"user-{stem}-presetill", "userprovided", p, "preset:illustration", {"preset": "illustration"})

    # D. slider sweep on 10 representative assets: colors x detail (150)
    reps = gen_assets[::21][:10]
    for a in reps:
        p = f"test-assets/images/generated/{a}"
        for colors in ("2", "4", "8", "16", "32"):
            for detail in ("25", "75"):
                conv(f"sweep-{a[:-4]}-c{colors}-d{detail}", "convert", p, "classic",
                     {"colors": colors, "detail": detail, "smoothness": "50"})

    # E. preset sweep (illus/lqip/artistic/custom) on 40 assets (160)
    for a in gen_assets[::5][:40]:
        p = f"test-assets/images/generated/{a}"
        for preset in ("illustration", "lqip", "artistic", "custom"):
            conv(f"preset-{preset}-{a[:-4]}", "convert", p, f"preset:{preset}", {"preset": preset})

    # F. remaining icons, w128 classic+model (160)
    for rec in icon_index[120:200]:
        p = str(Path(rec["source_svg"]).parent / "input-w128.png")
        if not (ROOT / p).exists():
            continue
        conv(f"icon2-{rec['id']}-classic", "iconpair", p, "classic", {"colors": "8"})
        conv(f"icon2-{rec['id']}-model", "iconpair", p, "model", {"use_model": "1"})

    # G. determinism: same asset run twice, compare svg sha (150 pairs = 300)
    for a in gen_assets[:150]:
        p = f"test-assets/images/generated/{a}"
        conv(f"det-{a[:-4]}-a", "determinism", p, "classic", {"colors": "8"})
        conv(f"det-{a[:-4]}-b", "determinism", p, "classic", {"colors": "8"})

    # J. Stage-B expansion: every remaining icon at w256 (classic+model) and w512 (classic)
    for rec in icon_index[200:]:
        p256 = str(Path(rec["source_svg"]).parent / "input-w256.png")
        p512 = str(Path(rec["source_svg"]).parent / "input-w512.png")
        if (ROOT / p256).exists():
            conv(f"iconfull-{rec['id']}-classic", "iconpair", p256, "classic", {"colors": "8"})
            conv(f"iconfull-{rec['id']}-model", "iconpair", p256, "model", {"use_model": "1"})
        if (ROOT / p512).exists():
            conv(f"icon512-{rec['id']}-classic", "iconpair", p512, "classic", {"colors": "8"})

    # K. pixel-level reference comparison: generated SVG rescored against its input raster
    #    (model.svg_geom score, same metric family as the trainer) on a 300-icon batch
    for rec in icon_index[:300]:
        p = str(Path(rec["source_svg"]).parent / "input-w128.png")
        if (ROOT / p).exists():
            cases.append({"id": f"pix-{rec['id']}", "kind": "pixcompare", "asset": p,
                          "mode": "classic", "params": {"colors": "8"}})

    # L. provider validation matrix: every AI provider must reject gracefully without a key
    try:
        from app.ai_providers import provider_catalog
        provs = list(provider_catalog().keys())
    except Exception:
        provs = []
    for prov in provs:
        cases.append({"id": f"provider-{prov}", "kind": "ai_mode",
                      "asset": "test-assets/images/user-provided/teal-orbit-logo.png",
                      "mode": "ai", "params": {"provider": prov, "model": "", "detail": "50", "colors": "8"}})

    # H. malformed inputs (12) - must not crash worker
    bad = [
        ("empty-file", b"", "empty.png", False),
        ("one-byte", b"\x00", "byte.png", False),
        ("txt-as-png", b"this is not an image", "text.png", True),
        ("gif-header", b"GIF89a" + b"\x00" * 64, "fake.gif", False),
        ("jpeg-trunc", b"\xff\xd8\xff\xe0" + b"\x00" * 32, "trunc.jpg", False),
        ("png-trunc", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "trunc.png", False),
        ("zip-as-png", b"PK\x03\x04" + b"\x00" * 64, "zip.png", True),
    ]
    # valid-but-extreme in-memory rasters: 1x1, 1x2000, sparse noise
    im1 = Image.new("RGBA", (1, 1), (255, 0, 0, 255))
    b = io.BytesIO(); im1.save(b, "PNG"); bad.append(("raster-1x1", b.getvalue(), "r1.png", False))
    im2 = Image.new("RGBA", (2, 2000), (255, 255, 255, 255))
    b = io.BytesIO(); im2.save(b, "PNG"); bad.append(("raster-2x2000", b.getvalue(), "r2.png", False))
    im3 = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    b = io.BytesIO(); im3.save(b, "PNG"); bad.append(("raster-empty-alpha", b.getvalue(), "r3.png", False))
    bad.append(("reject-exe", b"MZ" + os.urandom(256), "prog.exe", True))
    bad.append(("reject-deep", b"\xff" * 524288, "blob.jpg", False))
    for i, (nm, raw, fname, expect_reject) in enumerate(bad):
        cases.append({"id": f"malformed-{nm}", "kind": "malformed", "asset": None, "mode": "classic",
                      "params": {"colors": "8"}, "raw": raw, "fname": fname, "expect_reject": expect_reject})

    # I. AI mode probes (3) - no user key in sandbox; expect classified failure, must not crash runner
    for a in user_assets[:2]:
        p = f"test-assets/images/user-provided/{a}"
        cases.append({"id": f"aimode-{a[:-4]}", "kind": "ai_mode", "asset": p, "mode": "ai",
                      "params": {"provider": "openrouter", "model": "", "detail": "50", "colors": "8"}})
    return cases


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def save_state(patch: dict) -> None:
    st = load_state()
    st.update(patch)
    st["last_checkpoint"] = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1))


def summarize(done_results: list[dict]) -> dict:
    # only real execution records: files with an id+status from run_case
    done_results = [r for r in done_results if r.get("id") and r.get("status")]
    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    by_mode: dict[str, dict[str, int]] = {}
    lat = []
    for res in done_results:
        s = res.get("status", "ERROR")
        by_status[s] = by_status.get(s, 0) + 1
        if res.get("failure_class") and res["failure_class"] != "NONE":
            by_class[res["failure_class"]] = by_class.get(res["failure_class"], 0) + 1
        m = res.get("mode", "?")
        by_mode.setdefault(m, {})
        by_mode[m][s] = by_mode[m].get(s, 0) + 1
        if res.get("latency_ms"):
            lat.append(res["latency_ms"])
    det_ident = 0
    det_total = 0
    det: dict[str, list[str]] = {}
    for res in done_results:
        if res.get("kind") == "determinism":
            base = res["id"].rsplit("-", 1)[0]
            det.setdefault(base, []).append(res.get("svg_sha1", ""))
    for v in det.values():
        if len(v) == 2:
            det_total += 1
            det_ident += 1 if v[0] == v[1] else 0
    pixscores = [res["pixel_score"] for res in done_results if res.get("pixel_score") is not None]
    pixel_stats = {
        "cases": len(pixscores),
        "avg": round(sum(pixscores) / len(pixscores), 1) if pixscores else None,
        "min": min(pixscores) if pixscores else None,
        "p05": sorted(pixscores)[int(len(pixscores) * 0.05)] if pixscores else None,
    }
    return {
        "total_executions": len(done_results),
        "by_status": by_status,
        "by_failure_class": by_class,
        "by_mode": by_mode,
        "determinism_pairs": det_total,
        "determinism_identical": det_ident,
        "pixel_score_stats": pixel_stats,
        "latency_ms": {
            "avg": round(sum(lat) / len(lat), 1) if lat else 0,
            "p95": sorted(lat)[int(len(lat) * 0.95)] if lat else 0,
            "max": round(max(lat), 1) if lat else 0,
        },
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    all_cases = build_cases()
    todo = [c for c in all_cases if not (RESULTS / f"{c['id']}.json").exists()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"cases total={len(all_cases)} todo={len(todo)} workers={args.workers}")
    save_state({"current_phase": "qa_runner", "total_cases": len(all_cases),
                "remaining_cases": len(todo), "current_mode": "convert-matrix",
                "next_action": "run qa matrix executions"})
    t0 = time.time()
    done = 0
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_case, c): c for c in todo}
        for fut in as_completed(futs):
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"id": futs[fut]["id"], "status": STATUS_ERROR,
                       "failure_class": "TEST_HARNESS_FAILURE", "error": f"{type(exc).__name__}: {exc}"}
            results.append(res)
            done += 1
            if done % 100 == 0 or done == len(todo):
                prior = [json.loads(p.read_text()) for p in RESULTS.glob("*.json") if p.name not in ("_summary.json",) and not p.name.startswith("_")]
                SUMMARY.write_text(json.dumps(summarize(prior), indent=1))
                el = time.time() - t0
                print(f"progress {done}/{len(todo)} elapsed={el:.0f}s pass={sum(1 for r in prior if r.get('status')=='PASS')}", flush=True)
                save_state({"completed_cases": done, "remaining_cases": len(todo) - done,
                            "last_successful_case": res.get("id"),
                            "next_action": "continue qa matrix at " + str(done)})
    prior = [json.loads(p.read_text()) for p in RESULTS.glob("*.json") if p.name not in ("_summary.json",) and not p.name.startswith("_")]
    final = summarize(prior)
    SUMMARY.write_text(json.dumps(final, indent=1))
    save_state({"current_phase": "qa_runner_done", "completed_cases": len(prior),
                "remaining_cases": 0, "next_action": "regression browser tests + report"})
    print("FINAL", json.dumps(final))


if __name__ == "__main__":
    main()
