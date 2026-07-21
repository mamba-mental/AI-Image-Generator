"""Novita.ai backend — async txt2img (submit -> poll task-result).

Novita permits NSFW by default (`enable_nsfw_detection` is opt-IN); relaxed modes send it
false. Submit returns a task_id; poll until TASK_STATUS_SUCCEED, then read the image URLs.
Key from NOVITA_API_KEY. Ref: https://novita.ai/docs/api-reference/model-apis-txt2img
"""
import json
import os
import time
import urllib.error
import urllib.request

_SUBMIT = "https://api.novita.ai/v3/async/txt2img"
_POLL = "https://api.novita.ai/v3/async/task-result?task_id="

# ---- Spec B §0/AC-1.2/AC-1.7 — the modern "Model APIs" ----
# Novita has NO list endpoint for these (verified absent from both /v3/model and /openai/v1/models,
# per Spec B §0) — each entry here is the sanctioned offline seed, cited to its own doc page.
# `async` picks the submit-then-poll path (shares _POLL above) vs a same-response result.
MODEL_APIS = {
    "seedream-4.0": {"endpoint": "https://api.novita.ai/v3/seedream-4.0", "async": False,
                      "doc": "https://novita.ai/docs/api-reference/model-apis-seedream-4-0"},
    "seedream-4.5": {"endpoint": "https://api.novita.ai/v3/seedream-4.5", "async": False,
                      "doc": "https://novita.ai/docs/api-reference/model-apis-seedream-4-5"},
    "seedream-5.0-lite": {"endpoint": "https://api.novita.ai/v3/seedream-5.0-lite", "async": False,
                           "doc": "https://novita.ai/docs/api-reference/model-apis-seedream-5.0-lite"},
    "qwen-image-txt2img": {"endpoint": "https://api.novita.ai/v3/async/qwen-image-txt2img", "async": True,
                            "doc": "https://novita.ai/docs/api-reference/model-apis-qwen-image-txt2img"},
    "qwen-image-edit": {"endpoint": "https://api.novita.ai/v3/async/qwen-image-edit", "async": True,
                         "doc": "https://novita.ai/docs/api-reference/model-apis-qwen-image-edit"},
    "z-image-turbo": {"endpoint": "https://api.novita.ai/v3/async/z-image-turbo", "async": True,
                       "doc": "https://novita.ai/docs/api-reference/model-apis-z-image-turbo"},
    "z-image-turbo-lora": {"endpoint": "https://api.novita.ai/v3/async/z-image-turbo-lora", "async": True,
                            "doc": "https://novita.ai/docs/api-reference/model-apis-z-image-turbo-lora"},
}


def novita_model_apis() -> list:
    """The Model-APIs catalog for the dropdown's second group ("Novita · Model APIs")."""
    return sorted(MODEL_APIS.keys())


