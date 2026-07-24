"""NVIDIA NIM image backend — POST https://ai.api.nvidia.com/v1/genai/{model}.

Response verified live 2026-07-03: {"artifacts":[{"base64", "finishReason", "seed"}]}.
Note: NVIDIA image endpoints can cold-start slowly (30-120s) — timeout is generous.
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

# The real NIM ImageRequest schema (DOC-RAW, research/2026-07-21_provider-params-matrix.md §4) --
# width AND height are independently constrained to this SAME 10-value enum, not a free range.
_WH_ENUM = (768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344)

# Optional params safe to drop when a NIM 422 names them (never prompt/width/height — required and
# already enum-snapped). Ordered most-peripheral first for the rare multi-param error.
_DROPPABLE = ("seed", "mode", "cfg_scale", "steps")


def _snap_wh(v) -> int:
    v = int(v or 1024)
    return min(_WH_ENUM, key=lambda e: abs(e - v))


def _drop_rejected(container: dict, err_text: str, droppable) -> str:
    """The first droppable key present in `container` and named in the 4xx body, else ''.
    Word-boundary + case-insensitive so 'seed' can't hit a substring like 'seeded'."""
    low = err_text.lower()
    for k in droppable:
        if k in container and re.search(r"\b" + re.escape(k.lower()) + r"\b", low):
            return k
    return ""


def _retry_wait(headers, fallback):
    """Seconds to wait before retrying a 429 — server's Retry-After/reset header, else `fallback`.
    Caps at 30s; a header carrying an epoch reset (>1e6) is converted to a delta."""
    for h in ("Retry-After", "X-RateLimit-Reset", "x-ratelimit-reset"):
        v = headers.get(h) if headers else None
        if not v:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n > 1e6:
            n -= time.time()
        return max(1.0, min(n, 30.0))
    return max(1.0, min(fallback, 30.0))


def _sleep_cancellable(secs, cancel_event=None) -> bool:
    """Sleep up to `secs`, waking every 0.5s to honor a cancel. Returns True if cancelled."""
    end = time.time() + secs
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            return False
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return True
        time.sleep(min(0.5, remaining))


def balance() -> dict:
    """No $-balance API exists on integrate.api.nvidia.com or ai.api.nvidia.com — probed
    2026-07-21 (research/2026-07-21_provider-balance-apis.md): /v1/models 200s (key valid)
    but no credits/balance field or endpoint anywhere. Credits are tracked only at
    build.nvidia.com. Portal-only by design, not an engineering gap."""
    return {"label": "portal-only · build.nvidia.com", "kind": "none"}


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        return ["NVIDIA Error: NVIDIA_API_KEY not set (add it in Settings)."]
    if not model_id:
        return ["NVIDIA Error: model not selected."]

    cfg = float(params.get("guidance_scale", params.get("cfg_scale", 3.5)))
    steps = int(params.get("num_inference_steps", params.get("steps", 25)))
    body = {
        "prompt": params.get("prompt", ""),
        "mode": "base",
        "cfg_scale": min(9.0, max(1.01, cfg)),   # real range (1.0, 9.0] exclusive-min — §14 cookbook
        "width": _snap_wh(params.get("width", 1024)),
        "height": _snap_wh(params.get("height", 1024)),
        "steps": min(100, max(5, steps)),        # real range 5-100
    }
    if params.get("seed") is not None:
        body["seed"] = int(params["seed"])
    # NEVER send negative_prompt — not in the ImageRequest schema for FLUX.1-dev/SD3.5-large
    # (§14 cookbook Bug #2); the key must be absent, not null/empty.

    # FLUX.1-schnell is guidance-distilled and rejects cfg_scale (422). Strip it up front so the
    # common schnell path skips a wasted round-trip; the generic 422-retry below still covers any
    # other model that rejects any other param.
    if "schnell" in model_id.lower():
        body.pop("cfg_scale", None)

    if progress:
        progress(f"NVIDIA {model_id} (may cold-start)…")
    url = f"https://ai.api.nvidia.com/v1/genai/{model_id}"
    # Self-healing: NIM rejects an unsupported/unknown field with HTTP 422
    # ({"detail":[{"loc":["body","<param>"],...}]}). Drop the named optional param and retry, so a
    # model's schema quirks resolve without maintaining a hardcoded per-model list. On 429 (rate
    # limit) wait per the server header (else exponential backoff 2→30s) and retry.
    backoff = 2.0
    for _attempt in range(6):
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                     "Content-Type": "application/json"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=200).read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            if e.code == 429:
                if _sleep_cancellable(_retry_wait(e.headers, backoff), cancel_event):
                    return ["NVIDIA: cancelled"]
                backoff = min(30.0, backoff * 2)
                continue
            if e.code in (400, 422):
                bad = _drop_rejected(body, msg, _DROPPABLE)
                if bad:
                    body.pop(bad, None)
                    if progress:
                        progress(f"NVIDIA rejected '{bad}' for {model_id} — dropping it and retrying")
                    continue
            return [f"NVIDIA Error: HTTP {e.code} - {msg[:300]}"]
        except Exception as e:
            return [f"NVIDIA Error: {e}"]

        out = []
        for art in d.get("artifacts", []):
            if art.get("base64"):
                out.append(Image.open(io.BytesIO(base64.b64decode(art["base64"]))))
        return out or [f"NVIDIA Error: no artifact in response (keys: {list(d.keys())})"]
    return ["NVIDIA Error: too many retries (rate-limit or unsupported param)"]


if __name__ == "__main__":  # structural self-check, no key needed
    assert _drop_rejected({"cfg_scale": 3.5, "seed": 1},
                          '{"detail":[{"loc":["body","cfg_scale"],"msg":"x"}]}', _DROPPABLE) == "cfg_scale"
    assert _drop_rejected({"steps": 4}, "prompt too long", _DROPPABLE) == ""      # non-droppable named
    assert _drop_rejected({"seed": 1}, "seeded output is fine", _DROPPABLE) == "" # \bseed\b ≠ 'seeded'
    assert _snap_wh(1000) in _WH_ENUM
    assert _retry_wait({"Retry-After": "5"}, 2.0) == 5.0 and _retry_wait({}, 2.0) == 2.0
    assert _retry_wait({"X-RateLimit-Reset": "999999999999"}, 2.0) <= 30.0   # epoch → clamped delta
    assert _sleep_cancellable(9, type("C", (), {"is_set": staticmethod(lambda: True)})()) is True
    print("nvidia self-check OK")
