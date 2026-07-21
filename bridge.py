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


def _load_service_params() -> dict:
    """Per-service UI param schemas for the non-fal backends (retires generic LEGACY_PARAMS)."""
    path = engine_config.resource_path("engine/service_params.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("services", {})
    return {}


def _openapi_props_to_params(schema: dict, comps: dict) -> list:
    """OpenAPI Input schema properties -> UI params[] (name/type/values/default/min/max/description)."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    out = []
    for name, p in props.items():
        if name == "prompt" or name.endswith("_url") or name in ("image", "mask", "images"):
            continue
        typ, enum = p.get("type"), p.get("enum")
        if not typ and p.get("allOf"):  # replicate enum pattern: allOf: [{$ref -> EnumDef}]
            tgt = comps.get((p["allOf"][0].get("$ref") or "").split("/")[-1], {})
            enum = enum or tgt.get("enum"); typ = typ or tgt.get("type")
        entry = {"name": name}
        if enum:
            entry.update(type="enum", values=enum)
        elif typ == "boolean":
            entry["type"] = "bool"
        elif typ == "integer":
            entry["type"] = "int"
        elif typ == "number":
            entry["type"] = "float"
        elif typ == "string":
            entry["type"] = "string"
        else:
            continue
        if "default" in p:
            entry["default"] = p["default"]
        if "minimum" in p:
            entry["min"] = p["minimum"]
        if "maximum" in p:
            entry["max"] = p["maximum"]
        if name not in required and "default" not in p:
            entry["optional"] = True
        desc = (p.get("description") or "")[:220]
        if desc:
            entry["description"] = desc
        out.append(entry)
    out.sort(key=lambda e: (0 if "default" in e else 1, e["name"]))
    return out[:16]


def _replicate_input_params(model_id: str) -> list:
    """Fetch a Replicate model's live OpenAPI Input schema -> UI params[]. [] on any failure."""
    import urllib.request
    tok = os.environ.get("REPLICATE_API_TOKEN")
    if not tok or "/" not in (model_id or ""):
        return []
    owner, rest = model_id.split("/", 1)
    name = rest.split(":")[0].split("/")[0]  # strip any :version or extra path
    try:
        req = urllib.request.Request(f"https://api.replicate.com/v1/models/{owner}/{name}",
                                     headers={"Authorization": f"Token {tok}"})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception:
        return []
    comps = (((d.get("latest_version") or {}).get("openapi_schema") or {})
             .get("components", {}).get("schemas", {}))
    schema = comps.get("Input") or {}
    return _openapi_props_to_params(schema, comps) if schema.get("properties") else []


def _app_version() -> str:
    """A visible build stamp so PRIME always knows WHICH build he's running
    (source vs frozen exe) and at what revision — kills the stale-exe confusion."""
    import subprocess
    import datetime
    kind = "FROZEN" if engine_config.is_frozen() else "SOURCE"
    sha = "nogit"
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(engine_config.repo_root()), timeout=5,
            stderr=subprocess.DEVNULL,
        ).decode().strip() or "nogit"
    except Exception:
        pass
    return f"{kind} · {sha} · {datetime.datetime.now().strftime('%m-%d %H:%M')}"


