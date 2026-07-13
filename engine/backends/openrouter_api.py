"""OpenRouter backend (#11) — image generation via the chat/completions image-modality path.

OpenRouter image-capable models (google/gemini-*-image, openai/gpt-*-image) return generated
images in choices[].message.images as data: URIs (or http URLs). Data URIs are decoded to PIL
Images so the existing save layer persists them unchanged; http URLs pass through to the downloader.
Key from OPENROUTER_API_KEY (env/credential store). Ref: https://openrouter.ai/docs
"""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image

_API = "https://openrouter.ai/api/v1/chat/completions"


def _parse(data: dict) -> list:
    """Pull images (data URI -> PIL, http -> URL) from an OpenRouter chat response."""
    out = []
    for ch in data.get("choices", []) or []:
        msg = ch.get("message", {}) or {}
        for img in (msg.get("images") or []):
            url = (img.get("image_url") or {}).get("url", "") if isinstance(img, dict) else ""
            if url.startswith("data:"):
                try:
                    out.append(Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))))
                except Exception as e:
                    out.append(f"openrouter Error: bad image data ({e})")
            elif url.startswith("http"):
                out.append(url)
    if not out:
        txt = ((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content")
        if txt:
            return [{"text": txt}]
        err = (data.get("error") or {}).get("message")
        return [f"openrouter Error: {err or 'no image in response'}"]
    return out


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return ["openrouter Error: OPENROUTER_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["openrouter Error: Model not selected."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["openrouter Error: prompt required."]

    body = {"model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"]}
    if progress:
        progress(f"Submitting to OpenRouter: {model_id}")
    req = urllib.request.Request(
        _API, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/ai-studio-void", "X-Title": "AI Studio Void"})
    try:
        raw = urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:400]
        return [f"openrouter Error: HTTP {e.code} — {detail}"]
    except Exception as e:
        return [f"openrouter Error: {type(e).__name__}: {e}"]
    try:
        return _parse(json.loads(raw))
    except Exception as e:
        return [f"openrouter Error: bad response ({e})"]
