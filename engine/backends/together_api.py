"""Together.ai backend — image generation via the OpenAI-compatible /v1/images/generations endpoint.

Together sits behind Cloudflare, which 403s the default Python-urllib User-Agent (CF error 1010) —
so we always send a browser UA. Serverless FLUX models return image URLs (default); b64_json is
also handled. Non-serverless models 400 with a clear message (surfaced to the UI).
Key from TOGETHER_API_KEY (env / credential store). Ref: https://docs.together.ai/reference/post-images-generations
"""
import base64
import json
import os
import re
import time
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


def _retry_wait(headers, fallback: float) -> float:
    """Seconds to wait before a 429 retry. Prefer the server's reset hint
    (Retry-After = seconds; X-RateLimit-Reset = seconds-remaining OR an epoch
    timestamp), else the caller's exponential-backoff fallback. Clamped 1–30s."""
    for h in ("Retry-After", "X-RateLimit-Reset", "x-ratelimit-reset"):
        v = headers.get(h) if headers else None
        if not v:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n > 1e6:  # looks like a unix epoch → convert to seconds-remaining
            n = n - time.time()
        return max(1.0, min(n, 30.0))
    return max(1.0, min(fallback, 30.0))


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
    # Schnell/turbo FLUX models are timestep-distilled and reject guidance_scale (HTTP 400).
    # Strip it up front so the common free-model path skips a wasted round-trip; the generic
    # 400-retry below still covers any other model that rejects any other param.
    if "schnell" in model_id.lower():
        body.pop("guidance_scale", None)
    # LoRA (Phase 4) — Together image_loras:[{path,scale}] (max 2), only on FLUX.1-dev-lora / FLUX.2-dev
    loras = [lo for lo in (params.get("enabled_loras") or []) if lo.get("enabled")]
    if loras and _supports_lora(model_id):
        body["image_loras"] = [{"path": lo["url"], "scale": float(lo.get("scale", 1.0))} for lo in loras[:2]]
    if progress:
        progress(f"Submitting to Together: {model_id}")

    # Self-healing retries:
    #  • HTTP 400 "Unsupported use of '<param>' parameter" → drop that param and retry (no wait).
    #  • HTTP 429 (Together's rate limits are DYNAMIC) → wait per X-RateLimit-Reset/Retry-After,
    #    else exponential back-off from 2s, and retry. 400-param-drops don't consume the backoff.
    backoff = 2.0
    cancelled = (lambda: cancel_event is not None
                 and getattr(cancel_event, "is_set", lambda: False)())
    for _attempt in range(6):
        req = urllib.request.Request(
            _API, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": _UA})
        try:
            raw = urllib.request.urlopen(req, timeout=180).read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")
            if e.code == 400:
                m = re.search(r"Unsupported use of '([^']+)' parameter", msg)
                if m and m.group(1) in body:
                    dropped = m.group(1)
                    body.pop(dropped, None)
                    if progress:
                        progress(f"Together rejected '{dropped}' for {model_id} — dropping it and retrying")
                    continue
                return [f"together Error: HTTP 400 — {msg[:400]}"]
            if e.code == 429:
                if cancelled():
                    return ["together Error: cancelled"]
                wait = _retry_wait(e.headers, backoff)
                if progress:
                    progress(f"Together rate-limited (429) — backing off {wait:.0f}s then retrying")
                # cancellable wait: check every 0.5s so a cancel bails mid-backoff, not after 30s
                slept = 0.0
                while slept < wait:
                    if cancelled():
                        return ["together Error: cancelled"]
                    time.sleep(min(0.5, wait - slept))
                    slept += 0.5
                backoff = min(backoff * 2, 30.0)
                continue
            return [f"together Error: HTTP {e.code} — {msg[:400]}"]
        except Exception as e:
            return [f"together Error: {type(e).__name__}: {e}"]
        try:
            return _parse(json.loads(raw))
        except Exception as e:
            return [f"together Error: bad response ({e})"]
    return ["together Error: still rate-limited (429) after several back-offs — wait a bit and retry, or switch model/provider"]
