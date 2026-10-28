"""AI SVG analysis (sections 14, 15, 33).

Pipeline: deterministic analysis FIRST (facts), then optionally an AI
interpretation layered on top - the report ALWAYS separates:

  observed_from_svg   (verified by parsing - ground truth)
  model_interpretation (produced by the AI) if a provider key is available
  model_recommendation (AI suggestions)

Usage (any working key; env var `AI_KEY` or --key):
  PYTHONPATH=vendor:app/deps:. python3 qa/ai_svg_analysis.py path/to.svg \
      --provider openrouter --model gpt-4o-mini --out svg_analysis.json

Without a key/network the script still writes the structured report with the
AI sections explicitly marked UNSUPPORTED_WITH_REASON (no fabrication).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "vendor"), str(ROOT / "app"), str(ROOT / "app/deps"), str(ROOT)):
    sys.path.insert(0, p)

from qa.svg_analysis import analyze_svg  # noqa: E402

PROMPT_TMPL = """You are analyzing an SVG document. You ONLY have access to:
(A) the deterministic parse facts below, and
(B) the SVG source text.
Do not invent elements that are not in (A) or (B). Answer concisely with JSON
keys: interpretation (string, what the geometry plausibly represents),
grouping (string describing <g> layering),
redundant_elements (array of strings), simplification (array of strings),
complexity_assessment (string: path/command budget vs the depicted subject).

DETERMINISTIC FACTS (OBSERVED FROM SVG, VERIFIED BY PARSING):
{facts}

SVG SOURCE (truncated to 6000 chars):
{svg}
"""


def _ai_call(provider: str, model: str, key: str, prompt: str, timeout: int = 60) -> dict:
    """OpenAI-compatible chat call (works for openrouter/openai/etc.)."""
    url = {
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "mistral": "https://api.mistral.ai/v1/chat/completions",
        "together": "https://api.together.xyz/v1/chat/completions",
        "deepinfra": "https://api.deepinfra.com/v1/openai/chat/completions",
        "fireworks": "https://api.fireworks.ai/inference/v1/chat/completions",
        "xai": "https://api.x.ai/v1/chat/completions",
    }.get(provider)
    if not url:
        return {"error": f"provider '{provider}' has no OpenAI-compatible chat endpoint in this scaffold"}
    body = json.dumps({
        "model": model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}",
    })
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = json.loads(r.read())
            txt = raw["choices"][0]["message"]["content"]
            try:
                parsed = json.loads(txt.strip().strip("`").removeprefix("json").strip())
            except Exception:
                parsed = {"raw_text": txt}
            return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000), "model": raw.get("model", model), "parsed": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "ms": round((time.perf_counter() - t0) * 1000)}


def analyze(svg_path: str, provider: str, model: str, key: str | None, out_path: str | None) -> dict:
    svg = Path(svg_path).read_text(encoding="utf-8", errors="ignore")
    facts = analyze_svg(svg)
    report: dict = {
        "svg_file": svg_path,
        "observed_from_svg": facts,
        "model_interpretation": None,
        "model_recommendation": None,
        "provider": provider,
        "model": model,
        "status": "PASS",
        "notes": "observed_from_svg is verified by parsing; AI sections are clearly separated interpretations, not ground truth",
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not key:
        report["model_interpretation"] = {"status": "UNSUPPORTED_WITH_REASON",
                                          "reason": "no AI key configured (env AI_KEY or --key)"}
        report["status"] = "UNSUPPORTED_WITH_REASON"
    else:
        prompt = PROMPT_TMPL.format(facts=json.dumps(facts, indent=1), svg=svg[:6000])
        call = _ai_call(provider, model, key, prompt)
        if call.get("ok"):
            report["model_interpretation"] = call["parsed"].get("interpretation", call["parsed"])
            report["model_recommendation"] = {
                "redundant_elements": call["parsed"].get("redundant_elements"),
                "simplification": call["parsed"].get("simplification"),
                "complexity_assessment": call["parsed"].get("complexity_assessment"),
                "grouping": call["parsed"].get("grouping"),
            }
            report["ai_call_ms"] = call["ms"]
            report["ai_model_reported"] = call["model"]
        else:
            report["model_interpretation"] = {"status": "UNSUPPORTED_WITH_REASON", "reason": call.get("error")}
            report["status"] = "UNSUPPORTED_WITH_REASON"
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(report, indent=1))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("--provider", default="openrouter")
    ap.add_argument("--model", default="")
    ap.add_argument("--key", default=os.environ.get("AI_KEY") or None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rep = analyze(args.svg, args.provider, args.model, args.key, args.out)
    print(json.dumps({k: rep[k] for k in ("status", "provider", "model", "svg_file")}, indent=1))


if __name__ == "__main__":
    main()
