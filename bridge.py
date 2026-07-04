"""The js_api bridge — the ONLY surface JS can call. All returns are JSON-able dicts.
pywebview runs each call on a worker thread; generate() returns a job id immediately
and the JobRegistry pushes progress back via window.onEngineEvent.
"""
import json
import os

from engine import config as engine_config
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
        self.lora_managers = {
            "huggingface": LoRAManager("huggingface"),
            "replicate": LoRAManager("replicate"),
        }
        self.lora_managers["huggingface"].load_from_config(self.config.get("recent_loras_hf", []))
        self.lora_managers["replicate"].load_from_config(self.config.get("recent_loras_replicate", []))

    # ---- state ----

    def get_state(self) -> dict:
        return {
            "services": ["fal", "replicate", "huggingface", "gemini"],
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
            },
            "recent_prompts": self.config.get("recent_prompts", []),
            "loras": {
                "huggingface": self.lora_managers["huggingface"].get_loras(),
                "replicate": self.lora_managers["replicate"].get_loras(),
            },
            "keys_status": self.keys_status,
            "busy": REGISTRY.is_busy(),
        }

    def set_config(self, patch: dict) -> dict:
        for k, v in dict(patch).items():
            if k == "parameters" and isinstance(v, dict):
                self.config.setdefault("parameters", {}).update(v)
            else:
                self.config[k] = v
        self._persist()
        return {"ok": True}

    def list_models(self, service: str) -> list:
        if service == "fal":
            return _load_fal_models()
        key = {"replicate": "recent_models_replicate",
               "huggingface": "recent_models_hf",
               "gemini": "recent_models_gemini"}.get(service, "")
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
                     "gemini": "recent_models_gemini", "fal": "recent_models_fal"}.get(service)
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
