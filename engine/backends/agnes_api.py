"""AGNES-AI backend (Sapiens AI) — OpenAI-compatible hub at apihub.agnes-ai.com/v1.

Image: POST /v1/images/generations (OpenAI Images shape) → {data:[{url|b64_json}]}. Verified live 2026-07-20.
Video: ASYNC task API — POST /v1/videos to create, then GET /agnesapi?video_id=<id> to poll until
       status=completed (top-level "url" = mp4). Verified live 2026-07-20 (~44s, free at $0/s currently).
Being an OpenAI-compatible hub (litellm), a 400 names the offending field in error.param — so both the
image and the video-create call self-heal by dropping the rejected param and retrying instead of failing.
Key: AGNES_API_KEY (config resolver exports it to env). Auth: Authorization: Bearer.
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

ROOT = "https://apihub.agnes-ai.com"
BASE = ROOT + "/v1"


def _post(path: str, body: dict, key: str, timeout: int):
    req = urllib.request.Request(
        f"{BASE}/{path}", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get(url: str, key: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _rejected_param(err_text: str, body: dict):
    """Name of an OPTIONAL param a 400 (OpenAI error shape) rejected & present in `body` — drop-and-
    retry fuel. Prefers the structured error.param field, falls back to a message regex. Never
    returns model/prompt (essential)."""
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


def _gen_image(model_id: str, params: dict, key: str, progress, cancel_event=None) -> list:
    body = {"model": model_id, "prompt": params.get("prompt", ""),
            "n": int(params.get("num_outputs", 1) or 1)}
    if params.get("width") and params.get("height"):
        body["size"] = f"{int(params['width'])}x{int(params['height'])}"
    if progress:
        progress(f"AGNES {model_id}…")
    # Self-healing: AGNES is an OpenAI-compatible hub (litellm) → a 400 carries error.param naming an
    # unsupported field (drop it and retry); a 429 backs off per Retry-After header. Cap 6 attempts.
    for _attempt in range(6):
        try:
            d = _post("images/generations", body, key, 180)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if progress:
                    progress(f"AGNES rate-limited (429) — backing off for {model_id}")
                if _sleep_for_retry(e.headers, _attempt, cancel_event):
                    return ["AGNES Error: cancelled"]
                continue
            detail = e.read().decode("utf-8", "replace")
            if e.code == 400:
                bad = _rejected_param(detail, body)
                if bad:
                    body.pop(bad, None)
                    if progress:
                        progress(f"AGNES rejected '{bad}' for {model_id} — dropping it and retrying")
                    continue
            return [f"AGNES Error: HTTP {e.code} - {detail[:300]}"]
        out = []
        for item in d.get("data", []):
            if item.get("b64_json"):
                out.append(Image.open(io.BytesIO(base64.b64decode(item["b64_json"]))))
            elif item.get("url"):
                out.append(item["url"])
        return out or ["AGNES Error: no image in response"]
    return ["AGNES Error: too many unsupported-parameter retries"]


def _find_url(obj):
    """Walk common shapes for a media URL (str url, {url}, data.url, videos[].url)."""
    if isinstance(obj, str) and obj.startswith("http"):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("url"), str):
            return obj["url"]
        for k in ("data", "video", "result", "output"):
            u = _find_url(obj.get(k))
            if u:
                return u
        for k in ("videos", "outputs", "data"):
            for it in obj.get(k) or []:
                u = _find_url(it)
                if u:
                    return u
    if isinstance(obj, list):
        for it in obj:
            u = _find_url(it)
            if u:
                return u
    return None


_DONE = ("completed", "succeeded", "success", "done", "finished")
_FAIL = ("failed", "error", "cancelled", "canceled")


def _gen_video(model_id: str, params: dict, key: str, progress, cancel_event) -> list:
    # 1) create the async task — POST /v1/videos (NOT /v1/video/generations; that path 403s via litellm)
    body = {"model": model_id, "prompt": params.get("prompt", "")}
    for src, dst in (("width", "width"), ("height", "height"), ("num_frames", "num_frames"),
                     ("frame_rate", "frame_rate"), ("seed", "seed"), ("negative_prompt", "negative_prompt"),
                     ("aspect_ratio", "aspect_ratio"), ("duration", "duration")):
        if params.get(src) is not None:
            body[dst] = params[src]
    img = params.get("image") or params.get("image_url")  # image-to-video: a PUBLIC image URL
    if img and str(img).startswith("http"):
        body["image"] = str(img)
    # Self-healing create: the create POST speculatively sends width/height/frame_rate/duration/... —
    # drop whichever the model rejects (error.param on a 400) and retry rather than failing the task.
    d = None
    for _attempt in range(6):
        try:
            d = _post("videos", body, key, 60)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if progress:
                    progress(f"AGNES video rate-limited (429) — backing off for {model_id}")
                if _sleep_for_retry(e.headers, _attempt, cancel_event):
                    return ["AGNES Video: cancelled"]
                continue
            detail = e.read().decode("utf-8", "replace")
            if e.code == 400:
                bad = _rejected_param(detail, body)
                if bad:
                    body.pop(bad, None)
                    if progress:
                        progress(f"AGNES video rejected '{bad}' for {model_id} — dropping it and retrying")
                    continue
            return [f"AGNES Video Error: HTTP {e.code} - {detail[:300]}"]
    if d is None:
        return ["AGNES Video Error: too many unsupported-parameter retries"]
    vid = d.get("video_id") or d.get("id") or d.get("task_id")
    if not vid:
        return [f"AGNES Video Error: no task id - {d.get('message') or json.dumps(d)[:300]}"]

    # 2) poll GET /agnesapi?video_id=<id> until done (video ~40-90s; cap ~8 min)
    for _ in range(80):
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return ["AGNES Video: cancelled"]
        try:
            r = _get(f"{ROOT}/agnesapi?video_id={vid}", key)
        except Exception as e:
            r = {"status": "polling", "_err": str(e)}
        st = str(r.get("status", "")).lower()
        if progress:
            progress(f"AGNES video {st or 'working'} {r.get('progress', 0)}%")
        if st in _DONE:
            url = r.get("url") or _find_url(r)
            return [url] if url else [f"AGNES Video Error: completed, no url - {json.dumps(r)[:300]}"]
        if st in _FAIL:
            return [f"AGNES Video Error: {r.get('error') or r.get('message') or st}"]
        time.sleep(6)
    return ["AGNES Video Error: timed out waiting for the task"]


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    key = os.environ.get("AGNES_API_KEY")
    if not key:
        return ["AGNES Error: AGNES_API_KEY not set (add it in Settings)."]
    model_id = model_id or "agnes-image-2.1-flash"
    try:
        if "video" in model_id.lower():
            return _gen_video(model_id, params, key, progress, cancel_event)
        return _gen_image(model_id, params, key, progress, cancel_event)
    except urllib.error.HTTPError as e:
        return [f"AGNES Error: HTTP {e.code} - {e.read().decode('utf-8', 'replace')[:300]}"]
    except Exception as e:
        return [f"AGNES Error: {e}"]


if __name__ == "__main__":  # ponytail check: image path against the live API (video path verified separately)
    k = os.environ.get("AGNES_API_KEY")
    assert k, "set AGNES_API_KEY"
    r = _gen_image("agnes-image-2.0-flash", {"prompt": "a single red apple on white"}, k, print)
    print("image result:", r)
    assert r and isinstance(r[0], str) and r[0].startswith("http"), r
    print("self-check OK")
