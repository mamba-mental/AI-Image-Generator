"""OpenRouter backend (#11) — image generation.

Primary path = the DEDICATED Unified Image API (`POST /api/v1/images`), verified current 2026-07:
`model`+`prompt` required, plus `aspect_ratio` / `size` / `resolution` / `n` / `seed` — so the app's
aspect-preset dropdown is a real control here (params-research §11 / bug #3), unlike the legacy
chat/completions image-modality path which has no size control. On a 400 we self-heal: drop the param
the error names (or shed size fields one at a time), then fall through to the legacy chat path so a
chat-only image model (404 on the dedicated endpoint) still renders.

Images come back as data: URIs or b64_json (-> PIL, saved unchanged) or http URLs (pass through to
downloader). Key from OPENROUTER_API_KEY. Ref: https://openrouter.ai/docs — Unified Image API.
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
    """Dedicated /images path: {data:[{b64_json|url, media_type}]}, plus a tolerant fallback that
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


def _rejected_param(err_text: str, body: dict):
    """Name of an OPTIONAL param a 400 rejected & present in `body` — drop-and-retry fuel. Prefers a
    structured error.param field (OpenAI-style), falls back to a message regex. OpenRouter normalizes
    errors variably, so this degrades gracefully to None (caller then sheds size fields). Never
    returns model/prompt (essential)."""
    name, msg = None, err_text
    try:
        err = (json.loads(err_text) or {}).get("error") or {}
        p = err.get("param") or (err.get("metadata") or {}).get("param")
        if isinstance(p, str) and p:
            name = p.split(".")[0].split("[")[0]
        msg = err.get("message") or err_text
    except Exception:
        pass
    if not name:
        m = (re.search(r"(?:[Uu]nsupported|[Uu]nknown) parameter:?\s*'?([A-Za-z0-9_.\[\]]+)'?", msg)
             or re.search(r"'([A-Za-z0-9_]+)'\s+parameter", msg)
             or re.search(r"[Pp]arameter\s+'([A-Za-z0-9_]+)'", msg))
        if m:
            name = m.group(1).split(".")[0].split("[")[0]
    if name and name in body and name not in ("model", "prompt"):
        return name
    return None


def _sleep_for_retry(headers, attempt, cancel_event) -> bool:
    """429 backoff: wait per Retry-After / X-RateLimit-Reset header if present, else exponential from
    2s (2→4→…, cap 30s). Sleeps in ~0.5s slices so a cancel_event bails fast. Returns True if cancelled."""
    wait = min(2.0 * 2 ** attempt, 30.0)
    for h in ("Retry-After", "X-RateLimit-Reset", "x-ratelimit-reset"):
        v = headers.get(h) if headers else None
        if not v:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            break
        wait = max(1.0, min(n - time.time() if n > 1e6 else n, 30.0))
        break
    slept = 0.0
    while slept < wait:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return True
        time.sleep(min(0.5, wait - slept))
        slept += 0.5
    return False


def balance() -> dict:
    """Real $-balance via GET /v1/credits (total_credits - total_usage) — live-verified
    2026-07-21, HTTP 200, computes a genuine remaining-$ figure. Preferred over /v1/key
    (also live/200 but `limit` is null for this key -> only reports raw usage, no $-left).
    Reads the CURRENTLY-active pooled key (env, mirrored by keypool on rotation)."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"label": "no key", "kind": "none"}
    req = urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("data", {})
    except Exception as e:
        return {"label": f"balance unavailable ({type(e).__name__})", "kind": "none"}
    total, used = d.get("total_credits"), d.get("total_usage")
    if total is None:
        return {"label": f"${used or 0:.2f} used · no cap", "kind": "info"}
    left = max(0.0, float(total) - float(used or 0))
    return {"label": f"${left:.2f} left", "kind": "low" if left < 2 else "ok"}


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
    # 1) DEDICATED /images endpoint — the only path with real aspect/size control. Self-heal a 400 by
    #    dropping the named param (or shedding size fields one at a time); a 404 (model not served by
    #    this endpoint) or exhausted retries fall through to the legacy chat path below.
    if progress:
        progress(f"Submitting to OpenRouter /images: {model_id}"
                 + (f" [{size.get('aspect_ratio') or size.get('size')}]" if size else ""))
    body = {"model": model_id, "prompt": prompt, **size}
    for _attempt in range(6):
        try:
            out = _parse_images_api(_post(_IMAGES_API, body, key))
            if out:
                return out
            break                                  # 200 but no image → try the chat path
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore")
            if e.code == 429:                       # rate-limited → wait+retry, NEVER fall to chat
                if progress:
                    progress(f"OpenRouter rate-limited (429) — backing off for {model_id}")
                if _sleep_for_retry(e.headers, _attempt, cancel_event):
                    return ["openrouter Error: cancelled"]
                continue
            if e.code == 400:
                bad = _rejected_param(detail, body)
                if bad:
                    body.pop(bad, None)
                    if progress:
                        progress(f"OpenRouter rejected '{bad}' for {model_id} — dropping it and retrying")
                    continue
                for k in ("size", "resolution", "aspect_ratio"):   # no named param → shed a size field
                    if k in body:
                        body.pop(k, None)
                        break
                else:
                    break                          # nothing left to shed → legacy
                continue
            if e.code == 404:                       # model not on the dedicated endpoint → chat path
                break
            return [f"openrouter Error: HTTP {e.code} — {detail[:300]}"]
        except Exception:
            break

    # 2) LEGACY chat/completions fallback (no size control, but keeps chat-only image models working).
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
