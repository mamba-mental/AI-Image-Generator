"""Ideogram (subscription) backend — generates through ideogram.com's INTERNAL web API
using PRIME's logged-in Firebase session, so it spends his Plus **subscription** credits.

This is deliberately separate from the `ideogram` backend, which uses Ideogram's public
REST API — a SEPARATELY-BILLED prepaid balance (per Ideogram's own docs, subscription and
API accounts are distinct). The subscription's priority credits can only be spent via the
web app, so this backend replays the web app's own calls:

  1. Firebase refresh-token -> id_token   (securetoken.googleapis.com, needs Origin/Referer)
  2. POST /api/images/sample              (Bearer id_token)          -> request_id
  3. poll GET /api/g/u/c?user_id=<handle> (Bearer)                   -> is_completed + response_ids
  4. download https://ideogram.ai/assets/image/balanced/response/<response_id>@2k  (public)

Auth + identity live in config.json (gitignored): ideogram_web_refresh_token,
ideogram_web_api_key, ideogram_web_user_handle, ideogram_web_user_id.

UNOFFICIAL / session-based: if Ideogram changes their web internals, or the refresh token
is revoked (password change / "log out everywhere"), re-extract it via the setup capture.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO

from PIL import Image

from engine import config as _config

_BASE = "https://ideogram.ai"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122 Safari/537.36")
_WEB = {"Origin": _BASE, "Referer": _BASE + "/", "User-Agent": _UA}
_POLL_TIMEOUT_S = 180


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


def _auth_fields():
    c = _config.load()
    return (c.get("ideogram_web_refresh_token"), c.get("ideogram_web_api_key"),
            c.get("ideogram_web_user_handle"), c.get("ideogram_web_user_id"))


def _refresh(refresh_token, api_key):
    """Firebase refresh_token -> fresh id_token. Returns (id_token, maybe_new_refresh_token)."""
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}).encode()
    req = urllib.request.Request(
        "https://securetoken.googleapis.com/v1/token?key=" + api_key, data=body,
        headers={**_WEB, "Content-Type": "application/x-www-form-urlencoded"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return d["id_token"], d.get("refresh_token")


def _api(token, path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        _BASE + path, data=data, method=method,
        headers={**_WEB, "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def balance() -> dict:
    """No $-balance concept — this backend spends PRIME's Ideogram Plus **subscription**
    via the logged-in web session (priority-credit allotment, not a prepaid metered
    wallet). See module docstring for why this is deliberately separate from the
    `ideogram-api` prepaid-balance backend."""
    return {"label": "n/a · subscription (ideogram.ai)", "kind": "info"}


def _download_image(response_id):
    url = f"{_BASE}/assets/image/balanced/response/{response_id}@2k"
    req = urllib.request.Request(url, headers=_WEB)
    data = urllib.request.urlopen(req, timeout=90).read()
    return Image.open(BytesIO(data))


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    refresh_token, api_key, handle, user_id = _auth_fields()
    if not refresh_token or not api_key or not handle:
        return ["ideogram-web Error: not connected — run the Ideogram subscription setup "
                "(missing refresh token / api key / handle in config)."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["ideogram-web Error: prompt required."]

    # 1. auth
    if progress:
        progress("authenticating (subscription session)…")
    try:
        token, new_rt = _refresh(refresh_token, api_key)
    except urllib.error.HTTPError as e:
        return [f"ideogram-web Error: auth refresh HTTP {e.code} — session likely expired; re-extract token."]
    except Exception as e:
        return [f"ideogram-web Error: auth {type(e).__name__}: {e}"]
    if new_rt and new_rt != refresh_token:  # persist a rotated refresh token so it never goes stale
        try:
            c = _config.load()
            c["ideogram_web_refresh_token"] = new_rt
            _config.save(c)
        except Exception:
            pass

    # 2. submit (payload mirrors the web app's own /api/images/sample call)
    w = int(params.get("width") or 1024)
    h = int(params.get("height") or 1024)
    payload = {
        "prompt": prompt,
        "user_id": user_id,
        "private": bool(params.get("private", False)),
        "model_version": "AUTO",
        "model_uri": "model/AUTO/version/0",
        "use_autoprompt_option": "AUTO",
        "sampling_speed": -2,
        "character_reference_parents": [],
        "product_reference_parents": [],
        "resolution": {"width": w, "height": h},
        "num_images": int(params.get("num_outputs", 1) or 1),
        "style_type": (params.get("style_type") or "AUTO").upper(),
    }
    if progress:
        progress("submitting to Ideogram (subscription)…")
    # 429 backoff: a rate-limited submit created NO generation, so retrying is spend-safe (won't
    # double-charge the subscription). Poll-loop 429s are already tolerated by its except: continue.
    sub = None
    for attempt in range(6):
        if cancel_event is not None and cancel_event.is_set():
            return ["ideogram-web Error: cancelled."]
        try:
            sub = _api(token, "/api/images/sample", "POST", payload)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 5:
                if progress:
                    progress("Ideogram rate-limited (429) — backing off…")
                time.sleep(_retry_wait(e.headers, 2 ** (attempt + 1)))
                continue
            detail = e.read()[:200].decode("utf-8", "replace")
            return [f"ideogram-web Error: submit HTTP {e.code} — {detail}"]
        except Exception as e:
            return [f"ideogram-web Error: submit {type(e).__name__}: {e}"]
    request_id = sub.get("request_id")
    if not request_id:
        return [f"ideogram-web Error: no request_id in response (keys: {list(sub.keys())})"]

    # 3. poll the user's creations until this request completes
    creations_path = (f"/api/g/u/c?user_id={urllib.parse.quote(handle)}"
                      "&filters=everything&all_privacy=true")
    waited = 0
    while waited < _POLL_TIMEOUT_S:
        if cancel_event is not None and cancel_event.is_set():
            return ["ideogram-web Error: cancelled."]
        time.sleep(4)
        waited += 4
        try:
            cre = _api(token, creations_path)
        except Exception:
            continue
        row = next((r for r in (cre.get("results") or []) if r.get("request_id") == request_id), None)
        if row is None:
            if progress:
                progress(f"generating… ({waited}s)")
            continue
        if row.get("is_errored"):
            return ["ideogram-web Error: generation errored server-side."]
        resp_ids = [x.get("response_id") for x in (row.get("responses") or []) if x.get("response_id")]
        if row.get("is_completed") and resp_ids:
            # 4. download the finished images (public @2k assets)
            out = []
            for i, rid in enumerate(resp_ids):
                if progress:
                    progress(f"downloading image {i + 1}/{len(resp_ids)}…")
                try:
                    out.append(_download_image(rid))
                except Exception as e:
                    out.append(f"ideogram-web Error: download {rid} failed ({type(e).__name__}: {e})")
            return out
        if progress:
            progress(f"generating… ({waited}s, {int(row.get('completion_percentage', 0) * 100)}%)")
    return ["ideogram-web Error: timed out waiting for generation (180s)."]
