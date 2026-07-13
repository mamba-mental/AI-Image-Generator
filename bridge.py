"""The js_api bridge — the ONLY surface JS can call. All returns are JSON-able dicts.
pywebview runs each call on a worker thread; generate() returns a job id immediately
and the JobRegistry pushes progress back via window.onEngineEvent.
"""
import json
import os
from pathlib import Path

from engine import config as engine_config
from engine import history, mediaserver
from engine.jobs import REGISTRY
from loramanager import LoRAManager


def _load_fal_models() -> list:
    path = engine_config.resource_path("engine/fal_models.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("models", [])
    return []


class Api:
    def __init__(self):
        self.config = engine_config.load()
        self.keys_status = engine_config.resolve_keys(self.config)
        self.media_base = mediaserver.start(self.config["output_directory"])
        self.lora_managers = {
            "huggingface": LoRAManager("huggingface"),
            "replicate": LoRAManager("replicate"),
        }
        self.lora_managers["huggingface"].load_from_config(self.config.get("recent_loras_hf", []))
        self.lora_managers["replicate"].load_from_config(self.config.get("recent_loras_replicate", []))

    # ---- state ----

    def get_state(self) -> dict:
        return {
            "services": ["fal", "openai", "nvidia", "replicate", "huggingface", "gemini"],
            "active_service": self.config.get("service", "fal"),
            "config": {k: v for k, v in self.config.items()
                       if k not in ("replicate_api_key", "huggingface_token",
                                    "gemini_api_key", "fal_api_key")},
            "fal_models": _load_fal_models(),
            "recent_models": {
                "replicate": self.config.get("recent_models_replicate", []),
                "huggingface": self.config.get("recent_models_hf", []),
                "gemini": self.config.get("recent_models_gemini", []),
                "fal": self.config.get("recent_models_fal", []),
                "openai": self.config.get("recent_models_openai", []),
                "nvidia": self.config.get("recent_models_nvidia", []),
            },
            "recent_prompts": self.config.get("recent_prompts", []),
            "loras": {
                "huggingface": self.lora_managers["huggingface"].get_loras(),
                "replicate": self.lora_managers["replicate"].get_loras(),
            },
            "keys_status": self.keys_status,
            "media_base": self.media_base,
            "output_dir_name": Path(self.config["output_directory"]).name,
            "busy": REGISTRY.is_busy(),
        }

    def set_config(self, patch: dict) -> dict:
        for k, v in dict(patch).items():
            if k == "parameters" and isinstance(v, dict):
                self.config.setdefault("parameters", {}).update(v)
            else:
                self.config[k] = v
        if "output_directory" in patch:
            mediaserver.set_dir(self.config["output_directory"])
        self._persist()
        return {"ok": True}

    # live key-validation probes (cheapest per provider; endpoints from PRIME's validate.sh)
    _VALIDATE = {
        "fal": ("https://api.fal.ai/v1/models?limit=1", lambda k: {"Authorization": f"Key {k}"}),
        "replicate": ("https://api.replicate.com/v1/account", lambda k: {"Authorization": f"Token {k}"}),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", lambda k: {"x-goog-api-key": k}),
        "huggingface": ("https://huggingface.co/api/whoami-v2", lambda k: {"Authorization": f"Bearer {k}"}),
        "openai": ("https://api.openai.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
        "nvidia": ("https://integrate.api.nvidia.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
    }

    def validate_key(self, service: str, key: str = "") -> dict:
        """Live-check a key against its provider (2xx = accepted). If key is empty,
        validate the currently-resolved key. Key value is never echoed back."""
        import urllib.error
        import urllib.request
        probe = self._VALIDATE.get(service)
        if not probe:
            return {"valid": False, "http": 0, "detail": f"unknown service {service}"}
        url, hdr = probe
        env_name = engine_config.KEY_FIELDS[service][1]
        k = key.strip() or os.environ.get(env_name, "")
        if not k:
            return {"valid": False, "http": 0, "detail": "no key set"}
        try:
            req = urllib.request.Request(url, headers=hdr(k))
            code = urllib.request.urlopen(req, timeout=15).getcode()
            return {"valid": 200 <= code < 300, "http": code, "detail": "accepted"}
        except urllib.error.HTTPError as e:
            return {"valid": False, "http": e.code,
                    "detail": "rejected" if e.code in (401, 403) else f"HTTP {e.code}"}
        except Exception as e:
            return {"valid": False, "http": 0, "detail": f"unreachable ({type(e).__name__})"}

    def save_and_validate_key(self, service: str, key: str) -> dict:
        """Persist a new key then live-validate it. Returns validation + refreshed status."""
        self.set_key(service, key)
        result = self.validate_key(service)  # validates the now-resolved key
        return {"validation": result, "keys_status": self.keys_status}

    def get_history(self, limit: int = 300) -> list:
        return history.read(self.config["output_directory"], limit)

    def recent_files(self, limit: int = 24) -> list:
        """Newest media in the output dir (for the browse landing). Basename only —
        the JS resolves it against the media server, same as the session gallery."""
        exts = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"}
        d = Path(self.config["output_directory"])
        if not d.exists():
            return []
        files = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in exts]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return [{"file": f.name} for f in files[:int(limit)]]

    def get_balance(self, service: str) -> dict:
        """Credit/quota status for the footer. Only fal exposes a real balance
        (via FAL_KEY_ADMIN); the rest are usage-based or free-tier. Key never returned."""
        import urllib.request
        try:
            if service == "fal":
                key = os.environ.get("FAL_KEY_ADMIN") or os.environ.get("FAL_KEY")
                if not key:
                    return {"label": "no admin key", "kind": "none"}
                req = urllib.request.Request(
                    "https://api.fal.ai/v1/account/billing?expand=credits",
                    headers={"Authorization": f"Key {key}"})
                d = json.loads(urllib.request.urlopen(req, timeout=15).read())
                c = d.get("credits", {}) or {}
                bal = c.get("current_balance")
                if bal is None:
                    return {"label": "balance n/a", "kind": "none"}
                return {"label": f"${bal:.2f} {c.get('currency', 'USD')}",
                        "kind": "low" if bal < 2 else "ok"}
            if service == "gemini":
                return {"label": "free tier · daily quota", "kind": "info"}
            if service == "replicate":
                return {"label": "usage-based · no balance API", "kind": "info"}
            if service == "huggingface":
                return {"label": "free / PRO tier", "kind": "info"}
            if service == "openai":
                return {"label": "usage-based · platform.openai.com/usage", "kind": "info"}
            if service == "nvidia":
                return {"label": "NIM credits · usage-based", "kind": "info"}
        except Exception as e:
            return {"label": f"balance unavailable ({type(e).__name__})", "kind": "none"}
        return {"label": "", "kind": "none"}

    def list_models(self, service: str) -> list:
        if service == "fal":
            return _load_fal_models()
        key = {"replicate": "recent_models_replicate",
               "huggingface": "recent_models_hf",
               "gemini": "recent_models_gemini",
               "openai": "recent_models_openai",
               "nvidia": "recent_models_nvidia"}.get(service, "")
        return [{"id": m, "label": m, "category": "text-to-image"}
                for m in self.config.get(key, [])]

    # ---- generation ----

    def generate(self, req: dict) -> dict:
        service = req.get("service", "")
        model_id = req.get("model", "")
        params = dict(req.get("params", {}))
        params["prompt"] = req.get("prompt", "")
        if req.get("input_files"):
            params["_inputs"] = dict(req["input_files"])
            if params["_inputs"].get("image"):
                params["image"] = params["_inputs"]["image"]  # legacy backends read this
        elif req.get("input_image_path"):
            params["image"] = req["input_image_path"]
        if req.get("category"):
            params["category"] = req["category"]
        if service in self.lora_managers:
            enabled = [l for l in self.lora_managers[service].get_loras() if l.get("enabled")]
            if enabled:
                params["enabled_loras"] = enabled

        # remember recents
        prompt = params["prompt"]
        if prompt:
            recents = self.config.setdefault("recent_prompts", [])
            if prompt in recents:
                recents.remove(prompt)
            recents.insert(0, prompt)
            del recents[20:]
        model_key = {"replicate": "recent_models_replicate", "huggingface": "recent_models_hf",
                     "gemini": "recent_models_gemini", "fal": "recent_models_fal",
                     "openai": "recent_models_openai", "nvidia": "recent_models_nvidia"}.get(service)
        if model_key and model_id:
            recents = self.config.setdefault(model_key, [])
            if model_id in recents:
                recents.remove(model_id)
            recents.insert(0, model_id)
        self.config["service"] = service
        self.config[f"last_used_model_{'hf' if service == 'huggingface' else service}"] = model_id
        self._persist()

        return REGISTRY.start(service, model_id, params, self.config["output_directory"])

    def cancel(self, job_id: str) -> dict:
        return REGISTRY.cancel(job_id)

    # ---- LoRA ----

    def lora_list(self, service: str) -> list:
        mgr = self.lora_managers.get(service)
        return mgr.get_loras() if mgr else []

    def lora_add(self, service: str, path_or_url: str) -> list:
        mgr = self.lora_managers.get(service)
        if mgr:
            mgr.add_lora(path_or_url)
            self._persist()
        return self.lora_list(service)

    def lora_remove(self, service: str, index: int) -> list:
        mgr = self.lora_managers.get(service)
        if mgr:
            mgr.remove_lora(int(index))
            self._persist()
        return self.lora_list(service)

    def lora_set(self, service: str, index: int, patch: dict) -> list:
        mgr = self.lora_managers.get(service)
        if mgr:
            loras = mgr.get_loras()
            if 0 <= int(index) < len(loras):
                if "enabled" in patch:
                    mgr.set_enabled(int(index), bool(patch["enabled"]))
                if "scale" in patch:
                    mgr.set_scale(int(index), float(patch["scale"]))
                self._persist()
        return self.lora_list(service)

    # ---- files / keys ----

    def open_output_folder(self) -> dict:
        path = self.config["output_directory"]
        os.makedirs(path, exist_ok=True)
        os.startfile(path)
        return {"ok": True}

    def save_as(self, src_path: str) -> dict:
        import webview
        win = webview.windows[0]
        dest = win.create_file_dialog(webview.SAVE_DIALOG,
                                      save_filename=os.path.basename(src_path))
        if dest:
            import shutil
            shutil.copy2(src_path, dest if isinstance(dest, str) else dest[0])
            return {"ok": True, "path": str(dest)}
        return {"ok": False}

    _PICK_FILTERS = {
        "image": "Images (*.png;*.jpg;*.jpeg;*.webp)",
        "video": "Video (*.mp4;*.webm;*.mov)",
        "audio": "Audio (*.mp3;*.wav;*.m4a;*.flac)",
        "mesh": "3D models (*.glb;*.obj;*.stl)",
    }

    def pick_input_file(self, kind: str = "image") -> dict:
        import webview
        win = webview.windows[0]
        picked = win.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=(self._PICK_FILTERS.get(kind, "All files (*.*)"),))
        if picked:
            return {"path": picked[0] if isinstance(picked, (list, tuple)) else str(picked)}
        return {"path": None}

    def pick_input_image(self) -> dict:  # legacy alias
        return self.pick_input_file("image")

    def set_key(self, service: str, key: str) -> dict:
        field = engine_config.KEY_FIELDS.get(service, (None, None))[0]
        if not field:
            return {"error": f"unknown service {service}"}
        self.config[field] = key
        self._persist()
        self.keys_status = engine_config.resolve_keys(self.config)
        return {"keys_status": self.keys_status}

    # ---- internal ----

    def _persist(self):
        self.config["recent_loras_hf"] = self.lora_managers["huggingface"].get_loras()
        self.config["recent_loras_replicate"] = self.lora_managers["replicate"].get_loras()
        engine_config.save(self.config)
