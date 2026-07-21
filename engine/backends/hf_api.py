"""Hugging Face backend — port of app.py _call_hf_api (:1967) + configure_hf_api_params (:315).

Returns a list of PIL Images / "HF Error: ..." strings (one per requested output).
"""
import os
import random
import traceback

from PIL import Image
from huggingface_hub import InferenceClient


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


def _call_once(client, model_id: str, params: dict):
    api_params = configure_hf_api_params(params.copy())
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
    # LoRA (Phase 4) — stack all enabled weights; HF hosted inference honors a single scale
    # (real multi-adapter weighting needs local diffusers set_adapters — out of scope here).
    _loras = [lo for lo in (api_params.get("enabled_loras") or []) if lo.get("enabled")]
    if _loras:
        inference_params["lora_weights"] = [lo["url"] for lo in _loras]
        inference_params["lora_scale"] = float(_loras[0].get("scale", 1.0))
    if api_params.get("image"):
        try:
            inference_params["image"] = Image.open(api_params["image"])
        except Exception as img_err:
            return f"HF Error: Failed to open input image for img2img - {img_err}"
    inference_params = {k: v for k, v in inference_params.items() if v is not None}

    image_result = client.text_to_image(model=model_id, **inference_params)
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
            results.append(_call_once(client, model_id, batch_params))
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
