"""Runware backend — image inference via the single POST /v1 array-of-tasks API.

Runware permits NSFW by default (safety is opt-in via `checkNSFW`); relaxed modes send
`checkNSFW: false`. Models are AIR identifiers ("runware:101@1", "civitai:<id>@<ver>").
One `imageInference` task per call; the response returns `data[].imageURL`.
Key from RUNWARE_API_KEY. Ref: https://runware.ai/docs/image-inference/api-reference
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid

_API = "https://api.runware.ai/v1"

# Optional fields safe to drop when Runware 400s naming one (errors[].parameter; the name is also in
# the message). Never model/positivePrompt/width/height — required (w/h already snapped to a valid grid).
_DROPPABLE = ("negativePrompt", "steps", "CFGScale", "seed", "checkNSFW", "lora")


def _snap64(v, default=1024) -> int:
    """Runware width/height must be in [512, 2048] AND divisible by 64 (doc / sdk-python schema)."""
    v = min(2048, max(512, int(v or default)))
    return round(v / 64) * 64


def _drop_rejected(container: dict, err_text: str, droppable) -> str:
    """The first droppable key present in `container` and named in the 4xx body, else ''.
    Word-boundary + case-insensitive so 'seed' can't hit a substring and 'CFGScale' still matches."""
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


def _build_task(model_id, params, task_uuid="test"):
    """The imageInference task dict this backend POSTs. Shared by generate() + the verify harness
    so the request shape (incl. checkNSFW + LoRA translation) is asserted without a live call."""
    task = {
        "taskType": "imageInference",
        "taskUUID": task_uuid,
        "model": model_id,
        "positivePrompt": params.get("prompt", ""),
        # Doc ranges (sdk-python schema): width/height 512–2048 divisible by 64; snap so a raw UI
        # value never 400s (width is required — the drop-retry can't recover it).
        "width": _snap64(params.get("width", 1024)),
        "height": _snap64(params.get("height", 1024)),
        "numberResults": int(params.get("num_outputs", 1) or 1),
        "outputType": "URL",
    }
    if params.get("negative_prompt"):
        task["negativePrompt"] = params["negative_prompt"]
    if params.get("steps") not in (None, ""):
        task["steps"] = min(100, max(1, int(params["steps"])))            # doc range [1, 100]
    if params.get("guidance_scale") not in (None, ""):
        task["CFGScale"] = min(30.0, max(0.0, float(params["guidance_scale"])))  # doc range [0, 30]
    if params.get("seed") not in (None, ""):
        task["seed"] = int(params["seed"])
    if "checkNSFW" in params:
        task["checkNSFW"] = bool(params["checkNSFW"])
    # LoRA (Phase 4): enabled_loras -> Runware lora:[{model, weight}]
    loras = [lo for lo in (params.get("enabled_loras") or []) if lo.get("enabled")]
    if loras:
        task["lora"] = [{"model": lo["url"], "weight": float(lo.get("scale", 1.0))} for lo in loras]
    return task


def _parse(d: dict) -> list:
    rows = d.get("data") if isinstance(d, dict) else None
    out = [it["imageURL"] for it in (rows or []) if isinstance(it, dict) and it.get("imageURL")]
    if out:
        return out
    errs = (d.get("errors") if isinstance(d, dict) else None) or []
    msg = (errs[0].get("message") if errs and isinstance(errs[0], dict) else None) \
        or (d.get("message") if isinstance(d, dict) else None)
    return [f"runware Error: {msg or 'no image in response'}"]


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("RUNWARE_API_KEY")
    if not key:
        return ["runware Error: RUNWARE_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["runware Error: Model not selected."]
    if not params.get("prompt"):
        return ["runware Error: prompt required."]
    task = _build_task(model_id, params, task_uuid=str(uuid.uuid4()))
    if progress:
        progress(f"Submitting to Runware: {model_id}")
    # Self-healing: Runware 400s a per-model-unsupported field, naming it in errors[].parameter (and
    # the message). Drop the named optional field and retry, so schema quirks resolve without a
    # hardcoded per-model list. On 429 wait per the server header (else backoff 2→30s) and retry.
    backoff = 2.0
    for _attempt in range(6):
        req = urllib.request.Request(
            _API, data=json.dumps([task]).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            raw = urllib.request.urlopen(req, timeout=180).read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")
            if e.code == 429:
                if _sleep_cancellable(_retry_wait(e.headers, backoff), cancel_event):
                    return ["runware: cancelled"]
                backoff = min(30.0, backoff * 2)
                continue
            if e.code in (400, 422):
                bad = _drop_rejected(task, msg, _DROPPABLE)
                if bad:
                    task.pop(bad, None)
                    if progress:
                        progress(f"Runware rejected '{bad}' for {model_id} — dropping it and retrying")
                    continue
            return [f"runware Error: HTTP {e.code} — {msg[:400]}"]
        except Exception as e:
            return [f"runware Error: {type(e).__name__}: {e}"]
        try:
            return _parse(json.loads(raw))
        except Exception as e:
            return [f"runware Error: bad response ({e})"]
    return ["runware Error: too many retries (rate-limit or unsupported param)"]


if __name__ == "__main__":  # structural self-check, no key needed
    t = _build_task("runware:101@1", {"prompt": "x", "checkNSFW": False, "steps": 500, "width": 1000,
                                      "enabled_loras": [{"url": "civitai:1@2", "scale": 0.8, "enabled": True}]})
    assert t["checkNSFW"] is False and t["lora"][0] == {"model": "civitai:1@2", "weight": 0.8}, t
    assert t["steps"] == 100 and t["width"] == 1024, t          # clamped + snapped to the /64 grid
    assert _snap64(100) == 512 and _snap64(5000) == 2048 and _snap64(1000) == 1024
    assert _parse({"data": [{"imageURL": "http://x/1.png"}]}) == ["http://x/1.png"]
    assert _drop_rejected({"CFGScale": 7.0},
                          '{"errors":[{"parameter":"CFGScale","message":"unsupported"}]}', _DROPPABLE) == "CFGScale"
    assert _drop_rejected({"positivePrompt": "x"}, "positivePrompt too long", _DROPPABLE) == ""
    assert _retry_wait({"Retry-After": "5"}, 2.0) == 5.0 and _retry_wait({}, 2.0) == 2.0
    assert _sleep_cancellable(9, type("C", (), {"is_set": staticmethod(lambda: True)})()) is True
    print("runware self-check OK:", json.dumps(t))
