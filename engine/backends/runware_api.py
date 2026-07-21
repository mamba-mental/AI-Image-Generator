"""Runware backend — image inference via the single POST /v1 array-of-tasks API.

Runware permits NSFW by default (safety is opt-in via `checkNSFW`); relaxed modes send
`checkNSFW: false`. Models are AIR identifiers ("runware:101@1", "civitai:<id>@<ver>").
One `imageInference` task per call; the response returns `data[].imageURL`.
Key from RUNWARE_API_KEY. Ref: https://runware.ai/docs/image-inference/api-reference
"""
import json
import os
import urllib.error
import urllib.request
import uuid

_API = "https://api.runware.ai/v1"


def _build_task(model_id, params, task_uuid="test"):
    """The imageInference task dict this backend POSTs. Shared by generate() + the verify harness
    so the request shape (incl. checkNSFW + LoRA translation) is asserted without a live call."""
    task = {
        "taskType": "imageInference",
        "taskUUID": task_uuid,
        "model": model_id,
        "positivePrompt": params.get("prompt", ""),
        "width": int(params.get("width", 1024) or 1024),
        "height": int(params.get("height", 1024) or 1024),
        "numberResults": int(params.get("num_outputs", 1) or 1),
        "outputType": "URL",
    }
    if params.get("negative_prompt"):
        task["negativePrompt"] = params["negative_prompt"]
    if params.get("steps") not in (None, ""):
        task["steps"] = int(params["steps"])
    if params.get("guidance_scale") not in (None, ""):
        task["CFGScale"] = float(params["guidance_scale"])
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
    req = urllib.request.Request(
        _API, data=json.dumps([task]).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        return [f"runware Error: HTTP {e.code} — {e.read().decode(errors='ignore')[:400]}"]
    except Exception as e:
        return [f"runware Error: {type(e).__name__}: {e}"]
    try:
        return _parse(json.loads(raw))
    except Exception as e:
        return [f"runware Error: bad response ({e})"]


if __name__ == "__main__":  # structural self-check, no key needed
    t = _build_task("runware:101@1", {"prompt": "x", "checkNSFW": False,
                                      "enabled_loras": [{"url": "civitai:1@2", "scale": 0.8, "enabled": True}]})
    assert t["checkNSFW"] is False and t["lora"][0] == {"model": "civitai:1@2", "weight": 0.8}, t
    assert _parse({"data": [{"imageURL": "http://x/1.png"}]}) == ["http://x/1.png"]
    print("runware self-check OK:", json.dumps(t))
