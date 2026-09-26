"""Regenerate QA_PROJECT_INVENTORY.json (directive §1).

Scans the repository and records what actually exists: source dirs,
frontend pages, backend endpoints, vectorization/mode entry points,
dataset/QA infrastructure, config files, environment variables used.
Pure stdlib.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*a: str) -> str:
    try:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def scan() -> dict:
    endpoints = re.findall(r'@app\.(get|post)\("([^"]+)"\)', (ROOT / "app/main.py").read_text())
    frontend = [p.name for p in (ROOT / "app/static").glob("*") if p.is_file()]
    model_modules = [p.name for p in (ROOT / "model").glob("*.py")]
    qa_scripts = [str(p.relative_to(ROOT)) for p in (ROOT / "qa").rglob("*") if p.is_file() and not p.name.endswith(".png")]
    pipeline = [p.name for p in (ROOT / "scripts/dataset").glob("*.py")]
    families = []
    for f_dir in sorted((ROOT / "dataset/icons").glob("*")):
        idx = f_dir / "index.json"
        if idx.exists():
            try:
                j = json.loads(idx.read_text())
                items = j["items"] if isinstance(j, dict) else j
                lic = j.get("license") if isinstance(j, dict) else None
                if not lic and items:
                    lic = items[0].get("license")
                families.append({"family": f_dir.name, "license": lic,
                                 "originals": len(items)})
            except Exception:
                pass
    env_vars = sorted(set(re.findall(r'os\.(?:getenv|environ\.get)\("([A-Z0-9_]+)"',
                          "\n".join(p.read_text(errors="ignore") for p in list(ROOT.glob("app/*.py")) + list(ROOT.glob("model/*.py"))))))[:64]
    inv = {
        "generated_by": "qa/inventory.py",
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "source_dirs": {
            "app/": "FastAPI backend + static frontend",
            "model/": "training, dataset gen, scoring, onnx export",
            "qa/": "QA runner, deterministic SVG analysis, browser regression proofs",
            "scripts/dataset/": "dataset extraction/rendering/manifest pipeline",
            "automation/": "TASK_STATE checkpoint + supervisor",
            "test-assets/": "visible test image corpus + manifest",
            "dataset/icons/": "open-license SVG ground-truth icon pairs",
        },
        "frontend_files": frontend,
        "backend_endpoints": [{"method": m.upper(), "path": p} for m, p in endpoints],
        "vectorize_modes": {
            "classic_engine": "POST /api/convert with sliders (colors/detail/smoothness), optional preset best-tier",
            "model": "POST /api/convert use_model=1 (trained params)",
            "presets": ["logo", "icon", "illustration", "lqip", "artistic", "custom"],
            "ai_assist": "POST /api/ai/vectorize (user's own API key, 11 providers)",
        },
        "model_modules": model_modules,
        "qa_infra": sorted(qa_scripts),
        "dataset_pipeline": {"scripts": pipeline, "families": families},
        "env_vars_referenced": env_vars,
        "persistence": {
            "server": "localStorage-based workspace persistence in frontend (app/static/app.js)",
            "verdicts": "model_data_snapshot/verdicts.jsonl",
            "checkpoint": "automation/TASK_STATE.json",
        },
    }
    return inv


if __name__ == "__main__":
    inv = scan()
    dest = ROOT / "QA_PROJECT_INVENTORY.json"
    dest.write_text(json.dumps(inv, indent=2))
    print("wrote", dest)
