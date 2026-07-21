"""Replicate backend — behavior-preserving port of app.py _call_replicate_api (:1877).

Returns a list of image URLs on success, or a single-element ["Replicate Error: ..."] list.
"""
import os
import traceback

import replicate


def balance() -> dict:
    """No $-balance API exists on Replicate. Live-probed 2026-07-21: GET /v1/account
    returns only {type, username, name, avatar_url, github_url} — no credit/spend field.
    /v1/account/billing, /v1/billing, /v1/account/spend, /v1/account/usage all 404.
    Confirmed by Replicate's own docs (replicate.com/docs/topics/billing): balance is
    dashboard-only, no read API. Portal-only by design, not an engineering gap.

    Gotcha for any future live-key probe of api.replicate.com: it sits behind Cloudflare
    bot-protection. A plain urllib request with the default User-Agent gets blocked with
    a Cloudflare "error code: 1010" HTTP 403 that LOOKS like a rejected key but isn't —
    send a browser User-Agent (see bridge.py's `together`/`civitai` probes for the
    pattern) or the key will false-negative as invalid."""
    return {"label": "portal-only · replicate.com/account/billing", "kind": "none"}


def _build_input(params: dict, model_id: str = "") -> dict:
    input_params = {
        "prompt": params.get("prompt", ""),
        "width": params.get("width"),
        "height": params.get("height"),
        "num_inference_steps": params.get("num_inference_steps", 28),
        "guidance_scale": params.get("guidance_scale", params.get("guidance", 7.5)),
        "negative_prompt": params.get("negative_prompt", ""),
        "num_outputs": params.get("num_outputs", 1),
        "apply_watermark": False,
        "disable_safety_checker": True,
    }
    ui_safety_tolerance = params.get("safety_tolerance")
    if ui_safety_tolerance is not None:
        input_params["safety_tolerance"] = min(int(ui_safety_tolerance), 6)
    else:
        input_params["safety_tolerance"] = 6

    if params.get("image"):
        input_params["image"] = params["image"]
    if params.get("seed"):
        input_params["seed"] = params["seed"]
    # LoRA (Phase 4) — Replicate's param names differ PER MODEL (research §Replicate):
    #   *flux-dev-multi-lora* -> hf_loras:[str] + lora_scales:[num]  (up to 20, real multi-LoRA)
    #   flux-dev-lora / others -> lora_weights + extra_lora (+ *_scale), max 2
    loras = [lo for lo in (params.get("enabled_loras") or []) if lo.get("enabled")]
    if loras:
        if "multi-lora" in (model_id or "").lower():
            input_params["hf_loras"] = [lo["url"] for lo in loras]
            input_params["lora_scales"] = [float(lo.get("scale", 1.0)) for lo in loras]
        else:
            input_params["lora_weights"] = loras[0]["url"]
            input_params["lora_scale"] = float(loras[0].get("scale", 1.0))
            if len(loras) > 1:
                input_params["extra_lora"] = loras[1]["url"]
                input_params["extra_lora_scale"] = float(loras[1].get("scale", 1.0))
            if len(loras) > 2:
                print(f"Warning: Replicate flux-dev-lora supports 2 LoRAs; {len(loras)} enabled — using the first 2.")
    return {k: v for k, v in input_params.items() if v is not None}


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    if not os.environ.get("REPLICATE_API_TOKEN"):
        return ["Replicate Error: API Key not configured or found in environment/.env."]
    if not model_id:
        return ["Replicate Error: Model not selected."]

    input_params = _build_input(params, model_id)
    if progress:
        progress(f"Calling Replicate: {model_id}")
    try:
        output = replicate.run(model_id, input=input_params)
    except replicate.exceptions.ReplicateError as e:
        error_msg = str(e)
        if "nsfw" in error_msg.lower() or "safety" in error_msg.lower():
            # ported retry-with-aggressive-bypass path (:1942)
            retry_params = input_params.copy()
            retry_params["negative_prompt"] = (
                f"{retry_params.get('negative_prompt', '')}, nsfw, nude, safety watermark, "
                f"censored, explicit, bad quality, worst quality, deformed, blurry"
            ).strip(", ")
            if progress:
                progress("NSFW filter tripped — retrying with aggressive bypass")
            try:
                output = replicate.run(model_id, input=retry_params)
            except Exception as retry_e:
                return [f"Replicate Error (Retry Failed): {retry_e}"]
        else:
            return [f"Replicate Error: {error_msg}"]
    except Exception as e:
        traceback.print_exc()
        return [f"Unexpected Replicate Error: {e}"]

    num_outputs = params.get("num_outputs", 1)
    if isinstance(output, list):
        return [str(u) for u in output]
    if isinstance(output, str) and "Error" in output:
        return [output] * num_outputs
    if output:
        return [str(output)]
    return ["Replicate Error: No result returned"] * num_outputs
