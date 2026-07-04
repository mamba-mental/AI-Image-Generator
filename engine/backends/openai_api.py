"""OpenAI Images backend — POST /v1/images/generations.

gpt-image-* return b64_json; dall-e-3 can return a URL. Response verified live 2026-07-03.
"""
import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image

# gpt-image only accepts a fixed set of sizes; map free width/height to the nearest.
_GPT_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}


def _size(params: dict, model_id: str):
    size = params.get("size")
    if not size and params.get("width") and params.get("height"):
        size = f"{int(params['width'])}x{int(params['height'])}"
    if not size:
        return None
    if model_id.startswith("gpt-image") and size not in _GPT_SIZES:
        w, h = (int(x) for x in size.split("x")) if "x" in size else (1024, 1024)
        return "1536x1024" if w > h else "1024x1536" if h > w else "1024x1024"
    return size


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return ["OpenAI Error: OPENAI_API_KEY not set (add it in Settings)."]
    model_id = model_id or "gpt-image-2"
    body = {"model": model_id, "prompt": params.get("prompt", ""),
            "n": int(params.get("num_outputs", 1) or 1)}
    size = _size(params, model_id)
    if size:
        body["size"] = size
    for opt in ("quality", "background", "output_format"):
        if params.get(opt):
            body[opt] = params[opt]

    if progress:
        progress(f"OpenAI {model_id}…")
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=180).read())
    except urllib.error.HTTPError as e:
        return [f"OpenAI Error: HTTP {e.code} - {e.read().decode('utf-8', 'replace')[:300]}"]
    except Exception as e:
        return [f"OpenAI Error: {e}"]

    out = []
    for item in d.get("data", []):
        if item.get("b64_json"):
            out.append(Image.open(io.BytesIO(base64.b64decode(item["b64_json"]))))
        elif item.get("url"):
            out.append(item["url"])
    return out or ["OpenAI Error: no image in response"]