class Api:
    def __init__(self):
        self.config = engine_config.load()
        self.version = _app_version()
        self.keys_status = engine_config.resolve_keys(self.config)
        self.media_base = mediaserver.start(self.config["output_directory"])
        for _libdir in self._library_dirs():  # LIBRARY view browses every configured archive
            if os.path.isdir(_libdir):
                mediaserver.add_root(_libdir)
        # LoRA-capable services (each backend translates {url,scale} to its own request shape).
        self._lora_cfg = {"huggingface": "recent_loras_hf", "replicate": "recent_loras_replicate",
                          "fal": "recent_loras_fal", "together": "recent_loras_together",
                          "runware": "recent_loras_runware", "novita": "recent_loras_novita"}
        self.lora_managers = {s: LoRAManager(s) for s in self._lora_cfg}
        for _s, _k in self._lora_cfg.items():
            self.lora_managers[_s].load_from_config(self.config.get(_k, []))

    # ---- state ----

    def get_state(self) -> dict:
        return {
            "services": ["fal", "openai", "nvidia", "replicate", "huggingface", "gemini",
                         "openrouter", "together", "runware", "novita", "cliproxy", "ideogram", "agnes"],
            "active_service": self.config.get("service", "fal"),
            "config": {k: v for k, v in self.config.items()
                       if k not in ("replicate_api_key", "huggingface_token",
                                    "gemini_api_key", "fal_api_key")},
            "fal_models": _load_fal_models(),
            "service_params": _load_service_params(),
            "recent_models": {
                "replicate": self.config.get("recent_models_replicate", []),
                "huggingface": self.config.get("recent_models_hf", []),
                "gemini": self.config.get("recent_models_gemini", []),
                "fal": self.config.get("recent_models_fal", []),
                "openai": self.config.get("recent_models_openai", []),
                "nvidia": self.config.get("recent_models_nvidia", []),
                # #11 — seed OpenRouter's image-output models (verified via openrouter.ai/api/v1/models)
                "openrouter": self.config.get("recent_models_openrouter", []) or [
                    "google/gemini-3-pro-image", "google/gemini-3.1-flash-image",
                    "google/gemini-2.5-flash-image", "openai/gpt-5-image"],
                # E3 — Together.ai serverless image models (verified live on /v1/images/generations)
                "together": self.config.get("recent_models_together", []) or [
                    "black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.1-dev",
                    "black-forest-labs/FLUX.1-dev-lora", "black-forest-labs/FLUX.1.1-pro"],
                # Runware — AIR model ids (runware:<id>@<ver> base, or civitai:<id>@<ver> for NSFW
                # community checkpoints). checkNSFW is opt-in → uncensored on open weights.
                "runware": self.config.get("recent_models_runware", []) or [
                    "runware:100@1", "runware:101@1"],
                # Novita — catalog model_name strings (NOT urls); async txt2img, NSFW opt-in.
                "novita": self.config.get("recent_models_novita", []) or [
                    "sd_xl_base_1.0", "realisticVisionV51_v51VAE.safetensors", "dreamshaper_8_93211.safetensors"],
                # E1 — cliproxy image models routable via /v1/images/generations (verified live)
                "cliproxy": self.config.get("recent_models_cliproxy", []) or [
                    "gpt-image-2", "gpt-image-1.5", "grok-imagine-image"],
                # Ideogram = Plus subscription via web session; model auto-selected server-side
                "ideogram": self.config.get("recent_models_ideogram", []) or ["auto"],
                # AGNES-AI (Sapiens) — image via /v1/images/generations; video via async /v1/videos
                # (create → poll GET /agnesapi?video_id). All verified live 2026-07-20.
                "agnes": self.config.get("recent_models_agnes", []) or [
                    "agnes-image-2.1-flash", "agnes-image-2.0-flash", "agnes-video-v2.0"],
            },
            "recent_prompts": self.config.get("recent_prompts", []),
            "loras": {s: m.get_loras() for s, m in self.lora_managers.items()},
            "keys_status": self.keys_status,
            "key_pools": self._key_pools(),
            "media_base": self.media_base,
            "output_dir_name": Path(self.config["output_directory"]).name,
            "output_dir": self.config["output_directory"],
            "library_dir": self.config.get("library_directory") or "",
            "library_dir_name": Path(self.config["library_directory"]).name if self.config.get("library_directory") else "",
            "library_dirs": self.list_library_dirs(),  # folder-toggle UI: [{path,name,enabled,exists}]
            "version": self.version,
            "drive_fallback": self.config.get("_drive_fallback"),
            "busy": REGISTRY.is_busy(),
        }

    def _key_pools(self) -> dict:
        """#13 — how many keys are pooled per service (for the settings UI)."""
        from engine import keypool
        return {s: keypool.size(s) for s in engine_config.KEY_FIELDS}

    def _all_library_dirs(self) -> list:
        """Every configured library folder (enabled AND disabled). De-duped, order preserved.
        Supports the plural `library_directories`; falls back to legacy single `library_directory`."""
        dirs = self.config.get("library_directories")
        if not isinstance(dirs, list):
            single = self.config.get("library_directory") or ""
            dirs = [single] if single else []
        seen, out = set(), []
        for d in dirs:
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out

    def _library_dirs(self) -> list:
        """Folders the LIBRARY view actually browses = all configured dirs MINUS the ones toggled
        off in `library_directories_disabled`. This is the single chokepoint feeding the scan,
        read_meta, and media-server roots — filtering here toggles a folder everywhere at once."""
        disabled = set(self.config.get("library_directories_disabled") or [])
        return [d for d in self._all_library_dirs() if d not in disabled]

    _LIB_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"}
    _VID_EXTS = {".mp4", ".webm", ".mov"}
    _LIB_INDEX_VERSION = 2  # bump when the record shape changes (invalidates stale caches)

    def _library_index_path(self) -> str:
        return os.path.join(str(engine_config.repo_root()), ".cache", "library_index.json")

    def _scan_library(self, bases: list) -> list:
        """Walk the archive folders once and return de-duped per-image RECORDS (the slow NAS crawl).
        Each record: {file, dir, type} plus any of {service, model, prompt, category} found in the
        image's `<media>.<ext>.json` sidecar. Sidecar reads run on a small thread pool because NAS
        round-trips are latency-bound; the whole result is cached to the local index afterward."""
        from concurrent.futures import ThreadPoolExecutor
        seen, records = set(), []
        for base in bases:
            d = Path(base)
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() in self._LIB_EXTS and f.name not in seen:
                    seen.add(f.name)
                    records.append({"file": f.name, "dir": base, "_path": str(f),
                                    "type": "video" if f.suffix.lower() in self._VID_EXTS else "image"})

        def _enrich(rec):
            side = Path(rec.pop("_path") + ".json")
            if side.exists():
                try:
                    meta = json.loads(side.read_text(encoding="utf-8"))
                    for k in ("service", "model", "prompt", "category"):
                        if meta.get(k):
                            rec[k] = meta[k]
                except Exception:
                    pass
            return rec

        if records:
            with ThreadPoolExecutor(max_workers=16) as pool:
                records = list(pool.map(_enrich, records))
        records.sort(key=lambda r: r["file"].lower())
        return records

    def model_schema(self, service: str, model_id: str) -> dict:
        """Live per-model param schema for services that expose one (Replicate). {params:[]} otherwise."""
        try:
            if service == "replicate":
                return {"params": _replicate_input_params(model_id)}
        except Exception:
            pass
        return {"params": []}

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
        "openrouter": ("https://openrouter.ai/api/v1/key", lambda k: {"Authorization": f"Bearer {k}"}),
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

    def get_logs(self, query: str = "", level: str = "") -> list:
        """#14 — searchable engine-event ring buffer for the Logs panel."""
        from engine import logbuf
        return logbuf.read(query, level, 300)

    def clear_logs(self) -> dict:
        from engine import logbuf
        logbuf.clear()
        return {"ok": True}

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

    def list_library(self, limit: int = 8000, refresh: bool = False) -> list:
        """LIBRARY view source. Returns de-duped basenames across every configured archive.

        The archives live on the NAS; a live recursive crawl of ~5k files on every app open is
        why the grid used to redraw slowly. So the file list is cached to a LOCAL json index
        (`.cache/library_index.json`) and served from there instantly. The crawl only runs when
        the index is missing, the archive set changed, or `refresh=True` (the ↻ button)."""
        bases = [d for d in self._library_dirs() if os.path.isdir(d)] or [self.config["output_directory"]]
        idx = self._library_index_path()
        if not refresh:
            try:
                if os.path.exists(idx):
                    with open(idx, encoding="utf-8") as f:
                        data = json.load(f)
                    if (data.get("version") == self._LIB_INDEX_VERSION
                            and data.get("dirs") == bases and isinstance(data.get("files"), list)):
                        return data["files"][:int(limit)]
            except Exception:
                pass  # bad/absent/old-version index → fall through to a fresh scan
        records = self._scan_library(bases)
        try:
            os.makedirs(os.path.dirname(idx), exist_ok=True)
            with open(idx, "w", encoding="utf-8") as f:
                json.dump({"version": self._LIB_INDEX_VERSION, "dirs": bases,
                           "files": records, "count": len(records)}, f)
        except Exception:
            pass
        return records[:int(limit)]

    def refresh_library(self, limit: int = 8000) -> list:
        """Force a fresh NAS crawl + rebuild the cached index (for the Library ↻ refresh button)."""
        return self.list_library(limit=limit, refresh=True)

    def list_library_dirs(self) -> list:
        """Every configured library folder + its state, for the folder-toggle UI.
        [{path, name, enabled, exists}] — enabled = NOT in library_directories_disabled."""
        disabled = set(self.config.get("library_directories_disabled") or [])
        return [{"path": d, "name": Path(d).name or d,
                 "enabled": d not in disabled, "exists": os.path.isdir(d)}
                for d in self._all_library_dirs()]

    def set_library_dir_enabled(self, path: str, enabled: bool) -> dict:
        """Toggle one library folder on/off. Off = added to library_directories_disabled + its
        media-server root removed; on = removed from the disabled set + root re-registered. The
        library index rebuilds automatically on next list (its cached `dirs` set changes)."""
        disabled = set(self.config.get("library_directories_disabled") or [])
        if enabled:
            disabled.discard(path)
            if os.path.isdir(path):
                mediaserver.add_root(path)
        else:
            disabled.add(path)
            mediaserver.remove_root(path)
        self.config["library_directories_disabled"] = sorted(disabled)
        self._persist()
        return {"ok": True, "dirs": self.list_library_dirs()}

    def add_library_dir(self, path: str = "") -> dict:
        """Add a folder to the library. With no path, opens a native folder picker. Appends to
        library_directories, registers the media root, persists, returns the updated dir list."""
        if not path:
            import webview
            win = webview.windows[0]
            sel = win.create_file_dialog(webview.FOLDER_DIALOG)
            path = (sel[0] if sel else "") or ""
        if not path or not os.path.isdir(path):
            return {"ok": False, "error": "not a folder", "dirs": self.list_library_dirs()}
        if path not in self._all_library_dirs():
            existing = self.config.get("library_directories")
            base = list(existing) if isinstance(existing, list) else self._all_library_dirs()
            self.config["library_directories"] = base + [path]
            mediaserver.add_root(path)
            self._persist()
        return {"ok": True, "dirs": self.list_library_dirs()}

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
            if service == "openrouter":
                key = os.environ.get("OPENROUTER_API_KEY")
                if not key:
                    return {"label": "no key", "kind": "none"}
                req = urllib.request.Request("https://openrouter.ai/api/v1/key",
                                             headers={"Authorization": f"Bearer {key}"})
                d = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("data", {})
                usage, limit = d.get("usage"), d.get("limit")
                if limit is not None:
                    left = max(0.0, float(limit) - float(usage or 0))
                    return {"label": f"${left:.2f} left", "kind": "low" if left < 2 else "ok"}
                return {"label": f"${usage or 0:.2f} used · no cap", "kind": "info"}
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

    @staticmethod
    def _normalize_model_id(service: str, model_id: str) -> str:
        """Strip malformed prefixes so bad ids never enter recent_models_* (#8 404 source).
        hf/replicate ids sometimes arrive as 'huggingface.co/x/y' or a full URL — reduce to owner/name."""
        mid = (model_id or "").strip()
        if service in ("huggingface", "replicate"):
            for pre in ("https://huggingface.co/", "http://huggingface.co/", "huggingface.co/",
                        "https://replicate.com/", "replicate.com/"):
                if mid.startswith(pre):
                    mid = mid[len(pre):]
                    break
        return mid

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
        model_id = self._normalize_model_id(service, model_id)  # keep malformed ids out of recents (#8)
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

    def civitai_search(self, query: str = "", base_model: str = "", limit: int = 24) -> dict:
        """Browse CivitAI LoRAs (public REST API; CIVITAI_API_KEY optional for higher limits).
        Returns {ok, items:[{modelId, versionId, name, baseModel, nsfw, thumb, downloadUrl, air}]}."""
        import urllib.parse
        import urllib.request
        q = {"types": "LORA", "limit": max(1, min(int(limit or 24), 50)),
             "nsfw": "true", "sort": "Most Downloaded"}
        if query:
            q["query"] = query
        if base_model:
            q["baseModels"] = base_model
        url = "https://civitai.com/api/v1/models?" + urllib.parse.urlencode(q)
        headers = {"User-Agent": "Mozilla/5.0"}
        key = os.environ.get("CIVITAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            req = urllib.request.Request(url, headers=headers)
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "items": []}
        items = []
        for m in d.get("items", []):
            vers = m.get("modelVersions") or []
            if not vers:
                continue
            v = vers[0]
            thumb = next((img.get("url") for img in (v.get("images") or []) if img.get("url")), "")
            items.append({
                "modelId": m.get("id"), "versionId": v.get("id"), "name": m.get("name"),
                "baseModel": v.get("baseModel"), "nsfw": bool(m.get("nsfw")), "thumb": thumb,
                "downloadUrl": f"https://civitai.com/api/download/models/{v.get('id')}",
                "air": f"civitai:{m.get('id')}@{v.get('id')}",
            })
        return {"ok": True, "items": items}

    def civitai_ref_for(self, service: str, model_id, version_id) -> str:
        """Convert a CivitAI model/version into the reference form the given provider accepts
        (research §Civitai): Runware = AIR `civitai:<id>@<ver>`; everyone else = direct download URL
        (Replicate accepts CivitAI URLs natively; fal/Together need a .safetensors/download URL)."""
        if service == "runware":
            return f"civitai:{model_id}@{version_id}"
        return f"https://civitai.com/api/download/models/{version_id}"

    def civitai_add_lora(self, service: str, model_id, version_id) -> dict:
        """One-click add a CivitAI LoRA to the active provider's LoRA manager, in that provider's
        correct reference form. Novita uses its own catalog (not CivitAI) — flagged, not added."""
        if service == "novita":
            return {"ok": False, "error": "Novita uses its own LoRA catalog (model_name), not CivitAI URLs.",
                    "loras": self.lora_list(service)}
        ref = self.civitai_ref_for(service, model_id, version_id)
        return {"ok": True, "loras": self.lora_add(service, ref), "ref": ref}

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

    def open_prompt_refinery(self, prompt: str = "") -> dict:
        """#3 — integrate the EXISTING prompt-refinery.html: hand the detected/analyzed prompt off
        to it (opens in the default browser; JS copies the prompt to the clipboard for paste)."""
        import webbrowser
        webbrowser.open("http://localhost:31960/prompt-refinery.html")
        return {"ok": True}

    def analyze_image(self, filename: str) -> dict:
        """#3 — img->prompt. First DETECT the original prompt (sidecar/history via read_meta);
        if unknown, ANALYZE the image with an existing fal vision model to produce a regenerable
        prompt. Reuses read_meta (#9) + the fal backend — no new generation path."""
        meta = self.read_meta(filename)
        if meta.get("prompt"):
            return {"prompt": meta["prompt"], "source": meta.get("source", "detected"),
                    "model": meta.get("model")}
        path = self._resolve(filename)
        if not os.path.exists(path):
            return {"error": "file not found"}
        try:
            from engine.backends import fal_api
            res = fal_api.generate("fal-ai/moondream3-preview/caption",
                                   {"_inputs": {"image": path}, "category": "vision"})
            if res and isinstance(res[0], dict) and res[0].get("text"):
                return {"prompt": res[0]["text"].strip(), "source": "vision",
                        "model": "fal-ai/moondream3-preview/caption"}
            return {"error": res[0] if res and isinstance(res[0], str) else "no caption returned"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def open_output_folder(self) -> dict:
        path = self.config["output_directory"]
        os.makedirs(path, exist_ok=True)
        os.startfile(path)
        return {"ok": True}

    def _resolve(self, path: str) -> str:
        """A gallery tile carries a full path; a library tile carries a basename. Resolve either
        against the output dir so file actions work from both views."""
        if path and os.path.isabs(path) and os.path.exists(path):
            return path
        return os.path.join(self.config["output_directory"], os.path.basename(path or ""))

    def open_in_editor(self, path: str) -> dict:
        """#7 — open a generated image in its registered EDITOR (Windows 'edit' verb),
        falling back to the default viewer if no editor verb is registered."""
        p = self._resolve(path)
        if not os.path.exists(p):
            return {"ok": False, "error": "file not found"}
        try:
            os.startfile(p, "edit")
        except OSError:
            try:
                os.startfile(p)
            except OSError as e:
                return {"ok": False, "error": str(e)}
        return {"ok": True}

    def read_meta(self, filename: str) -> dict:
        """#9 — metadata for one output file. Prefer the <file>.json sidecar; fall back to the
        matching basename in history.jsonl (covers images generated before sidecars existed)."""
        out_dir = self.config["output_directory"]
        name = os.path.basename(filename or "")
        for _base in (out_dir, *self._library_dirs()):
            if not _base:
                continue
            side = os.path.join(_base, name + ".json")
            if os.path.exists(side):
                try:
                    with open(side, encoding="utf-8") as f:
                        return {"source": "sidecar", **json.load(f)}
                except Exception:
                    pass
        for row in history.read(out_dir, 1000):
            if any(os.path.basename(fp) == name for fp in (row.get("files") or [])):
                return {"source": "history", "service": row.get("service"),
                        "model": row.get("model"), "prompt": row.get("prompt"),
                        "seed": row.get("seed"), "params": row.get("params", {}),
                        "ts": row.get("ts")}
        return {"source": "none", "file": name}

    def save_as(self, src_path: str) -> dict:
        import webview
        src_path = self._resolve(src_path)
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
        for _s, _k in getattr(self, "_lora_cfg", {}).items():
            self.config[_k] = self.lora_managers[_s].get_loras()
        engine_config.save(self.config)
