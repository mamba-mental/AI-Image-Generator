"""Replicate backend — behavior-preserving port of app.py _call_replicate_api (:1877).

Returns a list of image URLs on success, or a single-element ["Replicate Error: ..."] list.
"""
import os
import random
import traceback

import replicate


def _build_input(params: dict) -> dict:
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
    if params.get("enabled_loras"):
        first = params["enabled_loras"][0]
        input_params["lora"] = first["url"]
        input_params["lora_scale"] = first["scale"]
        if len(params["enabled_loras"]) > 1:
            print("Warning: multiple Replicate LoRAs enabled; API supports one — using the first.")
    return {k: v for k, v in input_params.items() if v is not None}


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    if not os.environ.get("REPLICATE_API_TOKEN"):
        return ["Replicate Error: API Key not configured or found in environment/.env."]
    if not model_id:
        return ["Replicate Error: Model not selected."]

    input_params = _build_input(params)
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
