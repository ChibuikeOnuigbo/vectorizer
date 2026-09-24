"""FastAPI server: serves the single-page app and the /api/convert endpoint + manual training & strict vetting."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .convert import vectorize

log = logging.getLogger("vectorizer")

BASE = Path(__file__).parent
STATIC = BASE / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

app = FastAPI(title="Vectorizer")

# CORS for preview — allow all origins for Arena preview proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _clamped_int(value: str | None, lo: int, hi: int) -> int | None:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, v))


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    use_model: str | None = Form(None),
    profile: str | None = Form(None),
    color_precision: str | None = Form(None),
    layer_difference: str | None = Form(None),
    filter_speckle: str | None = Form(None),
    max_iterations: str | None = Form(None),
    corner_threshold: str | None = Form(None),
    preset: str | None = Form(None),
    colors: str | None = Form(None),
    detail: str | None = Form(None),
    smoothness: str | None = Form(None),
    enhance: str | None = Form(None),
    engine: str | None = Form(None),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large max 20 MB")
    name = (file.filename or "image").lower()
    if not any(name.endswith(e) for e in ALLOWED_EXT):
        raise HTTPException(415, "Unsupported file type Use PNG JPG WebP GIF BMP")

    params = None
    # best tier method: if preset given use it, else if use_model 1 use model params, else classic
    if preset and preset in ("logo", "icon", "illustration", "lqip", "artistic", "custom"):
        params = {"preset": preset}
        # allow override with explicit params
        if profile in ("flat", "photo"):
            params["profile"] = profile
        for key, raw, lo, hi in (
            ("color_precision", color_precision, 1, 8),
            ("layer_difference", layer_difference, 6, 40),
            ("filter_speckle", filter_speckle, 1, 8),
            ("max_iterations", max_iterations, 8, 48),
            ("corner_threshold", corner_threshold, 10, 110),
        ):
            v = _clamped_int(raw, lo, hi)
            if v is not None:
                params[key] = v
    elif use_model == "1":
        params = {}
        if profile in ("flat", "photo"):
            params["profile"] = profile
        for key, raw, lo, hi in (
            ("color_precision", color_precision, 1, 8),
            ("layer_difference", layer_difference, 6, 40),
            ("filter_speckle", filter_speckle, 1, 8),
            ("max_iterations", max_iterations, 8, 48),
            ("corner_threshold", corner_threshold, 10, 110),
        ):
            v = _clamped_int(raw, lo, hi)
            if v is not None:
                params[key] = v
        if not params:
            params = None
    else:
        # classic best tier without model: pick preset if given else let vectorize pick best tier
        if preset:
            params = {"preset": preset}
        else:
            params = None

    mode_opts = {
        "colors": _clamped_int(colors, 2, 128),
        "detail": _clamped_int(detail, 0, 100),
        "smoothness": _clamped_int(smoothness, 0, 100),
        "enhance": enhance == "1",
        "engine": engine if engine == "best" else None,
    }
    try:
        return JSONResponse(vectorize(data, params, mode_opts))
    except Exception as exc:  # noqa: BLE001
        log.exception("conversion failed")
        raise HTTPException(422, f"Could not vectorize this image {exc}") from exc


# ============ AI ASSIST (user's own API key, see research notes) ============
from .ai_providers import ai_vectorize, provider_catalog  # noqa: E402


@app.get("/api/ai/providers")
def ai_providers():
    return {"providers": provider_catalog()}


@app.post("/api/ai/vectorize")
async def ai_vectorize_endpoint(
    request: Request,
    file: UploadFile = File(...),
    provider: str = Form("openrouter"),
    model: str | None = Form(None),
    detail: str | None = Form(None),
    colors: str | None = Form(None),
):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large max 20 MB")
    name = (file.filename or "image").lower()
    if not any(name.endswith(e) for e in ALLOWED_EXT):
        raise HTTPException(415, "Unsupported file type Use PNG JPG WebP GIF BMP")
    key = request.headers.get("x-ai-key", "")
    try:
        return JSONResponse(ai_vectorize(
            data, provider=provider, model=model or "",
            key=key, detail=detail or "auto",
            colors=_clamped_int(colors, 2, 128)))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("ai vectorize failed")
        raise HTTPException(500, f"AI vectorize failed {exc}") from exc


app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ============ MANUAL TRAINING & DEBUG VETTING (very strict) ============
MANUAL_BASE = Path(__file__).parent.parent / "model" / "data" / "manual"
MANUAL_IMAGES = MANUAL_BASE / "images"
MANUAL_RESULTS = MANUAL_BASE / "results"
MANUAL_IMAGES.mkdir(parents=True, exist_ok=True)
MANUAL_RESULTS.mkdir(parents=True, exist_ok=True)

@app.post("/api/manual/images")
async def manual_upload_images(files: list[UploadFile] = File(...)):
    saved = []
    for file in files:
        data = await file.read()
        if not data or len(data) > MAX_UPLOAD_BYTES:
            continue
        name = (file.filename or f"img_{len(saved)}.png").lower()
        safe = "".join(c for c in name if c.isalnum() or c in "._-")[-100:]
        if not safe:
            safe = f"img_{len(saved)}.png"
        dest = MANUAL_IMAGES / safe
        if dest.exists():
            dest = MANUAL_IMAGES / f"{int(time.time()*1000)}_{safe}"
        dest.write_bytes(data)
        saved.append(safe)
    return {"saved": len(saved), "files": saved, "total_images": len(list(MANUAL_IMAGES.glob("*"))), "total_results": len(list(MANUAL_RESULTS.glob("*")))}

@app.post("/api/manual/results")
async def manual_upload_results(files: list[UploadFile] = File(...)):
    saved = []
    for file in files:
        data = await file.read()
        if not data or len(data) > MAX_UPLOAD_BYTES:
            continue
        name = (file.filename or f"result_{len(saved)}.svg").lower()
        safe = "".join(c for c in name if c.isalnum() or c in "._-")[-100:]
        if not safe:
            safe = f"result_{len(saved)}.svg"
        dest = MANUAL_RESULTS / safe
        if dest.exists():
            dest = MANUAL_RESULTS / f"{int(time.time()*1000)}_{safe}"
        dest.write_bytes(data)
        saved.append(safe)
    return {"saved": len(saved), "files": saved, "total_images": len(list(MANUAL_IMAGES.glob("*"))), "total_results": len(list(MANUAL_RESULTS.glob("*")))}

@app.get("/api/manual/status")
def manual_status():
    images = sorted([p.name for p in MANUAL_IMAGES.glob("*")])[-100:]
    results = sorted([p.name for p in MANUAL_RESULTS.glob("*")])[-100:]
    cont_log = Path(__file__).parent.parent / "model" / "out" / "continuous_log.jsonl"
    last_train = None
    if cont_log.exists():
        try:
            lines = cont_log.read_text().strip().splitlines()[-5:]
            import json as _js
            last_train = [_js.loads(l) for l in lines]
        except Exception:
            pass
    return {
        "total_images": len(list(MANUAL_IMAGES.glob("*"))),
        "total_results": len(list(MANUAL_RESULTS.glob("*"))),
        "images_sample": images,
        "results_sample": results,
        "last_training": last_train,
        "model_exists": (Path(__file__).parent.parent / "model" / "out" / "params.npz").exists(),
        "onnx_size": (STATIC / "model" / "params.onnx").stat().st_size if (STATIC / "model" / "params.onnx").exists() else 0,
        "manual_base": str(MANUAL_BASE),
        "note": "Section 1: upload as many images as possible, Section 2: upload results for those images, site collects and trains"
    }

@app.post("/api/manual/train")
def manual_train():
    import subprocess, sys, os
    ROOT = Path(__file__).parent.parent
    try:
        cmd = [sys.executable, "-m", "model.train", "--dataset", str(ROOT / "model" / "data" / "dataset.json"), "--out", str(ROOT / "model" / "out"), "--rounds", "1", "--val-frac", "0.15", "--seed", "1"]
        env = {**os.environ, "PYTHONPATH": f"vendor:{ROOT}"}
        subprocess.Popen(cmd, cwd=str(ROOT), env=env)
        return {"ok": True, "msg": "Training started in background (1 round), check /api/manual/status, ONNX will be updated, manual images will be included next dataset rebuild"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/debug/vet")
def debug_vet(limit: int = 20):
    """Vet the model very strictly — scan result and grade strictly for debug."""
    import numpy as np
    from PIL import Image
    import json as js
    ROOT = Path(__file__).parent.parent
    try:
        from model.train import init_net, forward
        from model.features import targets_to_params
        from app.convert import analyze, trace_with
        from model.svg_geom import score
    except Exception as e:
        raise HTTPException(500, f"Failed to import model: {e}")

    npz_path = ROOT / "model" / "out" / "params.npz"
    if not npz_path.exists():
        return {"error": "model/out/params.npz not found, train first", "strict": True}

    try:
        npz = np.load(npz_path)
        W1, b1, W2, b2, W3, b3 = npz["W1"], npz["b1"], npz["W2"], npz["b2"], npz["W3"], npz["b3"]
        net = [W1, b1, W2, b2, W3, b3]
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {e}")

    dataset_path = ROOT / "model" / "data" / "dataset.json"
    if not dataset_path.exists():
        return {"error": "dataset.json not found", "strict": True}

    records = js.loads(dataset_path.read_text())
    sample = records[:limit]

    results = []
    total_score = 0
    strict_pass = 0
    strict_fail = 0

    for r in sample:
        try:
            img_path = r["path"]
            img = Image.open(img_path).convert("RGBA")
            feat = np.array(r["features"], dtype=np.float32)
            y, _ = forward(net, feat[None], training=False)
            params = targets_to_params(y[0])
            a = analyze(img)
            svg = trace_with(a, params)
            s = score(img, svg)

            is_clean = "degraded" not in r["path"] and "blur" not in r["name"] and "degraded" not in r["name"]
            if is_clean:
                score_ok = s["score"] >= 80
                coverage_ok = s.get("coverage", 0) >= 0.8
                precision_ok = s.get("precision", 0) >= 0.6
                color_ok = s.get("color_err", 999) <= 40
                paths_ok = 1 <= s.get("paths", 0) <= 50
                grade = "PASS" if (score_ok and coverage_ok and precision_ok and color_ok and paths_ok) else "FAIL"
            else:
                score_ok = s["score"] >= 60
                coverage_ok = s.get("coverage", 0) >= 0.6
                precision_ok = s.get("precision", 0) >= 0.4
                color_ok = True
                paths_ok = 1 <= s.get("paths", 0) <= 80
                grade = "PASS" if (score_ok and coverage_ok and precision_ok and paths_ok) else "FAIL"

            if grade == "PASS":
                strict_pass += 1
            else:
                strict_fail += 1
            total_score += s["score"]

            results.append({
                "name": r["name"],
                "score": round(s["score"], 2),
                "coverage": round(s.get("coverage", 0), 3),
                "precision": round(s.get("precision", 0), 3),
                "color_err": round(s.get("color_err", 0), 2),
                "paths": s.get("paths", 0),
                "grade": grade,
                "is_clean": is_clean,
                "params": params,
                "strict": {
                    "score_ok": score_ok,
                    "coverage_ok": coverage_ok,
                    "precision_ok": precision_ok,
                    "color_ok": color_ok,
                    "paths_ok": paths_ok
                }
            })
        except Exception as e:
            results.append({"name": r.get("name", "unknown"), "error": str(e), "grade": "ERROR"})

    avg_score = total_score / max(1, len(results))
    return {
        "strict": True,
        "total": len(results),
        "pass": strict_pass,
        "fail": strict_fail,
        "pass_rate": round(strict_pass / max(1, len(results)), 3),
        "avg_score": round(avg_score, 2),
        "thresholds": {
            "clean": "score>=80, coverage>=0.8, precision>=0.6, color_err<=40, paths 1-50",
            "blurred": "score>=60, coverage>=0.6, precision>=0.4, paths 1-80"
        },
        "results": results,
        "model": {
            "arch": f"1047->{W1.shape[1]}->{W2.shape[1]}->5",
            "onnx_size": (STATIC / "model" / "params.onnx").stat().st_size if (STATIC / "model" / "params.onnx").exists() else 0
        }
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
