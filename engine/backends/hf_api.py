"""Hugging Face backend — port of app.py _call_hf_api (:1967) + configure_hf_api_params (:315).

Returns a list of PIL Images / "HF Error: ..." strings (one per requested output).
"""
import os
import random
import time
import traceback

from PIL import Image
from huggingface_hub import InferenceClient


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


def _run_with_backoff(call, cancel_event=None):
    """Run an InferenceClient call, retrying HTTP 429 with header-aware backoff (cap 6 tries).
    Duck-types the SDK's HfHubHTTPError (has .response) so we don't import a version-specific class;
    non-429 errors re-raise immediately for generate()'s existing formatter."""
    for attempt in range(6):
        try:
            return call()
        except Exception as e:
            resp = getattr(e, "response", None)
            code = getattr(resp, "status_code", None)
            is_429 = code == 429 or "429" in str(e) or "too many requests" in str(e).lower()
            if not is_429 or attempt == 5:
                raise
            if cancel_event is not None and cancel_event.is_set():
                raise
            time.sleep(_retry_wait(getattr(resp, "headers", None), 2 ** (attempt + 1)))


def configure_hf_api_params(params):
    """Apply comprehensive NSFW filter bypass techniques for Hugging Face (verbatim port)."""
    base_negative = ("worst quality, low quality, normal quality, signature, watermark, "
                     "username, artist name, text, words, blurry, censored, safety checker, "
                     "explicit censoring")
    if "negative_prompt" in params and params["negative_prompt"]:
        user_neg = params["negative_prompt"]
        combined_neg = f"{base_negative}, {user_neg}"
        params["negative_prompt"] = ", ".join(sorted(list(set(p.strip() for p in combined_neg.split(",")))))
    else:
        params["negative_prompt"] = base_negative

    safety_keywords = ("(highly detailed, masterpiece, best quality, photorealistic:1.4), "
                       "(perfectly acceptable content:1.8)")
    if "prompt" in params and params["prompt"]:
        if "(perfectly acceptable content" not in params["prompt"]:
            params["prompt"] = f"{params['prompt']} {safety_keywords}"
    os.environ["HF_DISABLE_SAFETY"] = "true"
    return params


def _call_once(client, model_id: str, params: dict, cancel_event=None):
    api_params = configure_hf_api_params(params.copy())

    # img2img: text_to_image() has no `image` kwarg (raises TypeError) — HF exposes a distinct
    # image_to_image() method. Only its documented params are safe to forward (no width/height/seed).
    if api_params.get("image"):
        try:
            src = Image.open(api_params["image"])
        except Exception as img_err:
            return f"HF Error: Failed to open input image for img2img - {img_err}"
        i2i = {
            "negative_prompt": api_params.get("negative_prompt"),
            "guidance_scale": api_params.get("guidance_scale"),
            "num_inference_steps": api_params.get("num_inference_steps"),
        }
        i2i = {k: v for k, v in i2i.items() if v is not None}
        result = _run_with_backoff(
            lambda: client.image_to_image(src, prompt=api_params["prompt"], model=model_id, **i2i),
            cancel_event)
        return result if isinstance(result, Image.Image) else "HF Error: Unexpected API response format."

    inference_params = {
        "prompt": api_params["prompt"],
        "negative_prompt": api_params.get("negative_prompt", ""),
        "width": api_params.get("width"),
        "height": api_params.get("height"),
        "guidance_scale": api_params.get("guidance_scale"),
        "num_inference_steps": api_params.get("num_inference_steps"),
    }
    if "seed" in api_params:
        inference_params["seed"] = api_params["seed"]
    inference_params = {k: v for k, v in inference_params.items() if v is not None}

    # LoRA (Phase 4) — text_to_image() has NO lora_weights/lora_scale kwargs (TypeError); provider
    # adapters go through extra_body. ponytail: fal-ai "loras" [{path,scale}] shape, best-effort —
    # a non-fal HF provider ignores an unknown extra_body key rather than crashing.
    _loras = [lo for lo in (api_params.get("enabled_loras") or []) if lo.get("enabled")]
    if _loras:
        extra = {"loras": [{"path": lo["url"], "scale": float(lo.get("scale", 1.0))} for lo in _loras]}
        image_result = _run_with_backoff(
            lambda: client.text_to_image(model=model_id, extra_body=extra, **inference_params), cancel_event)
    else:
        image_result = _run_with_backoff(
            lambda: client.text_to_image(model=model_id, **inference_params), cancel_event)
    if isinstance(image_result, Image.Image):
        return image_result
    return "HF Error: Unexpected API response format."


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    hf_token = os.environ.get("HUGGINGFACE_TOKEN")
    if not hf_token:
        return ["HF Error: Token not configured or found in environment/.env."]
    if not model_id:
        return ["HF Error: Model not selected."]

    client = InferenceClient(token=hf_token)
    num_outputs = params.get("num_outputs", 1)
    results = []
    for i in range(num_outputs):
        if cancel_event is not None and cancel_event.is_set():
            results.append("HF Error: Cancelled.")
            break
        batch_params = params.copy()
        batch_params["seed"] = (params.get("seed") if i == 0 and "seed" in params
                                else random.randint(0, 2**32 - 1))
        if progress:
            progress(f"Generating image {i + 1}/{num_outputs} (HF)...")
        try:
            results.append(_call_once(client, model_id, batch_params, cancel_event))
        except Exception as e:
            traceback.print_exc()
            error_str = str(e)
            if "authorization" in error_str.lower():
                results.append("HF Error: Authorization failed. Check your token.")
            elif "model is currently loading" in error_str.lower():
                results.append("HF Error: Model is loading, please wait and try again.")
            else:
                results.append(f"HF Error: {error_str}")
    return results
