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


def _build_body(model_id, params):
    """The submit payload this backend POSTs. Shared with the verify harness (asserts the
    enable_nsfw_detection flag lands under `request` + LoRA translation) without a live call."""
    request = {
        "model_name": model_id,
        "prompt": params.get("prompt", ""),
        "width": int(params.get("width", 1024) or 1024),
        "height": int(params.get("height", 1024) or 1024),
        "image_num": int(params.get("num_outputs", 1) or 1),
        "steps": int(params.get("steps", 25) or 25),
        "guidance_scale": float(params.get("guidance_scale", 7.0) or 7.0),
        "sampler_name": params.get("sampler_name", "Euler a"),
        "seed": int(params.get("seed", -1) or -1),
    }
    if params.get("negative_prompt"):
        request["negative_prompt"] = params["negative_prompt"]
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
    if not params.get("prompt"):
        return ["novita Error: prompt required."]
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

    for _ in range(90):  # ~6-9 min ceiling
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


if __name__ == "__main__":  # structural self-check, no key needed
    b = _build_body("sd_xl_base_1.0", {"prompt": "x", "enable_nsfw_detection": False,
                                       "enabled_loras": [{"url": "add_detail", "scale": 0.7, "enabled": True}]})
    assert b["request"]["enable_nsfw_detection"] is False, b
    assert b["request"]["loras"][0] == {"model_name": "add_detail", "strength": 0.7}, b
    assert _imgs({"images": [{"image_url": "http://x/1.jpg"}]}) == ["http://x/1.jpg"]
    print("novita self-check OK:", json.dumps(b))
