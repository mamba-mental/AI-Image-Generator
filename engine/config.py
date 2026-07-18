"""Config load/save, API-key resolution, dev-vs-frozen path logic.

Ported from app.py load_config (:457), save_config (:522), setup_services (:542).
Key resolution order preserved: config value wins unless empty/placeholder, else env.
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

_LOCK = threading.Lock()

# Best-effort mount script for the NAS image drive (I:). If the configured output
# drive is missing we try this once before falling back to a local dir.
_MOUNT_SCRIPT = r"C:/Scripts/Mount-AIImagesDrive.ps1"

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
    "openrouter": ("openrouter_api_key", "OPENROUTER_API_KEY"),
    "together": ("together_api_key", "TOGETHER_API_KEY"),
    "cliproxy": ("cliproxy_api_key", "CLIPROXY_API_KEY"),
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
    # Dev override: run the source app against the real (frozen-exe) config/data.
    override = os.environ.get("VOID_CONFIG")
    if override:
        return Path(override)
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


def _try_mount_drive() -> None:
    """Best-effort: run the known mount script for the NAS image drive (I:)."""
    if os.path.exists(_MOUNT_SCRIPT):
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _MOUNT_SCRIPT],
                timeout=25, capture_output=True,
            )
        except Exception:
            pass


def _ensure_output_dir(cfg: dict) -> None:
    """Guarantee the output dir exists WITHOUT discarding the rest of config.

    If the configured drive/dir is missing (e.g. the I: NAS mount is down) we try to
    mount it once, then fall back to a local dir and flag it so the UI can warn — we
    NEVER let a missing drive silently blow the whole config back to defaults.
    """
    cfg.pop("_drive_fallback", None)
    out = cfg.get("output_directory") or str(default_output_dir())
    try:
        os.makedirs(out, exist_ok=True)
        cfg["output_directory"] = out
        return
    except Exception:
        pass
    # Drive/dir unreachable — if it's a bare drive letter, try to mount it once.
    drive = os.path.splitdrive(out)[0]  # e.g. 'I:'
    if drive:
        _try_mount_drive()
        try:
            os.makedirs(out, exist_ok=True)
            cfg["output_directory"] = out
            return
        except Exception:
            pass
    # Still unreachable — fall back locally, keep everything else, flag for the UI banner.
    fallback = str(default_output_dir())
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        pass
    cfg["output_directory"] = fallback
    cfg["_drive_fallback"] = {"wanted": out, "using": fallback}


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
            cfg.setdefault("library_directory", "")  # extra folder the LIBRARY view browses (blank = just output_dir)
            _ensure_output_dir(cfg)
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
    """Resolve keys per service (config-wins-over-env), build the multi-key POOL (#13),
    export the active key to env for the client libraries, and return {service: bool} status.
    Values never leave this module."""
    from . import keypool
    status = {}
    for service, (config_field, env_name) in KEY_FIELDS.items():
        final = _resolve_one(cfg, config_field, env_name)
        if final:
            os.environ[env_name] = final
        # #13 — pool from config (single or list) + primary env + numbered/comma env variants
        pool_cfg = cfg.get(config_field + "s") or cfg.get(config_field)
        n = keypool.build(service, env_name, pool_cfg if pool_cfg else final)
        status[service] = bool(final) or n > 0
    # library behavior flags (ported from setup_services :567)
    os.environ["FLUX_DISABLE_SAFETY"] = "true"
    os.environ["FLUX_GO_FAST"] = "true"
    print("API Key Setup: " + ", ".join(f"{s}={'OK' if ok else 'missing'}" for s, ok in status.items()))
    return status
