"""AGNES-AI backend (Sapiens AI) — OpenAI-compatible hub at apihub.agnes-ai.com/v1.

Image: POST /v1/images/generations (OpenAI Images shape) → {data:[{url|b64_json}]}. Verified live 2026-07-20.
Video: ASYNC task API — POST /v1/videos to create, then GET /agnesapi?video_id=<id> to poll until
       status=completed (top-level "url" = mp4). Verified live 2026-07-20 (~44s, free at $0/s currently).
Key: AGNES_API_KEY (config resolver exports it to env). Auth: Authorization: Bearer.
"""
import base64
import io
import json
import os
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


def _gen_image(model_id: str, params: dict, key: str, progress) -> list:
    body = {"model": model_id, "prompt": params.get("prompt", ""),
            "n": int(params.get("num_outputs", 1) or 1)}
    if params.get("width") and params.get("height"):
        body["size"] = f"{int(params['width'])}x{int(params['height'])}"
    if progress:
        progress(f"AGNES {model_id}…")
    d = _post("images/generations", body, key, 180)
    out = []
    for item in d.get("data", []):
        if item.get("b64_json"):
            out.append(Image.open(io.BytesIO(base64.b64decode(item["b64_json"]))))
        elif item.get("url"):
            out.append(item["url"])
    return out or ["AGNES Error: no image in response"]


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
                     ("frame_rate", "frame_rate"), ("seed", "seed"), ("negative_prompt", "negative_prompt")):
        if params.get(src) is not None:
            body[dst] = params[src]
    img = params.get("image") or params.get("image_url")  # image-to-video: a PUBLIC image URL
    if img and str(img).startswith("http"):
        body["image"] = str(img)
    try:
        d = _post("videos", body, key, 60)
    except urllib.error.HTTPError as e:
        return [f"AGNES Video Error: HTTP {e.code} - {e.read().decode('utf-8', 'replace')[:300]}"]
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
        return _gen_image(model_id, params, key, progress)
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
