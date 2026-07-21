"""Ideogram backend — text-to-image via the Ideogram 3.0 REST API.

Ideogram auth is an `Api-Key` header (NOT Bearer) and the v3 generate endpoint takes
multipart/form-data, so scalar fields are sent as (None, value) tuples via requests'
`files=` form (same trick the ideogram-mcp uses). Returned image URLs expire after a
short window; jobs.py downloads/persists them immediately (same path as Together).

The app's generic param panel speaks width/height/num_outputs/seed; Ideogram speaks
aspect_ratio + rendering_speed + style_type, so we translate: model_id carries the
rendering speed (ideogram-v3-turbo|-default|-quality), width/height map to the nearest
supported aspect ratio. Key from IDEOGRAM_API_KEY (env / credential store).
Ref: https://developer.ideogram.ai/api-reference/api-reference/generate-v3
"""
import os

import requests

_API = "https://api.ideogram.ai/v1/ideogram-v3/generate"

# model_id suffix -> Ideogram rendering_speed. QUALITY is slowest/best, TURBO fastest/cheapest.
_SPEEDS = {"turbo": "TURBO", "default": "DEFAULT", "quality": "QUALITY", "flash": "FLASH"}

# Ideogram v3 accepts a fixed set of aspect ratios (WxH form). Map an arbitrary
# width:height to the closest supported ratio so the generic size panel just works.
_RATIOS = {
    "1x1": 1.0, "16x9": 16 / 9, "9x16": 9 / 16, "4x3": 4 / 3, "3x4": 3 / 4,
    "3x2": 3 / 2, "2x3": 2 / 3, "16x10": 16 / 10, "10x16": 10 / 16,
    "3x1": 3.0, "1x3": 1 / 3,
}


def _aspect_ratio(params) -> str:
    """Explicit params['aspect_ratio'] wins; else derive from width/height; else 1x1."""
    explicit = (params.get("aspect_ratio") or "").strip()
    if explicit in _RATIOS:
        return explicit
    try:
        w, h = float(params.get("width") or 0), float(params.get("height") or 0)
        if w > 0 and h > 0:
            target = w / h
            return min(_RATIOS, key=lambda r: abs(_RATIOS[r] - target))
    except (TypeError, ValueError):
        pass
    return "1x1"


def _speed(model_id: str) -> str:
    mid = (model_id or "").lower()
    for suffix, speed in _SPEEDS.items():
        if mid.endswith(suffix):
            return speed
    return "DEFAULT"


def balance() -> dict:
    """No $-balance API on Ideogram's public REST — prepaid balance is dashboard-only
    (ideogram.ai billing page). SEPARATELY: the configured `ideogram_api_key` is currently
    REJECTED — live-probed 2026-07-21 with the exact multipart shape this module sends,
    HTTP 401 "Access denied. Please verify your API Token is valid." (previously a 402
    valid-key-empty-balance per project history — the key was rotated/revoked since).
    Flagged for PRIME to reissue; this backend isn't in the app's dropdown (see
    engine/backends/__init__.py — `ideogram` routes to the working ideogram_web_api
    subscription path instead)."""
    return {"label": "portal-only · key rejected (401) — reissue", "kind": "none"}


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("IDEOGRAM_API_KEY")
    if not key:
        return ["ideogram Error: IDEOGRAM_API_KEY not configured (add it in Settings)."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["ideogram Error: prompt required."]

    files = {
        "prompt": (None, prompt),
        "rendering_speed": (None, _speed(model_id)),
        "style_type": (None, (params.get("style_type") or "AUTO").upper()),
        "num_images": (None, str(int(params.get("num_outputs", 1) or 1))),
    }
    resolution = (params.get("resolution") or "").strip()
    if resolution:
        files["resolution"] = (None, resolution)  # resolution overrides aspect_ratio — mutually exclusive per Ideogram v3 docs
    else:
        files["aspect_ratio"] = (None, _aspect_ratio(params))
    magic_prompt = (params.get("magic_prompt") or "").strip().upper()
    if magic_prompt in ("AUTO", "ON", "OFF"):
        files["magic_prompt"] = (None, magic_prompt)
    if params.get("negative_prompt"):
        files["negative_prompt"] = (None, params["negative_prompt"])
    seed = params.get("seed")
    if seed not in (None, ""):
        try:
            files["seed"] = (None, str(int(seed)))
        except (TypeError, ValueError):
            pass

    if progress:
        progress(f"Submitting to Ideogram ({_speed(model_id)})…")
    try:
        r = requests.post(_API, files=files, headers={"Api-Key": key}, timeout=180)
    except Exception as e:
        return [f"ideogram Error: {type(e).__name__}: {e}"]
    if r.status_code == 401:
        return ["ideogram Error: HTTP 401 — key rejected (check IDEOGRAM_API_KEY)."]
    if r.status_code >= 400:
        return [f"ideogram Error: HTTP {r.status_code} — {r.text[:400]}"]
    try:
        data = r.json()
    except Exception as e:
        return [f"ideogram Error: bad response ({e})"]
    out = [d["url"] for d in (data.get("data") or []) if isinstance(d, dict) and d.get("url")]
    return out or [f"ideogram Error: no image in response (keys: {list(data.keys())})"]
