"""NVIDIA NIM image backend — POST https://ai.api.nvidia.com/v1/genai/{model}.

Response verified live 2026-07-03: {"artifacts":[{"base64", "finishReason", "seed"}]}.
Note: NVIDIA image endpoints can cold-start slowly (30-120s) — timeout is generous.
"""
import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        return ["NVIDIA Error: NVIDIA_API_KEY not set (add it in Settings)."]
    if not model_id:
        return ["NVIDIA Error: model not selected."]

    body = {
        "prompt": params.get("prompt", ""),
        "mode": "base",
        "cfg_scale": float(params.get("guidance_scale", params.get("cfg_scale", 3.5))),
        "width": int(params.get("width", 1024)),
        "height": int(params.get("height", 1024)),
        "steps": int(params.get("num_inference_steps", params.get("steps", 25))),
    }
    if params.get("seed") is not None:
        body["seed"] = int(params["seed"])
    if params.get("negative_prompt"):
        body["negative_prompt"] = params["negative_prompt"]

    if progress:
        progress(f"NVIDIA {model_id} (may cold-start)…")
    req = urllib.request.Request(
        f"https://ai.api.nvidia.com/v1/genai/{model_id}",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=200).read())
    except urllib.error.HTTPError as e:
        return [f"NVIDIA Error: HTTP {e.code} - {e.read().decode('utf-8', 'replace')[:300]}"]
    except Exception as e:
        return [f"NVIDIA Error: {e}"]

    out = []
    for art in d.get("artifacts", []):
        if art.get("base64"):
            out.append(Image.open(io.BytesIO(base64.b64decode(art["base64"]))))
    return out or [f"NVIDIA Error: no artifact in response (keys: {list(d.keys())})"]
