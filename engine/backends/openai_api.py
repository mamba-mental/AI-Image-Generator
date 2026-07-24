"""OpenAI Images backend — POST /v1/images/generations.

gpt-image-* return b64_json; dall-e-3 can return a URL. Response verified live 2026-07-03.
Params audited against developers.openai.com/api/reference (2026-07): gpt-image models accept
size / quality(auto|low|medium|high) / background / output_format / output_compression / moderation
and REJECT the dall-e-only response_format & style (we never send those). gpt-image-2 additionally
takes arbitrary WxH sizes. A self-healing 400-retry drops any residual per-model-unsupported param
(the OpenAI error body carries error.param) and retries, instead of hard-failing.
"""
import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

from PIL import Image

# gpt-image-1 / -1.5 / -1-mini accept only this fixed size enum; gpt-image-2 also takes arbitrary WxH.
_GPT_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}


def _size(params: dict, model_id: str):
    size = params.get("size")
    if not size and params.get("width") and params.get("height"):
        size = f"{int(params['width'])}x{int(params['height'])}"
    if not size:
        return None
    mid = model_id or ""
    # gpt-image-2 accepts arbitrary WxH (each divisible by 16, aspect 1:3–3:1, ≤3840 per side) —
    # pass a conforming request through so aspect presets aren't flattened to one of three enums.
    if mid.startswith("gpt-image-2") and size != "auto" and "x" in size:
        try:
            w, h = (int(x) for x in size.lower().split("x"))
            if w % 16 == 0 and h % 16 == 0 and 0 < w <= 3840 and 0 < h <= 3840 and (1 / 3) <= (w / h) <= 3:
                return f"{w}x{h}"
        except Exception:
            pass
        # non-conforming → fall through to the enum snap below (safe, never 400s)
    if mid.startswith("gpt-image") and size not in _GPT_SIZES:
        w, h = (int(x) for x in size.split("x")) if "x" in size else (1024, 1024)
        return "1536x1024" if w > h else "1024x1536" if h > w else "1024x1024"
    return size


def _rejected_param(err_text: str, body: dict):
    """Name of an OPTIONAL param a 400 body (OpenAI error shape) rejected AND that is present in
    `body`, so the caller can drop it and retry. Prefers the structured error.param field; falls
    back to a message regex. Never returns model/prompt (essential)."""
    name, msg = None, err_text
    try:
        err = (json.loads(err_text) or {}).get("error") or {}
        p = err.get("param")
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
    if params.get("output_compression") is not None:
        body["output_compression"] = int(params["output_compression"])
    if params.get("moderation") is not None:
        body["moderation"] = params["moderation"]

    if progress:
        progress(f"OpenAI {model_id}…")
    # Self-healing: on a 400 that names an unsupported/unknown parameter (OpenAI puts it in
    # error.param), drop that optional param and retry (cap 4) — resolves per-model schema quirks
    # (dall-e handed a gpt-image-only field, an unsupported size/quality value, etc.) without a
    # hardcoded matrix. model/prompt are never dropped.
    for _attempt in range(6):
        req = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=180).read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if progress:
                    progress(f"OpenAI rate-limited (429) — backing off for {model_id}")
                if _sleep_for_retry(e.headers, _attempt, cancel_event):
                    return ["OpenAI Error: cancelled"]
                continue
            detail = e.read().decode("utf-8", "replace")
            if e.code == 400:
                bad = _rejected_param(detail, body)
                if bad:
                    body.pop(bad, None)
                    if progress:
                        progress(f"OpenAI rejected '{bad}' for {model_id} — dropping it and retrying")
                    continue
            return [f"OpenAI Error: HTTP {e.code} - {detail[:300]}"]
        except Exception as e:
            return [f"OpenAI Error: {e}"]

        out = []
        for item in d.get("data", []):
            if item.get("b64_json"):
                out.append(Image.open(io.BytesIO(base64.b64decode(item["b64_json"]))))
            elif item.get("url"):
                out.append(item["url"])
        return out or ["OpenAI Error: no image in response"]
    return ["OpenAI Error: too many unsupported-parameter retries"]
