"""Config load/save, API-key resolution, dev-vs-frozen path logic.

Ported from app.py load_config (:457), save_config (:522), setup_services (:542).
Key resolution order preserved: config value wins unless empty/placeholder, else env.
"""
import json
import os
import sys
import threading
from pathlib import Path

_LOCK = threading.Lock()

APP_NAME = "AI Studio Void"
PLACEHOLDER_MARKERS = ("YOUR_REPLICATE_API_TOKEN", "YOUR_HUGGINGFACE_TOKEN",
                       "YOUR_GEMINI_API_KEY", "YOUR_FAL_KEY")

KEY_FIELDS = {
    "replicate": ("replicate_api_key", "REPLICATE_API_TOKEN"),
    "huggingface": ("huggingface_token", "HUGGINGFACE_TOKEN"),
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
    "fal": ("fal_api_key", "FAL_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "nvidia": ("nvidia_api_key", "NVIDIA_API_KEY"),
}


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_path(rel: str) -> Path:
    """Bundled read-only assets: web/, engine/fal_models.json, icon."""
    base = Path(getattr(sys, "_MEIPASS", repo_root()))
    return base / rel


def config_path() -> Path:
    if is_frozen():
        return Path(os.environ["APPDATA"]) / APP_NAME / "config.json"
    return repo_root() / "config.json"


def default_output_dir() -> Path:
    if is_frozen():
        return Path(os.path.expanduser("~")) / "Pictures" / APP_NAME
    return repo_root() / "generated_images"


def _default_config() -> dict:
    tmpl = resource_path("config.default.json")
    if tmpl.exists():
        cfg = json.loads(tmpl.read_text(encoding="utf-8"))
    else:
        cfg = {"service": "fal", "parameters": {}, "recent_prompts": []}
    cfg["output_directory"] = str(default_output_dir())
    return cfg


def load() -> dict:
    """Load config, merging any missing keys from the default template (ported merge logic)."""
    path = config_path()
    default = _default_config()
    try:
        if path.exists():
            with _LOCK:
                cfg = json.loads(path.read_text(encoding="utf-8"))
            for key, value in default.items():
                if key not in cfg:
                    cfg[key] = value
                elif key == "parameters" and isinstance(value, dict):
                    if not isinstance(cfg.get(key), dict):
                        cfg[key] = {}
                    for sub_key, sub_value in value.items():
                        cfg[key].setdefault(sub_key, sub_value)
                elif key.startswith("recent_") and not isinstance(cfg.get(key), list):
                    cfg[key] = value
            cfg.get("parameters", {}).pop("lora_scale", None)  # obsolete key, ported cleanup
            if not cfg.get("output_directory"):
                cfg["output_directory"] = str(default_output_dir())
            os.makedirs(cfg["output_directory"], exist_ok=True)
            return cfg
        os.makedirs(default["output_directory"], exist_ok=True)
        save(default)
        return default
    except Exception as e:
        print(f"Error loading/creating config: {e}")
        os.makedirs(default["output_directory"], exist_ok=True)
        return default


def save(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _resolve_one(cfg: dict, config_field: str, env_name: str) -> str:
    config_val = cfg.get(config_field, "") or ""
    if config_val and not any(m in config_val for m in PLACEHOLDER_MARKERS):
        return config_val
    return os.environ.get(env_name) or ""


def resolve_keys(cfg: dict) -> dict:
    """Resolve final key per service (config-wins-over-env), export to env for the
    client libraries, and return {service: bool} status. Values never leave this module."""
    status = {}
    for service, (config_field, env_name) in KEY_FIELDS.items():
        final = _resolve_one(cfg, config_field, env_name)
        if final:
            os.environ[env_name] = final
        status[service] = bool(final)
    # library behavior flags (ported from setup_services :567)
    os.environ["FLUX_DISABLE_SAFETY"] = "true"
    os.environ["FLUX_GO_FAST"] = "true"
    print("API Key Setup: " + ", ".join(f"{s}={'OK' if ok else 'missing'}" for s, ok in status.items()))
    return status