def _post(url, body, key, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get(url, key, timeout=30):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _imgs(r: dict) -> list:
    """Walk both documented shapes: images:[{image_url}] and imgs:[url]."""
    out = []
    for k in ("images", "imgs"):
        for it in (r.get(k) or []):
            if isinstance(it, str) and it.startswith("http"):
                out.append(it)
            elif isinstance(it, dict) and it.get("image_url"):
                out.append(it["image_url"])
    return out


def _build_model_api_body(model_id: str, params: dict) -> dict:
    """The submit payload for one of MODEL_APIS — shape differs per model (each doc-cited), so
    this dispatches on model_id rather than a shared schema like the legacy checkpoint path."""
    prompt = (params.get("prompt") or "").strip()
    size = params.get("size") or f"{int(params.get('width', 1024) or 1024)}*{int(params.get('height', 1024) or 1024)}"
    img = (params.get("_inputs") or {}).get("image") or params.get("image")
    seed = params.get("seed")
    if model_id in ("seedream-4.0", "seedream-4.5", "seedream-5.0-lite"):
        body = {"prompt": prompt, "size": size}
        if params.get("watermark") is not None:
            body["watermark"] = bool(params["watermark"])
        if img:
            body["images"] = [img]
        return body
    if model_id == "qwen-image-txt2img":
        return {"prompt": prompt, "size": size}
    if model_id == "qwen-image-edit":
        body = {"prompt": prompt}
        if img:
            body["image"] = img
        if seed not in (None, ""):
            body["seed"] = int(seed)
        return body
    if model_id == "z-image-turbo":
        body = {"prompt": prompt, "size": size}
        if seed not in (None, ""):
            body["seed"] = int(seed)
        return body
    if model_id == "z-image-turbo-lora":
        body = {"prompt": prompt, "size": size}
        if seed not in (None, ""):
            body["seed"] = int(seed)
        loras = [lo for lo in (params.get("enabled_loras") or []) if lo.get("enabled")]
        if loras:
            body["loras"] = [{"path": lo["url"], "scale": float(lo.get("scale", 1.0))} for lo in loras[:3]]
        return body
    return {"prompt": prompt, "size": size}  # unreachable unless MODEL_APIS grows without a branch


def _poll_task(tid, key, progress=None, cancel_event=None) -> list:
    """Shared submit->poll wait loop (~6-9 min ceiling) — used by the legacy checkpoint path and
    every `async: True` Model API."""
    for _ in range(90):
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return ["novita: cancelled"]
        try:
            r = _get(_POLL + str(tid), key)
        except Exception:
            r = {}
        task = r.get("task") or {}
        st = str(task.get("status", "")).upper()
        if progress:
            progress(f"Novita {st.replace('TASK_STATUS_', '').lower() or 'working'} {task.get('progress_percent', '')}")
        if st in ("TASK_STATUS_SUCCEED", "SUCCEED", "SUCCESS"):
            urls = _imgs(r)
            return urls or [f"novita Error: completed but no image — {json.dumps(r)[:300]}"]
        if st in ("TASK_STATUS_FAILED", "FAILED"):
            return [f"novita Error: {task.get('reason') or 'task failed'}"]
        time.sleep(4)
    return ["novita Error: timed out waiting for the task"]


def _generate_model_api(model_id, params, key, progress=None, cancel_event=None) -> list:
    spec = MODEL_APIS[model_id]
    body = _build_model_api_body(model_id, params)
    if progress:
        progress(f"Submitting to Novita Model API: {model_id}")
    try:
        d = _post(spec["endpoint"], body, key, 60)
    except urllib.error.HTTPError as e:
        return [f"novita Error: HTTP {e.code} — {e.read().decode(errors='ignore')[:400]}"]
    except Exception as e:
        return [f"novita Error: {type(e).__name__}: {e}"]
    if not spec["async"]:
        urls = _imgs(d)
        return urls or [f"novita Error: completed but no image — {json.dumps(d)[:300]}"]
    tid = d.get("task_id") or d.get("id")
    if not tid:
        return [f"novita Error: no task id — {json.dumps(d)[:300]}"]
    return _poll_task(tid, key, progress, cancel_event)


def _build_body(model_id, params):
    """The submit payload this backend POSTs. Shared with the verify harness (asserts the
    enable_nsfw_detection flag lands under `request` + LoRA translation) without a live call."""
    request = {
        "model_name": model_id,
        # Novita hard-limits the prompt to 1–1024 runes; strip + clamp so we never trip its validator.
        "prompt": (params.get("prompt") or "").strip()[:1024],
        "width": int(params.get("width", 1024) or 1024),
        "height": int(params.get("height", 1024) or 1024),
        "image_num": int(params.get("num_outputs", 1) or 1),
        "steps": int(params.get("steps", 25) or 25),
        "guidance_scale": float(params.get("guidance_scale", 7.0) or 7.0),
        "sampler_name": params.get("sampler_name", "Euler a"),
        "seed": int(params.get("seed", -1) or -1),
    }
    if params.get("negative_prompt"):
        request["negative_prompt"] = str(params["negative_prompt"]).strip()[:1024]
    if "enable_nsfw_detection" in params:
        request["enable_nsfw_detection"] = bool(params["enable_nsfw_detection"])
    loras = [lo for lo in (params.get("enabled_loras") or []) if lo.get("enabled")]
    if loras:
        request["loras"] = [{"model_name": lo["url"], "strength": float(lo.get("scale", 1.0))} for lo in loras]
    return {"extra": {"response_image_type": "jpeg"}, "request": request}


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("NOVITA_API_KEY")
    if not key:
        return ["novita Error: NOVITA_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["novita Error: Model not selected."]
    if not (params.get("prompt") or "").strip():
        return ["novita Error: a prompt is required (1–1024 characters)."]
    if model_id in MODEL_APIS:  # E2 — the modern "Model APIs" each have their own bespoke endpoint
        return _generate_model_api(model_id, params, key, progress, cancel_event)
    body = _build_body(model_id, params)
    if progress:
        progress(f"Submitting to Novita: {model_id}")
    try:
        d = _post(_SUBMIT, body, key, 60)
    except urllib.error.HTTPError as e:
        return [f"novita Error: HTTP {e.code} — {e.read().decode(errors='ignore')[:400]}"]
    except Exception as e:
        return [f"novita Error: {type(e).__name__}: {e}"]
    tid = d.get("task_id") or d.get("id")
    if not tid:
        return [f"novita Error: no task id — {json.dumps(d)[:300]}"]
    return _poll_task(tid, key, progress, cancel_event)


if __name__ == "__main__":  # structural self-check, no key needed
    b = _build_body("sd_xl_base_1.0", {"prompt": "x", "enable_nsfw_detection": False,
                                       "enabled_loras": [{"url": "add_detail", "scale": 0.7, "enabled": True}]})
    assert b["request"]["enable_nsfw_detection"] is False, b
    assert b["request"]["loras"][0] == {"model_name": "add_detail", "strength": 0.7}, b
    assert _imgs({"images": [{"image_url": "http://x/1.jpg"}]}) == ["http://x/1.jpg"]
    # E2 — Model APIs body builders (offline, no key needed)
    assert novita_model_apis() == sorted(MODEL_APIS.keys())
    zb = _build_model_api_body("z-image-turbo", {"prompt": "y", "seed": 7, "width": 512, "height": 512})
    assert zb == {"prompt": "y", "size": "512*512", "seed": 7}, zb
    zlb = _build_model_api_body("z-image-turbo-lora", {"prompt": "y", "enabled_loras": [{"url": "u", "scale": 0.6, "enabled": True}]})
    assert zlb["loras"] == [{"path": "u", "scale": 0.6}], zlb
    sb = _build_model_api_body("seedream-4.0", {"prompt": "y", "size": "1K"})
    assert sb == {"prompt": "y", "size": "1K"}, sb
    print("novita self-check OK:", json.dumps(b))
