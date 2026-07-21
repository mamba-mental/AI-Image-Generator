"""Together.ai backend — image generation via the OpenAI-compatible /v1/images/generations endpoint.

Together sits behind Cloudflare, which 403s the default Python-urllib User-Agent (CF error 1010) —
so we always send a browser UA. Serverless FLUX models return image URLs (default); b64_json is
also handled. Non-serverless models 400 with a clear message (surfaced to the UI).
Key from TOGETHER_API_KEY (env / credential store). Ref: https://docs.together.ai/reference/post-images-generations
"""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image

_API = "https://api.together.xyz/v1/images/generations"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _supports_lora(model_id: str) -> bool:
    """Together accepts image_loras only on FLUX.1-dev-lora and FLUX.2-dev (research §Together)."""
    m = (model_id or "").lower()
    return "dev-lora" in m or "flux.2-dev" in m or "flux-2-dev" in m


def _parse(d: dict) -> list:
    out = []
    for item in (d.get("data") or []):
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            out.append(item["url"])
        elif item.get("b64_json"):
            try:
                out.append(Image.open(BytesIO(base64.b64decode(item["b64_json"]))))
            except Exception as e:
                out.append(f"together Error: bad image data ({e})")
    if not out:
        err = (d.get("error") or {}).get("message")
        return [f"together Error: {err or 'no image in response'}"]
    return out


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("TOGETHER_API_KEY")
    if not key:
        return ["together Error: TOGETHER_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["together Error: Model not selected."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["together Error: prompt required."]

    body = {"model": model_id, "prompt": prompt, "n": int(params.get("num_outputs", 1) or 1)}
    for k in ("width", "height", "steps", "seed", "negative_prompt",
              "guidance_scale", "output_format", "disable_safety_checker"):
        v = params.get(k)
        if v not in (None, ""):
            body[k] = v
    # LoRA (Phase 4) — Together image_loras:[{path,scale}] (max 2), only on FLUX.1-dev-lora / FLUX.2-dev
    loras = [lo for lo in (params.get("enabled_loras") or []) if lo.get("enabled")]
    if loras and _supports_lora(model_id):
        body["image_loras"] = [{"path": lo["url"], "scale": float(lo.get("scale", 1.0))} for lo in loras[:2]]
    if progress:
        progress(f"Submitting to Together: {model_id}")
    req = urllib.request.Request(
        _API, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": _UA})
    try:
        raw = urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        return [f"together Error: HTTP {e.code} — {e.read().decode(errors='ignore')[:400]}"]
    except Exception as e:
        return [f"together Error: {type(e).__name__}: {e}"]
    try:
        return _parse(json.loads(raw))
    except Exception as e:
        return [f"together Error: bad response ({e})"]
