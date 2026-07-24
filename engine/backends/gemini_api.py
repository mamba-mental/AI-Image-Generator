"""Gemini backend — port of app.py _call_gemini_api (:2046). Raw urllib kept (no SDK dep).

Returns a list of PIL Images / "Gemini Error: ..." strings (one per requested output).
"""
import base64
import io
import json
import os
import re
import ssl
import time
import traceback
import urllib.error
import urllib.request

from PIL import Image


def _retry_wait(headers, fallback):
    """Seconds to wait before a 429 retry: server header if present, else exp `fallback`. Capped 1–30s."""
    for h in ("Retry-After", "X-RateLimit-Reset", "x-ratelimit-reset"):
        v = headers.get(h) if headers else None
        if not v:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n > 1e6:  # absolute epoch reset -> delta from now
            n = n - time.time()
        return max(1.0, min(n, 30.0))
    return max(1.0, min(fallback, 30.0))


def _call_once(model_id: str, params: dict):
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return "Gemini Error: API Key not configured. Set GEMINI_API_KEY in .env or configure via UI."

    prompt_text = params.get("prompt", "")
    if not prompt_text:
        return "Gemini Error: No prompt provided."

    full_prompt = f"Generate an image: {prompt_text}"

    generation_config = {"responseModalities": ["TEXT", "IMAGE"]}
    image_config = {}
    if params.get("aspect_ratio"):
        image_config["aspectRatio"] = params["aspect_ratio"]
    if params.get("image_size"):
        image_config["imageSize"] = params["image_size"]
    if image_config:
        generation_config["imageConfig"] = image_config

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_key}"

    # imageConfig (aspectRatio/imageSize) hard-400s on models that don't accept those knobs
    # (e.g. a fixed-1024px image model). Self-heal: drop imageConfig and retry once, mirroring
    # together_api's unsupported-param loop. 429s get header-aware backoff (transient per-minute
    # limits clear; the daily-quota message is surfaced only after retries are exhausted). Other
    # 400s (bad prompt, safety) surface as-is.
    attempts_429 = 0
    for _attempt in range(6):
        request_body = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": generation_config,
        }
        req = urllib.request.Request(url, data=json.dumps(request_body).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            resp = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=120)
            data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            if e.code == 429:
                attempts_429 += 1
                if attempts_429 < 3:
                    time.sleep(_retry_wait(e.headers, 2 ** attempts_429))
                    continue
                return ("Gemini Error: Rate limit exceeded (429). Try a different API key or wait "
                        f"for quota reset at midnight Pacific. {error_body[:200]}")
            if e.code == 400:
                if ("imageConfig" in generation_config
                        and re.search(r"image[_ ]?config|image[_ ]?size|aspect[_ ]?ratio",
                                      error_body, re.IGNORECASE)):
                    generation_config.pop("imageConfig", None)
                    continue
                return f"Gemini Error: Bad request (400). {error_body[:300]}"
            return f"Gemini Error: HTTP {e.code} - {error_body[:300]}"
        except urllib.error.URLError as e:
            return f"Gemini Error: Connection failed - {e}"
        except json.JSONDecodeError as e:
            return f"Gemini Error: Failed to parse API response - {e}"

        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    img_bytes = base64.b64decode(part["inlineData"]["data"])
                    return Image.open(io.BytesIO(img_bytes))

        text_parts = [part["text"]
                      for candidate in data.get("candidates", [])
                      for part in candidate.get("content", {}).get("parts", [])
                      if "text" in part]
        if text_parts:
            return f"Gemini Error: Model returned text instead of image - {' '.join(text_parts)[:300]}"
        return "Gemini Error: No image data in response."
    return "Gemini Error: retries exhausted after dropping imageConfig."


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    model_id = model_id or params.get("model_id", "gemini-2.5-flash-image")
    num_outputs = params.get("num_outputs", 1)
    results = []
    for i in range(num_outputs):
        if cancel_event is not None and cancel_event.is_set():
            results.append("Gemini Error: Cancelled.")
            break
        if progress:
            progress(f"Generating image {i + 1}/{num_outputs} (Gemini)...")
        try:
            results.append(_call_once(model_id, params))
        except Exception as e:
            traceback.print_exc()
            results.append(f"Gemini Error: {e}")
    return results
