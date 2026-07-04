"""fal.ai backend — queue lifecycle via fal_client: submit -> iter_events -> get.

submit (not subscribe) so we hold a request handle for cancellation
(fal_client.cancel(model_id, request_id)). Model curation lives in
engine/fal_models.json; params from the UI pass through verbatim so model
schema drift surfaces as fal's own 422 message instead of a local crash.
"""
import json
import os
import traceback

import fal_client

from .. import config as engine_config

_MODELS_CACHE = None


def _models() -> dict:
    """{model_id: entry} from the curated table."""
    global _MODELS_CACHE
    if _MODELS_CACHE is None:
        path = engine_config.resource_path("engine/fal_models.json")
        entries = json.loads(path.read_text(encoding="utf-8")).get("models", []) if path.exists() else []
        _MODELS_CACHE = {m["id"]: m for m in entries}
    return _MODELS_CACHE


_ENGINE_ONLY_KEYS = {"image", "category", "enabled_loras", "num_outputs",
                     "width", "height", "prompt_strength", "_inputs"}

_INPUT_ARG_NAME = {"image": "image_url", "video": "video_url",
                   "audio": "audio_url", "mesh": "model_mesh_url"}


def _build_args(entry: dict, params: dict) -> dict:
    """Pass params through; translate legacy UI fields; upload local input media."""
    args = {k: v for k, v in params.items()
            if v is not None and k not in _ENGINE_ONLY_KEYS}

    # Legacy width/height (from the shared params panel) -> explicit image_size,
    # only for image models that didn't already get an image_size/aspect_ratio hint.
    if (entry.get("output") == "image" and "image_size" not in args
            and "aspect_ratio" not in args
            and params.get("width") and params.get("height")):
        args["image_size"] = {"width": int(params["width"]), "height": int(params["height"])}

    # Local input media (one slot per kind: image/video/audio/mesh) -> fal storage URLs
    inputs = dict(params.get("_inputs") or {})
    if params.get("image") and "image" not in inputs:  # legacy single-image path
        inputs["image"] = params["image"]
    from pathlib import Path
    for kind, path in inputs.items():
        if not path:
            continue
        url = str(path) if str(path).startswith("http") else fal_client.upload_file(Path(path))
        args[_INPUT_ARG_NAME.get(kind, f"{kind}_url")] = url

    return args


def _extract_outputs(result: dict, output_kind: str = "image") -> list:
    """Normalize fal result shapes to a list of URL strings / {'text': ...} dicts."""
    urls = []
    if not isinstance(result, dict):
        return urls
    for list_key in ("images", "videos", "outputs", "audios"):
        for item in result.get(list_key) or []:
            if isinstance(item, dict) and item.get("url"):
                urls.append(item["url"])
    for key in ("image", "video", "audio", "audio_file", "audio_url",
                "model_mesh", "mesh", "file", "output_file"):
        val = result.get(key)
        if isinstance(val, dict) and val.get("url"):
            urls.append(val["url"])
        elif isinstance(val, str) and val.startswith("http"):
            urls.append(val)
    if not urls and result.get("url"):
        urls.append(result["url"])
    if not urls and output_kind == "text":
        for key in ("text", "output", "caption", "transcription", "description"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                urls.append({"text": val})
                break
        else:  # structured text result — dump it whole
            urls.append({"text": json.dumps(result, indent=1, default=str)})
    return urls


def _describe(event) -> str:
    if isinstance(event, fal_client.InProgress):
        logs = event.logs or []
        if logs:
            return str(logs[-1].get("message", "running..."))
        return "running..."
    if isinstance(event, fal_client.Queued):
        return f"queued (position {event.position})"
    return event.__class__.__name__.lower()


def generate(model_id: str, params: dict, progress=None, cancel_event=None) -> list:
    if not os.environ.get("FAL_KEY"):
        return ["fal Error: FAL_KEY not configured in environment/.env."]
    if not model_id:
        return ["fal Error: Model not selected."]

    entry = _models().get(model_id, {"id": model_id, "output": "image"})
    try:
        args = _build_args(entry, params)
    except Exception as e:
        return [f"fal Error: input preparation failed - {e}"]

    if progress:
        progress(f"Submitting to fal: {model_id}")
    try:
        handler = fal_client.submit(model_id, arguments=args)
        for event in handler.iter_events(with_logs=True):
            if cancel_event is not None and cancel_event.is_set():
                try:
                    fal_client.cancel(model_id, handler.request_id)
                except Exception as cancel_err:
                    print(f"fal cancel call failed: {cancel_err}")
                return ["fal Error: Cancelled."]
            if progress:
                progress(_describe(event))
        result = handler.get()
    except Exception as e:
        traceback.print_exc()
        msg = str(e)
        if "422" in msg or "validation" in msg.lower():
            return [f"fal Error (validation — model schema may have drifted): {msg[:400]}"]
        return [f"fal Error: {msg[:400]}"]

    urls = _extract_outputs(result, entry.get("output", "image"))
    if not urls:
        return [f"fal Error: no output URL in result — keys: {list(result.keys()) if isinstance(result, dict) else type(result).__name__}"]
    return urls
