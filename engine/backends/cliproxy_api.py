"""cliproxy backend — image generation via the self-hosted CLIProxyAPI OpenAI-compatible endpoint
(HP2 :8317/v1/images/generations).

CLIProxy exposes ~500 models; the ones routable through /v1/images/generations are the OpenAI/Grok
image family — gpt-image-1.5, gpt-image-2, grok-imagine-image (others like Imagen/qwen/gemini-image
route through the chat path and are out of scope for this endpoint). Returns b64_json -> PIL (or url).
Key = CLIPROXY_API_KEY (the CLIProxy client key, env / credential store). Endpoint overridable via CLIPROXY_BASE_URL.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image

_BASE = os.environ.get("CLIPROXY_BASE_URL", "http://192.168.86.191:8317/v1").rstrip("/")
_API = _BASE + "/images/generations"


def _parse(d: dict) -> list:
    out = []
    for item in (d.get("data") or []):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            try:
                out.append(Image.open(BytesIO(base64.b64decode(item["b64_json"]))))
            except Exception as e:
                out.append(f"cliproxy Error: bad image data ({e})")
        elif item.get("url"):
            out.append(item["url"])
    if not out:
        err = (d.get("error") or {}).get("message")
        return [f"cliproxy Error: {err or 'no image in response'}"]
    return out


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("CLIPROXY_API_KEY")
    if not key:
        return ["cliproxy Error: CLIPROXY_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["cliproxy Error: Model not selected."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["cliproxy Error: prompt required."]

    body = {"model": model_id, "prompt": prompt, "n": int(params.get("num_outputs", 1) or 1)}
    size = params.get("size")
    if not size and params.get("width") and params.get("height"):
        size = f"{params['width']}x{params['height']}"
    if size:
        body["size"] = size
    if progress:
        progress(f"Submitting to cliproxy: {model_id}")
    req = urllib.request.Request(
        _API, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        return [f"cliproxy Error: HTTP {e.code} — {e.read().decode(errors='ignore')[:400]}"]
    except Exception as e:
        return [f"cliproxy Error: {type(e).__name__}: {e}"]
    try:
        return _parse(json.loads(raw))
    except Exception as e:
        return [f"cliproxy Error: bad response ({e})"]
