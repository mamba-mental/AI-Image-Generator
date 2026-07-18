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
    for k in ("width", "height", "steps", "seed", "negative_prompt"):
        v = params.get(k)
        if v not in (None, ""):
            body[k] = v
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
