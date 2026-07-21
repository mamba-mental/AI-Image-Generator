"""cliproxy backend — image generation via the self-hosted CLIProxyAPI OpenAI-compatible endpoint
(HP2 :8317/v1/images/generations).

CLIProxy exposes ~500 models, but only a fixed allowlist is routable through
/v1/images/generations — everything else (Imagen, qwen-image, gemini-image, ...) 400s there and
would need the chat-completions image-modality path instead (out of scope for this endpoint).
The allowlist is authoritative straight from the proxy's own 400 body (live-probed 2026-07-21):
"Use gpt-image-1.5, gpt-image-2, grok-imagine-image, grok-imagine-image-quality, or a configured
openai-compatibility image model." `grok-imagine-image-quality` was previously missing from the
app's model list/comment here. Returns b64_json -> PIL (or url).
Key = CLIPROXY_API_KEY (the CLIProxy client key, env / credential store). Endpoint overridable via CLIPROXY_BASE_URL.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO

from PIL import Image

from .openai_api import _size  # cliproxy is a pass-through to the same gpt-image family (§14 cookbook)

_BASE = os.environ.get("CLIPROXY_BASE_URL", "http://192.168.86.191:8317/v1").rstrip("/")
_API = _BASE + "/images/generations"
_MODELS_API = _BASE + "/models"

# Authoritative allowlist (see module docstring) — the only ids /v1/images/generations accepts today.
_KNOWN_IMAGE_MODELS = ("gpt-image-1.5", "gpt-image-2", "grok-imagine-image", "grok-imagine-image-quality")


def cliproxy_models() -> list:
    """Live-discover which of the known-generatable image ids the proxy currently serves (GET
    /v1/models), so a renamed/retired id on the proxy side doesn't get offered to the dropdown.
    Falls back to the static allowlist if the discovery call fails (proxy down/unreachable)."""
    key = os.environ.get("CLIPROXY_API_KEY")
    if not key:
        return list(_KNOWN_IMAGE_MODELS)
    req = urllib.request.Request(_MODELS_API, headers={"Authorization": f"Bearer {key}"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
    except Exception:
        return list(_KNOWN_IMAGE_MODELS)
    live_ids = {m.get("id") for m in (d.get("data") or []) if isinstance(m, dict)}
    return [m for m in _KNOWN_IMAGE_MODELS if m in live_ids] or list(_KNOWN_IMAGE_MODELS)


def balance() -> dict:
    """cliproxy is PRIME's own self-hosted router (HP2), not a billed service — it has no
    spend ledger of its own (the providers *behind* it have theirs, covered by their own
    balance() where real). Its remote-management API exists but is gated by a separate
    bcrypt secret-key not in this app's key store — not a per-request $-balance anyway."""
    return {"label": "n/a · self-hosted gateway", "kind": "info"}


def _parse(d: dict) -> list:
    out = []
    for item in (d.get("data") or []):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            try:
                out.append(Image.open(BytesIO(base64.b64decode(item["b64_json"]))))
            except Exception as e:
                out.append(f"cliproxy Error: bad image data ({e})")
        elif item.get("url"):
            out.append(item["url"])
    if not out:
        err = (d.get("error") or {}).get("message")
        return [f"cliproxy Error: {err or 'no image in response'}"]
    return out


def generate(model_id, params, progress=None, cancel_event=None) -> list:
    key = os.environ.get("CLIPROXY_API_KEY")
    if not key:
        return ["cliproxy Error: CLIPROXY_API_KEY not configured (add it in Settings)."]
    if not model_id:
        return ["cliproxy Error: Model not selected."]
    prompt = params.get("prompt", "")
    if not prompt:
        return ["cliproxy Error: prompt required."]

    body = {"model": model_id, "prompt": prompt, "n": int(params.get("num_outputs", 1) or 1)}
    size = _size(params, model_id)  # snap to the 3 legal gpt-image enums before send (§14 Bug #1)
    if size:
        body["size"] = size
    for opt in ("quality", "background", "output_format"):
        if params.get(opt):
            body[opt] = params[opt]
    if progress:
        progress(f"Submitting to cliproxy: {model_id}")
    req = urllib.request.Request(
        _API, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=180).read()
    except urllib.error.HTTPError as e:
        return [f"cliproxy Error: HTTP {e.code} — {e.read().decode(errors='ignore')[:400]}"]
    except Exception as e:
        return [f"cliproxy Error: {type(e).__name__}: {e}"]
    try:
        return _parse(json.loads(raw))
    except Exception as e:
        return [f"cliproxy Error: bad response ({e})"]
