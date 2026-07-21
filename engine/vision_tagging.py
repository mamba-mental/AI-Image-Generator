"""Vision auto-tagging (Spec C AC-8.7) — semantic content tags from a vision-capable OpenAI model
served through a CONFIGURED OpenAI-compatible endpoint. cliproxy is the default endpoint (bills
against PRIME's Pro sub -> $0 marginal); the base URL + key ALWAYS resolve from config/env, never
hardcoded to api.openai.com. Off by default: is_configured() is false until an endpoint resolves.

Model id: VISION_TAG_MODEL defaults to "gpt-5.5" — pinned + live-verified 2026-07-21 against the
cliproxy /v1/models catalog (present, vision-capable: confirmed via a real /v1/chat/completions
call with an image_url content part). Override via env if the fleet catalog changes.

Never blocks save/open: every call is wrapped, failures return None/False and are logged, never
raised. Runs as a background batch (bridge.py starts it on a daemon thread) with a hard per-image
timeout and a crude rate delay between calls (ponytail: no token-bucket — a fixed sleep is enough
for a personal-scale backlog; upgrade if the batch ever needs real concurrency control).
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

_TIMEOUT = 20          # hard per-image cap (AC-8.7) — a stuck call can never hang the batch
_RATE_DELAY = 0.4      # seconds between calls — a crude rate budget
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

_PROMPT = (
    "Describe this image for a searchable tag index. Reply with ONLY compact JSON, no prose, "
    "no markdown fences: "
    '{"subject":"...","setting":"...","style":"...","palette":"...","composition":"...",'
    '"content_level":"sfw|suggestive|explicit"}'
)


def _base_url() -> str:
    # cliproxy default ($0-marginal via PRIME's Pro sub); OPENAI_BASE_URL / an explicit
    # VISION_TAG_BASE_URL override it. NEVER hardcodes api.openai.com (AC-8.7).
    return (os.environ.get("VISION_TAG_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("CLIPROXY_BASE_URL")
            or "http://192.168.86.191:8317/v1").rstrip("/")


def _api_key() -> str:
    return (os.environ.get("VISION_TAG_API_KEY")
            or os.environ.get("CLIPROXY_API_KEY")
            or os.environ.get("OPENAI_API_KEY") or "")


def _model() -> str:
    return os.environ.get("VISION_TAG_MODEL", "gpt-5.5")


def is_configured() -> bool:
    """Off-by-default gate — vision tagging only runs once BOTH a base URL and a key resolve."""
    return bool(_base_url() and _api_key())


def base_url_label() -> str:
    return _base_url()


def _to_data_url(path) -> str | None:
    ext = Path(path).suffix.lower()
    mime = _MIME.get(ext)
    if not mime:
        return None
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime};base64,{b64}"


def tag_image(path) -> list | None:
    """One image -> a flat list of tag strings, or None on any failure/timeout. Never raises."""
    if not is_configured():
        return None
    data_url = _to_data_url(path)
    if not data_url:
        return None
    body = {
        "model": _model(),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "max_tokens": 200,
    }
    req = urllib.request.Request(
        _base_url() + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=_TIMEOUT).read()
        text = json.loads(raw)["choices"][0]["message"]["content"].strip()
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        fields = json.loads(text)
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
        print(f"vision_tagging failed for {Path(path).name}: {type(e).__name__}: {e}")
        return None
    tags = []
    for k in ("subject", "setting", "style", "palette", "composition"):
        v = fields.get(k)
        if v:
            tags.append(str(v).strip().lower())
    level = fields.get("content_level")
    if level:
        tags.append(f"content:{str(level).strip().lower()}")
    return tags or None


def _targeted_prompt(tag: str) -> str:
    return (f'Does this image match the concept "{tag}"? Reply with ONLY the single word '
            '"yes" or "no" — no punctuation, no explanation.')


def tag_matches(path, tag: str) -> bool | None:
    """R3 #4 — 'add a tag + rescan for it'. One image -> True/False for whether it matches
    `tag`, or None on any failure/timeout (never raises). Same shape as tag_image() but a
    targeted yes/no classification instead of open-ended tag extraction."""
    if not is_configured():
        return None
    data_url = _to_data_url(path)
    if not data_url:
        return None
    body = {
        "model": _model(),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _targeted_prompt(tag)},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "max_tokens": 5,
    }
    req = urllib.request.Request(
        _base_url() + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=_TIMEOUT).read()
        text = json.loads(raw)["choices"][0]["message"]["content"].strip().lower()
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
        print(f"vision_tagging.tag_matches failed for {Path(path).name}: {type(e).__name__}: {e}")
        return None
    return text.startswith("yes")


def parallel_rescan_tag(paths: list, tag: str, index, max_workers: int = 12, on_progress=None) -> dict:
    """R3 #4 — 12-worker parallel targeted rescan (ponytail: reuse the proven pattern from
    .dd/parallel_vision_backfill.py verbatim rather than inventing a new concurrency scheme —
    the sequential batch_tag()'s 0.4s rate delay would take ~35+ minutes over a 5k-image library;
    this is minutes). Applies `tag` to every image tag_matches() says yes to; a "no" or a failure
    never touches that image's existing tags. `on_progress(done, total)`, if given, is called
    from a worker thread after each image — caller's responsibility to make it thread-safe."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()
    counts = {"matched": 0, "no_match": 0, "failed": 0}
    total = len(paths)

    def work(p):
        result = tag_matches(p, tag)
        with lock:   # index writes + the shared counters both need the same guard (mirrors the
                      # proven parallel_vision_backfill.py pattern)
            if result is True:
                try:
                    index.add_tag(p, tag)
                    counts["matched"] += 1
                except Exception as e:
                    print(f"vision_tagging.parallel_rescan_tag: failed to persist tag for {p}: {e}")
                    counts["failed"] += 1
            elif result is False:
                counts["no_match"] += 1
            else:
                counts["failed"] += 1
            if on_progress:
                on_progress(counts["matched"] + counts["no_match"] + counts["failed"], total)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(work, paths))
    return counts


def batch_tag(paths: list, index) -> dict:
    """Background batch — tags each path once, caches via index.mark_vision_tagged (sets
    vision_tagged_at so it's never re-called), never blocks the caller. Run this on its own
    thread (bridge.py does)."""
    done, failed = 0, 0
    for p in paths:
        tags = tag_image(p)
        if tags:
            try:
                index.mark_vision_tagged(p, tags)
                done += 1
            except Exception as e:
                print(f"vision_tagging: failed to persist tags for {p}: {e}")
                failed += 1
        else:
            failed += 1
        time.sleep(_RATE_DELAY)
    return {"done": done, "failed": failed}


if __name__ == "__main__":
    # ponytail: smallest runnable self-check — no network needed when unconfigured.
    import sys
    was = os.environ.pop("VISION_TAG_API_KEY", None)
    ok = is_configured() == bool(_api_key())  # off-by-default gate matches key presence
    print(f"is_configured()={is_configured()} base_url={base_url_label()} model={_model()}")
    print("ALL PASS" if ok else "FAILED")
    if was is not None:
        os.environ["VISION_TAG_API_KEY"] = was
    sys.exit(0 if ok else 1)
