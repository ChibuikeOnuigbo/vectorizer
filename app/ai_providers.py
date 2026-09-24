"""AI Assist mode: vision LLM vectorization using the USER'S OWN API key.

The user picks a provider, pastes their key into the settings modal (stored only
in their browser localStorage), and this module forwards ONE request to that
provider asking a vision model to redraw the image as SVG code.

Security approach (matches /home/user/research/vectorizers/notes.md):
- the key arrives in the X-AI-Key header and is used for exactly one outbound
  call. It is never written to disk, never logged (FastAPI does not log
  request headers), never cached.
- the image is sent only to the provider the user picked, under that
  provider's pricing and privacy terms. We tell the user this in the UI.
- the SVG the model returns is sanitized here (strip scripts, foreignObject,
  event handlers, javascript: URLs) and again client-side before display.

Only stdlib urllib is used so no extra dependencies are needed.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
import urllib.request
import urllib.error

from PIL import Image

MAX_AI_EDGE = 896          # resize before sending so payload stays small
AI_TIMEOUT = 150           # generous — models writing lots of SVG are slow
MAX_SVG_BYTES = 1_000_000  # refuse absurdly large outputs

SVG_PROMPT = (
    "You are an expert vector graphics artist. Recreate the image as clean "
    "SVG code. Rules: output ONLY the SVG markup, starting with <svg and "
    "ending with </svg>, no markdown fences, no explanation, no comments. "
    "Visible elements must be flat filled paths, rects, circles, ellipses, "
    "or polygons only. Match the image proportions exactly using an accurate "
    "viewBox and set width and height. Simplify into at most 60 solid color "
    "shapes, stacking larger background shapes behind smaller foreground "
    "shapes. Use smooth curves for curved edges. Do not use scripts, "
    "animations, filters, external links, fonts, embedded raster images, "
    "opacity tricks, or gradients. Plain color fills only."
)

# provider registry: style = how to build the request/parse the reply
PROVIDERS = {
    "openrouter": {
        "label": "OpenRouter",
        "style": "openai",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "models": [
            "google/gemini-2.5-flash",
            "openai/gpt-4o-mini",
            "qwen/qwen3-vl-235b-a22b-instruct",
            "anthropic/claude-sonnet-4.5",
            "meta-llama/llama-4-maverick",
        ],
        "keys": "https://openrouter.ai/keys",
    },
    "openai": {
        "label": "OpenAI",
        "style": "openai",
        "url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-5"],
        "keys": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic",
        "style": "anthropic",
        "url": "https://api.anthropic.com/v1/messages",
        "models": ["claude-sonnet-4-5", "claude-haiku-4-5"],
        "keys": "https://console.anthropic.com/settings/keys",
    },
    "gemini": {
        "label": "Google Gemini",
        "style": "gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        "models": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
        "keys": "https://aistudio.google.com/apikey",
    },
    "xai": {
        "label": "xAI Grok",
        "style": "openai",
        "url": "https://api.x.ai/v1/chat/completions",
        "models": ["grok-4", "grok-2-vision"],
        "keys": "https://console.x.ai",
    },
    "mistral": {
        "label": "Mistral",
        "style": "openai",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "models": ["pixtral-large-latest", "pixtral-12b-2409"],
        "keys": "https://console.mistral.ai/api-keys",
    },
    "groq": {
        "label": "Groq",
        "style": "openai",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "models": ["meta-llama/llama-4-scout-17b-16e-instruct"],
        "keys": "https://console.groq.com/keys",
    },
    "together": {
        "label": "Together AI",
        "style": "openai",
        "url": "https://api.together.xyz/v1/chat/completions",
        "models": ["meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"],
        "keys": "https://api.together.xyz/settings/api-keys",
    },
    "deepinfra": {
        "label": "DeepInfra",
        "style": "openai",
        "url": "https://api.deepinfra.com/v1/openai/chat/completions",
        "models": ["Qwen/Qwen2.5-VL-32B-Instruct"],
        "keys": "https://deepinfra.com/dash/api_keys",
    },
    "fireworks": {
        "label": "Fireworks AI",
        "style": "openai",
        "url": "https://api.fireworks.ai/inference/v1/chat/completions",
        "models": ["accounts/fireworks/models/llama4-maverick-instruct-basic"],
        "keys": "https://fireworks.ai/api-keys",
    },
    "huggingface": {
        "label": "Hugging Face",
        "style": "openai",
        "url": "https://router.huggingface.co/v1/chat/completions",
        "models": ["Qwen/Qwen2.5-VL-7B-Instruct", "Qwen/Qwen3-VL-8B-Instruct"],
        "keys": "https://huggingface.co/settings/tokens",
    },
}

FORBIDDEN_TAG_RE = re.compile(
    r"<\s*/?\s*(script|foreignObject|iframe|object|embed|video|audio|canvas|link|meta|animate|set|animateTransform|animateMotion)\b[^>]*>",
    re.I,
)
EVENT_ATTR_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
JS_URL_RE = re.compile(r"(javascript\s*:|data\s*:\s*text/html)", re.I)
HREF_RE = re.compile(r"\b(xlink:)?href\s*=", re.I)
USE_RE = re.compile(r"<\s*(use|image)\b[^>]*>")


def prepare_image_jpeg_b64(img_bytes: bytes) -> tuple[str, int, int]:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size
    if max(w, h) > MAX_AI_EDGE:
        f = MAX_AI_EDGE / max(w, h)
        img = img.resize((max(1, round(w * f)), max(1, round(h * f))), Image.LANCZOS)
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, (0, 0), img.getchannel("A"))
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("ascii"), w, h


def sanitize_svg(svg: str, w: int, h: int) -> str:
    """Remove anything that could execute or load external content."""
    svg = FORBIDDEN_TAG_RE.sub("", svg)
    svg = EVENT_ATTR_RE.sub("", svg)
    svg = JS_URL_RE.sub("#", svg)
    svg = HREF_RE.sub("data-x-href=", svg)
    svg = re.sub(r"\bstyle\s*=", "data-x-style=", svg)
    svg = USE_RE.sub("", svg)
    if "<svg" not in svg or "</svg>" not in svg:
        raise ValueError("no SVG returned")
    start = svg.index("<svg")
    end = svg.rindex("</svg>") + len("</svg>")
    svg = svg[start:end]
    # force sane root attributes
    svg = re.sub(
        r"<svg\b[^>]*>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        svg,
        count=1,
    )
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        raise ValueError("SVG too large")
    return svg


def _openai_payload(model: str, b64: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SVG_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Vectorize this image. Reply with only the SVG markup."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
        "max_tokens": 16000,
        "temperature": 0.2,
    }


def _build_request(provider: str, model: str, key: str, b64: str) -> urllib.request.Request:
    spec = PROVIDERS[provider]
    style = spec["style"]
    if style == "openai":
        url = spec["url"]
        body = json.dumps(_openai_payload(model, b64)).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://vectorizer.local"
            headers["X-Title"] = "Vectorizer"
        return urllib.request.Request(url, data=body, headers=headers, method="POST")
    if style == "anthropic":
        body = json.dumps({
            "model": model,
            "max_tokens": 16000,
            "system": SVG_PROMPT,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": "Vectorize this image. Reply with only the SVG markup."},
            ]}],
        }).encode()
        headers = {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
        return urllib.request.Request(spec["url"], data=body, headers=headers, method="POST")
    if style == "gemini":
        url = spec["url"].format(model=model, key=key)
        body = json.dumps({
            "contents": [{"role": "user", "parts": [
                {"text": SVG_PROMPT + " Vectorize this image. Reply with only the SVG markup."},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ]}],
            "generationConfig": {"maxOutputTokens": 16000, "temperature": 0.2},
        }).encode()
        return urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    raise ValueError(f"unknown provider style {style}")


def _parse_reply(provider: str, raw: bytes) -> str:
    spec = PROVIDERS[provider]
    data = json.loads(raw.decode("utf-8", "replace"))
    style = spec["style"]
    if style == "openai":
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("provider returned no choices")
        return str(choices[0].get("message", {}).get("content", ""))
    if style == "anthropic":
        parts = data.get("content") or []
        return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
    if style == "gemini":
        cands = data.get("candidates") or []
        if not cands:
            raise ValueError("gemini returned no candidates")
        parts = cands[0].get("content", {}).get("parts", [])
        return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
    raise ValueError(f"unknown provider style {style}")


_MDL_FENCE_RE = re.compile(r"^```(?:svg|xml)?\s*|\s*```$", re.M)


def ai_vectorize(img_bytes: bytes, provider: str, model: str, key: str,
                 detail: str = "auto", colors: int | None = None) -> dict:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider}")
    key = (key or "").strip()
    if len(key) < 8:
        raise ValueError("API key missing Add it in AI settings")
    if not model:
        model = PROVIDERS[provider]["models"][0]

    t0 = time.time()
    b64, w, h = prepare_image_jpeg_b64(img_bytes)
    prompt_note = ""
    if detail in ("low", "high"):
        prompt_note = f" Desired detail level {detail}."
    if colors and 2 <= colors <= 128:
        prompt_note += f" Use about {colors} colors."

    req = _build_request(provider, model, key, b64)
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        try:
            detail_txt = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail_txt = str(e)
        raise RuntimeError(f"{PROVIDERS[provider]['label']} error {e.code}: {detail_txt}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"could not reach {PROVIDERS[provider]['label']}: {e.reason}") from e

    text = _parse_reply(provider, raw)
    text = _MDL_FENCE_RE.sub("", text).strip()
    if prompt_note:  # keep for result note only
        pass
    svg = sanitize_svg(text, w, h)
    fills = re.findall(r'fill="(#[0-9A-Fa-f]{3,8})"', svg)
    paths = len(re.findall(r"<(path|rect|circle|ellipse|polygon)\b", svg))
    kb = round(len(svg.encode("utf-8")) / 1024, 1)
    meta = {
        "width": w, "height": h,
        "colors": len(set(fills)) or 0,
        "paths": paths,
        "kb": kb,
        "flat": True,
        "transparent_bg": False,
        "seconds": round(time.time() - t0, 1),
        "ai": True,
        "provider": provider,
        "model": model,
        "note": "AI redrawn preview quality varies by model",
    }
    return {"svg": svg, "meta": meta}


def provider_catalog() -> dict:
    return {
        pid: {k: v for k, v in spec.items() if k != "style"}
        for pid, spec in PROVIDERS.items()
    }
