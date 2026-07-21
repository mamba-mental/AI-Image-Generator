"""OpenRouter backend (#11) — image generation.

Primary path = the DEDICATED Image API (`POST /api/v1/images`), which — unlike the legacy
chat/completions image-modality path — actually accepts `aspect_ratio` / `size`, so the app's
aspect-preset dropdown is no longer a silent no-op for OpenRouter (params-research §11 / bug #3).
On a 400 (a model that doesn't support the dedicated endpoint, or a mismatched size trio) we retry
with aspect_ratio-only, then fall back to the legacy chat path so nothing regresses.

Images come back as data: URIs (-> PIL, saved unchanged) or http URLs (pass through to downloader).
Key from OPENROUTER_API_KEY. Ref: https://openrouter.ai/docs — Unified Image API announcement.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image

_IMAGES_API = "https://openrouter.ai/api/v1/images"
_CHAT_API = "https://openrouter.ai/api/v1/chat/completions"
_HEADERS_EXTRA = {"HTTP-Referer": "https://github.com/omni-image", "X-Title": "Omni-Image"}


def _one_image(url):
    """A single data:/http image url -> PIL (data) or the http url (pass-through) or an error str."""
    if url.startswith("data:"):
        try:
            return Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1])))
        except Exception as e:
            return f"openrouter Error: bad image data ({e})"
    if url.startswith("http"):
        return url
    return None


def _parse_chat(data: dict) -> list:
    """Legacy chat path: images live in choices[].message.images[].image_url.url."""
    out = []
    for ch in data.get("choices", []) or []:
        for img in ((ch.get("message", {}) or {}).get("images") or []):
            url = (img.get("image_url") or {}).get("url", "") if isinstance(img, dict) else ""
            r = _one_image(url)
            if r is not None:
                out.append(r)
    if not out:
        txt = ((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content")
        if txt:
            return [{"text": txt}]
        err = (data.get("error") or {}).get("message")
        return [f"openrouter Error: {err or 'no image in response'}"]
    return out


def _parse_images_api(data: dict) -> list:
    """Dedicated /images path: OpenAI-style {data:[{url|b64_json}]}, plus a tolerant fallback that
    scans for any data:/http image url so a minor shape drift doesn't drop a good render."""
    out = []
    for it in (data.get("data") or []):
        if not isinstance(it, dict):
            continue
        if it.get("b64_json"):
            try:
                out.append(Image.open(BytesIO(base64.b64decode(it["b64_json"]))))
                continue
            except Exception:
                pass
        r = _one_image(it.get("url", "") or "")
        if r is not None:
            out.append(r)
    return out


def _post(url, body, key, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", **_HEADERS_EXTRA})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    return json.loads(raw)


def _size_fields(params: dict) -> dict:
    """The aspect/size controls the DEDICATED endpoint accepts (§11) — sent only when present, so a
    model that ignores them isn't handed junk. width+height -> "WxH"; aspect_ratio passthrough."""
    f = {}
    w, h = params.get("width"), params.get("height")
    if w and h:
        f["size"] = f"{int(w)}x{int(h)}"
    if params.get("aspect_ratio"):
        f["aspect_ratio"] = params["aspect_ratio"]
    if params.get("resolution"):
        f["resolution"] = params["resolution"]
    return f


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return ["openrouter Error: OPENROUTER_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["openrouter Error: Model not selected."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["openrouter Error: prompt required."]

    size = _size_fields(params)
    # 1) DEDICATED /images endpoint — the only path with real aspect/size control.
    if progress:
        progress(f"Submitting to OpenRouter /images: {model_id}"
                 + (f" [{size.get('aspect_ratio') or size.get('size')}]" if size else ""))
    for attempt in ("full", "aspect_only"):
        body = {"model": model_id, "prompt": prompt}
        if attempt == "full":
            body.update(size)
        elif size.get("aspect_ratio"):        # retry with ratio-only (a mismatched size trio 400s)
            body["aspect_ratio"] = size["aspect_ratio"]
        elif "size" not in size:
            break                              # nothing size-ish to retry with → go to legacy
        try:
            out = _parse_images_api(_post(_IMAGES_API, body, key))
            if out:
                return out
        except urllib.error.HTTPError as e:
            if e.code != 400:
                detail = e.read().decode(errors="ignore")[:300]
                return [f"openrouter Error: HTTP {e.code} — {detail}"]
            # 400 → try the next attempt, then fall through to legacy
        except Exception:
            break

    # 2) LEGACY chat/completions fallback (no size control, but keeps working models working).
    if progress:
        progress(f"OpenRouter /images unavailable for {model_id} — using chat path (no size control)")
    body = {"model": model_id, "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"]}
    try:
        return _parse_chat(_post(_CHAT_API, body, key))
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:400]
        return [f"openrouter Error: HTTP {e.code} — {detail}"]
    except Exception as e:
        return [f"openrouter Error: {type(e).__name__}: {e}"]
