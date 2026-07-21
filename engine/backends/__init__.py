"""Backend dispatch table. Each backend exposes generate(model_id, params, progress, cancel_event)
and returns a list of results: URL strings, PIL Images, bytes tuples, or "…Error…" strings."""
from . import replicate_api, hf_api, gemini_api, openai_api, nvidia_api, openrouter_api
from . import together_api, cliproxy_api, ideogram_api, ideogram_web_api, agnes_api
from . import runware_api, novita_api

BACKENDS = {
    "replicate": replicate_api.generate,
    "huggingface": hf_api.generate,
    "gemini": gemini_api.generate,
    "openai": openai_api.generate,
    "nvidia": nvidia_api.generate,
    "openrouter": openrouter_api.generate,
    "together": together_api.generate,
    "cliproxy": cliproxy_api.generate,
    "runware": runware_api.generate,         # uncensored open-weight host (checkNSFW opt-in) + CivitAI AIRs + LoRA
    "novita": novita_api.generate,           # async txt2img; NSFW opt-in (enable_nsfw_detection) + LoRA
    "ideogram": ideogram_web_api.generate,   # "Ideogram" = Plus subscription via the web session
    "ideogram-api": ideogram_api.generate,   # paid public REST API — kept for if/when funded (not in dropdown)
    "agnes": agnes_api.generate,             # AGNES-AI (Sapiens) — image (/v1/images/generations) + video (async /v1/videos + poll)
}

try:  # fal lands in Phase 3; optional so the engine imports without fal-client installed
    from . import fal_api
    BACKENDS["fal"] = fal_api.generate
except ImportError:
    pass
