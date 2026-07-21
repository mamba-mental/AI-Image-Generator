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


def _load_novita_model_apis() -> list:
    from engine.backends import novita_api
    return novita_api.novita_model_apis()


# The dropdown-visible services (mirrors SVC_LABELS/state.services in app.js) — get_state() and
# _accessible_models() share this ONE list so Ask-AI can never ground on a service PRIME can't
# actually pick (civitai/ideogram-api are key-only, not generation services in the dropdown).
SERVICES = ["fal", "openai", "nvidia", "replicate", "huggingface", "gemini",
            "openrouter", "together", "runware", "novita", "cliproxy", "ideogram", "agnes"]


def _load_content_grades() -> dict:
    """Spec B §3 — the NSFW sweep's evidence, wired into per-model content grading for EVERY
    provider (not just fal). `engine/nsfw_capability.json` v2 carries the empirical evidence rows
    (keyed "provider:model" -> {grade,...}, grade in verified/refused/unclear/sfw) plus a resolved
    `excluded` snapshot; `engine/nsfw_exclusions.json` carries the REGEX exclusion RULES so a model
    added to a catalog after the last sweep is still graded `excluded` live (AC-2.5/AC-3.1) without
    waiting for a re-sweep. AC-3.1: a model with no evidence and no exclusion match is `untested`
    — the JS side never assumes permissive without one of these two sources."""
    cap_path = engine_config.resource_path("engine/nsfw_capability.json")
    exc_path = engine_config.resource_path("engine/nsfw_exclusions.json")
    cap = json.loads(cap_path.read_text(encoding="utf-8")) if cap_path.exists() else {}
    exc = json.loads(exc_path.read_text(encoding="utf-8")) if exc_path.exists() else {}
    return {
        "version": cap.get("version"),
        "generated_at": cap.get("generated_at"),
        "models": cap.get("models", {}),               # "provider:model" -> evidence row (grade,...)
        "exclusion_rules": exc.get("exclusions", []),   # [{id_pattern, reason, policy_source_url}]
    }


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
        self._ensure_output_registered()  # #6 — generations land in a scanned folder from boot
        # LoRA-capable services (each backend translates {url,scale} to its own request shape).
        self._lora_cfg = {"huggingface": "recent_loras_hf", "replicate": "recent_loras_replicate",
                          "fal": "recent_loras_fal", "together": "recent_loras_together",
                          "runware": "recent_loras_runware", "novita": "recent_loras_novita"}
        self.lora_managers = {s: LoRAManager(s) for s in self._lora_cfg}
        for _s, _k in self._lora_cfg.items():
            self.lora_managers[_s].load_from_config(self.config.get(_k, []))

    # ---- state ----

    def _recent_models_map(self) -> dict:
        """The per-service recent/seed model list (config override, else the labelled offline
        seed) — shared by get_state() (dropdown) and _accessible_models() (Ask-AI grounding), so
        the two can never drift apart."""
        return {
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
            # Novita — REAL catalog checkpoint names (from GET /v3/model?type=checkpoint; NOT urls).
            # Community NSFW-capable photoreal + anime; Novita doesn't force moderation. Browse more
            # at novita.ai/models. epicrealism confirmed generating 2026-07-20.
            "novita": self.config.get("recent_models_novita", []) or [
                "epicrealism_naturalSinRC1VAE_106430.safetensors", "epicphotogasm_xPlusPlus_135412.safetensors",
                "realisticAfmix_realisticAfmix_75178.safetensors", "revAnimated_v122.safetensors"],
            # E1 — cliproxy image models routable via /v1/images/generations (verified live)
            "cliproxy": self.config.get("recent_models_cliproxy", []) or [
                "gpt-image-2", "gpt-image-1.5", "grok-imagine-image"],
            # Ideogram = Plus subscription via web session; model auto-selected server-side
            "ideogram": self.config.get("recent_models_ideogram", []) or ["auto"],
            # AGNES-AI (Sapiens) — image via /v1/images/generations; video via async /v1/videos
            # (create → poll GET /agnesapi?video_id). All verified live 2026-07-20.
            "agnes": self.config.get("recent_models_agnes", []) or [
                "agnes-image-2.1-flash", "agnes-image-2.0-flash", "agnes-video-v2.0"],
        }

    def get_state(self) -> dict:
        return {
            "services": SERVICES,
            "active_service": self.config.get("service", "fal"),
            "config": {k: v for k, v in self.config.items()
                       if k not in ("replicate_api_key", "huggingface_token",
                                    "gemini_api_key", "fal_api_key")},
            "fal_models": _load_fal_models(),
            "service_params": _load_service_params(),
            "content_grades": _load_content_grades(),  # Spec B §3 — sweep evidence, every provider
            "recent_models": self._recent_models_map(),
            # E2 — Novita's modern "Model APIs" (Seedream/Qwen-Image/Z-Image-Turbo). No list
            # endpoint exists for these (Spec B AC-1.7) → the sanctioned offline seed from
            # engine/backends/novita_api.MODEL_APIS, surfaced as its own dropdown group.
            "novita_model_apis": _load_novita_model_apis(),
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

    def _accessible_models(self) -> list:
        """§4 AC-4.2 — every model across providers PRIME can ACTUALLY reach (a resolved key),
        server-side mirror of app.js's accessibleModels(). Shares the exact sources get_state()
        feeds the dropdown (fal catalog, per-service recent/seed list, Novita's Model-APIs seed)
        so suggest_model() can never ground an answer in something behind a missing key."""
        from engine.backends import novita_api
        recent = self._recent_models_map()
        out = []
        for svc in SERVICES:
            if not self.keys_status.get(svc):
                continue
            if svc == "fal":
                models = [{"id": m["id"], "label": m.get("label", m["id"])}
                          for m in _load_fal_models() if m.get("category") == "text-to-image"]
            elif svc == "novita":
                models = [{"id": mid, "label": mid} for mid in (recent.get(svc) or [])] + \
                         [{"id": mid, "label": mid} for mid in novita_api.novita_model_apis()]
            else:
                models = [{"id": mid, "label": mid} for mid in (recent.get(svc) or [])]
            out.extend({"id": m["id"], "label": m["label"], "service": svc} for m in models)
        return out

    def suggest_model(self, query: str) -> dict:
        """§4 AC-4.2/4.3 — the Ask-AI model reply. Grounds the answer ONLY in models PRIME can
        actually reach (_accessible_models — keyed providers only) plus their content grade and
        the active Content Mode, via a compact system prompt to cliproxy's chat/completions.
        The reply is hard-filtered afterward so an id outside the accessible set can never render
        — a guard against hallucination, not a courtesy (AC-4.2)."""
        import urllib.error
        import urllib.request
        query = (query or "").strip()
        if not query:
            return {"ok": False, "error": "empty query"}
        accessible = self._accessible_models()
        if not accessible:
            return {"ok": False, "error": "no accessible models — add a provider key in Settings first"}
        key = (os.environ.get("CLIPROXY_API_KEY") or "").strip().strip("'\"")  # wrapping-quote bug guard
        if not key:
            return {"ok": False, "error": "cliproxy unreachable — CLIPROXY_API_KEY not configured"}
        base = os.environ.get("CLIPROXY_BASE_URL", "http://192.168.86.191:8317/v1").rstrip("/")
        grades = _load_content_grades().get("models", {})
        mode = self.config.get("ui_content_mode", "safe")
        lines = []
        for m in accessible[:400]:  # keep the prompt bounded even with fal's ~1300-row catalog in scope
            gid = f"{m['service']}:{m['id']}"
            lines.append(f"{gid} (grade={grades.get(gid, {}).get('grade', 'untested')})")
        system = (
            "You are the model picker for an image/video generation app. Recommend ONLY from the "
            "ACCESSIBLE MODELS list below (service:id) — never invent or suggest an id that isn't "
            f"listed. Active content mode: {mode}. Reply with up to 3 picks, one per line: "
            "`model id · provider · one-line why`.\n\nACCESSIBLE MODELS:\n" + "\n".join(lines)
        )
        body = {"model": os.environ.get("MODEL_SUGGEST_MODEL", "gpt-5.5"),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": query}],
                "max_tokens": 400}
        req = urllib.request.Request(
            base + "/chat/completions", data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
            text = d["choices"][0]["message"]["content"]
        except Exception as e:
            return {"ok": False, "error": f"cliproxy unreachable ({type(e).__name__})"}
        picks = [m for m in accessible if m["id"] in text][:3]  # AC-4.2 hard guard — accessible-only
        return {"ok": True, "text": text, "picks": picks}

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

    def novita_models(self, limit: int = 100) -> list:
        """Live Novita checkpoint catalog (sd_name strings) for the model dropdown — so the exact
        model names never have to be guessed. Returns [] without a NOVITA_API_KEY."""
        import urllib.request
        key = os.environ.get("NOVITA_API_KEY")
        if not key:
            return []
        try:
            u = f"https://api.novita.ai/v3/model?type=checkpoint&pagination.limit={int(limit)}"
            req = urllib.request.Request(u, headers={"Authorization": f"Bearer {key}"})
            d = json.loads(urllib.request.urlopen(req, timeout=20).read())
            names = []
            for m in (d.get("models") or []):
                n = m.get("sd_name") or m.get("name")
                if n and n not in names:
                    names.append(n)
            return names
        except Exception:
            return []

    # OpenAI-compatible catalog endpoints (same URLs the key-validator uses) → live model lists,
    # so these providers' dropdowns stop being hardcoded guesses (issue #1). Novita has its own
    # method above (non-OpenAI shape); runware/ideogram expose no list API → offline seeds (AC-1.7).
    _CATALOG = {
        "together": ("https://api.together.xyz/v1/models",
                     lambda k: {"Authorization": f"Bearer {k}", "User-Agent": "Mozilla/5.0"}),
        "agnes": ("https://apihub.agnes-ai.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
        "nvidia": ("https://integrate.api.nvidia.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
        "openai": ("https://api.openai.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
        "openrouter": ("https://openrouter.ai/api/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
    }
    # id substrings that hint an image/video model (used only to PREFER image models, never to hide —
    # if the filter finds nothing we return the full live list rather than guess it empty).
    _IMG_HINTS = ("flux", "image", "imagen", "sd", "stable", "dall", "kontext", "qwen-image",
                  "seedream", "playground", "recraft", "ideogram", "sana", "pixart", "kolors",
                  "wan", "hunyuan", "ltx", "video", "veo", "kling", "hidream", "nano-banana")

    def provider_models(self, service: str, limit: int = 300) -> dict:
        """Live model catalog for an OpenAI-compatible provider (issue #1 — no more guessed lists).
        Returns {ok, live, models:[ids], filtered:bool, note}. Empty models + a note when there's no
        key or the fetch fails, so the frontend can fall back to its labelled offline seeds."""
        import urllib.request
        spec = self._CATALOG.get(service)
        if not spec:
            return {"ok": False, "live": False, "models": [], "note": "no live catalog (uses offline seeds)"}
        field = engine_config.KEY_FIELDS.get(service)
        key = os.environ.get(field[1]) if field else None
        if not key:
            return {"ok": False, "live": False, "models": [], "note": "no key set"}
        url, hdr = spec
        try:
            req = urllib.request.Request(url, headers=hdr(key))
            d = json.loads(urllib.request.urlopen(req, timeout=20).read())
            data = d.get("data") if isinstance(d, dict) else d   # together returns a bare array
            ids, typed_img = [], []
            for m in (data or []):
                if isinstance(m, dict):
                    mid = m.get("id") or m.get("name")
                    if (m.get("type") or "").lower() in ("image", "video"):
                        typed_img.append(mid)
                else:
                    mid = m
                if mid and mid not in ids:
                    ids.append(mid)
            # prefer provider-declared image/video types; else id-hint filter; else the full list
            if typed_img:
                models, filtered = typed_img, True
            else:
                hinted = [i for i in ids if any(h in i.lower() for h in self._IMG_HINTS)]
                models, filtered = (hinted, True) if hinted else (ids, False)
            return {"ok": True, "live": True, "models": models[:int(limit)], "filtered": filtered,
                    "note": f"{len(models)} live model(s)" + ("" if filtered else " — unfiltered")}
        except Exception as e:
            return {"ok": False, "live": False, "models": [],
                    "note": f"catalog fetch failed ({type(e).__name__})"}

    # LoRA-capable services that accept an ARBITRARY HF .safetensors URL (novita = own-catalog
    # only, runware = CivitAI AIRs — both excluded by design, not oversight).
    _LORA_URL_SVCS = ("fal", "together", "replicate", "huggingface")

    def import_lora(self, ref: str, scale: float = 0.8) -> dict:
        """Convert a HuggingFace LoRA repo/URL into the artifact every URL-capable provider needs,
        and register it in their LoRA pickers in one shot (PRIME's personal LoRAs importer).

        Accepts: 'user/repo', a huggingface.co repo URL, or a direct .safetensors URL.
        Resolves the repo's weight file via the HF API, then add_lora()s it into fal/together/
        replicate/hf managers ({url, scale, enabled} — each backend translates to its own shape).
        """
        import re as _re
        import urllib.request
        ref = (ref or "").strip()
        if not ref:
            return {"ok": False, "error": "empty ref"}
        url = None
        if ref.lower().endswith((".safetensors", ".bin")) and ref.startswith("http"):
            url = ref
        else:
            m = _re.search(r"(?:huggingface\.co/)?([\w.-]+/[\w.-]+)", ref)
            if not m:
                return {"ok": False, "error": "unrecognized ref — pass user/repo or a URL"}
            repo = m.group(1)
            try:
                d = json.loads(urllib.request.urlopen(
                    f"https://huggingface.co/api/models/{repo}", timeout=20).read())
                weights = [s["rfilename"] for s in d.get("siblings", [])
                           if s["rfilename"].endswith(".safetensors")]
                if not weights:
                    return {"ok": False, "error": f"no .safetensors in {repo}"}
                url = f"https://huggingface.co/{repo}/resolve/main/{weights[0]}"
            except Exception as e:
                return {"ok": False, "error": f"HF lookup failed: {type(e).__name__}"}
        added = []
        for svc in self._LORA_URL_SVCS:
            mgr = self.lora_managers.get(svc)
            if mgr and mgr.add_lora(url, scale=scale):
                added.append(svc)
        self._persist()  # serializes every manager back to config (get_loras) + saves
        return {"ok": True, "url": url, "added_to": added,
                "note": "novita (own catalog) + runware (CivitAI AIRs) can't take HF URLs"}

    def set_config(self, patch: dict) -> dict:
        # #6 AC-6.3 — a drive/share root or non-writable output dir is rejected BEFORE it's applied,
        # so `output_directory` can never be set to `I:\` (the NAS root) again.
        if "output_directory" in patch:
            from engine import save
            ok, msg = save.validate_output_root(patch["output_directory"])
            if not ok:
                return {"ok": False, "error": msg}
        for k, v in dict(patch).items():
            if k == "parameters" and isinstance(v, dict):
                self.config.setdefault("parameters", {}).update(v)
            else:
                self.config[k] = v
        if "output_directory" in patch:
            mediaserver.set_dir(self.config["output_directory"])
            self._ensure_output_registered()   # keep the new output's generated/ folder scanned
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
        # Cloudflare-fronted providers 403 the default urllib UA → send a browser UA.
        "together": ("https://api.together.xyz/v1/models",
                     lambda k: {"Authorization": f"Bearer {k}", "User-Agent": "Mozilla/5.0"}),
        "novita": ("https://api.novita.ai/v1/billing/balance/detail", lambda k: {"Authorization": f"Bearer {k}"}),
        "agnes": ("https://apihub.agnes-ai.com/v1/models", lambda k: {"Authorization": f"Bearer {k}"}),
        "civitai": ("https://civitai.com/api/v1/models?limit=1",
                    lambda k: {"Authorization": f"Bearer {k}", "User-Agent": "Mozilla/5.0"}),
    }

    def validate_key(self, service: str, key: str = "") -> dict:
        """Live-check a key against its provider (2xx = accepted). If key is empty,
        validate the currently-resolved key. Key value is never echoed back."""
        import urllib.error
        import urllib.request
        probe = self._VALIDATE.get(service)
        if not probe:
            # A KEY_FIELDS service without a live-validation probe (e.g. runware/ideogram) still
            # SAVED its key — we just can't confirm it live. valid=None -> frontend shows it neutrally.
            known = service in engine_config.KEY_FIELDS
            return {"valid": None if known else False, "http": 0,
                    "detail": "saved (no live validation for this provider)" if known else f"unknown service {service}"}
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

    def _index(self):
        """The SQLite Library Index (ADR 0001), lazily opened once per Api. Replaces the old flat
        JSON cache: metadata is stored as columns, folders are indexed independently and keyed by a
        change signature, so a warm open is a pure local-DB read and a folder toggle is a flag flip
        — never a NAS re-crawl. Colocated with the old index dir; migrates the legacy JSON once."""
        idx = getattr(self, "_lib_idx", None)
        if idx is None:
            from engine.library_index import LibraryIndex
            db = os.path.join(os.path.dirname(self._library_index_path()), "library.db")
            idx = LibraryIndex(db)
            idx.migrate_from_json(self._library_index_path())  # one-time import → instant first open
            self._lib_idx = idx
        return idx

    def _ensure_output_registered(self) -> None:
        """Guarantee the output `generated/` root is in the Library scan set so fresh generations are
        findable (#6, AC-6.2). Idempotent — the common case is a cheap membership check."""
        from engine import save
        root = save.generated_root(self.config.get("output_directory", ""))
        if not root or root in self._all_library_dirs():
            return
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            return
        dirs = self.config.get("library_directories")
        base = list(dirs) if isinstance(dirs, list) else self._all_library_dirs()
        self.config["library_directories"] = base + [root]
        try:
            mediaserver.add_root(root)
        except Exception:
            pass
        self._persist()

    def refresh_generated(self) -> dict:
        """Re-index ONLY the current output month-folder so a just-saved image is findable
        immediately, without re-crawling the whole NAS (#6, AC-6.2). Called by the UI after a job."""
        from engine import save
        month = save.month_dir(self.config.get("output_directory", ""))
        if month and os.path.isdir(month):
            try:
                self._index().index_folder(month)
            except Exception:
                pass
        return {"ok": True}

    def list_library(self, limit: int = 8000, refresh: bool = False) -> list:
        """LIBRARY view source. Returns de-duped basenames across every enabled archive.

        Backed by the SQLite Library Index (`.cache/library.db`, ADR 0001). A warm call is a single
        local-DB query with ZERO NAS access — the ~5k-file crawl only runs on first index of a
        folder, or on an explicit `refresh=True` (the ↻ button) for folders whose signature changed.
        Toggling a folder never re-crawls (it changes which bases are queried)."""
        bases = [d for d in self._library_dirs() if os.path.isdir(d)] or [self.config["output_directory"]]
        idx = self._index()
        if refresh:
            idx.refresh(bases, force=True)      # explicit ↻ — re-sign + re-index changed folders
        else:
            idx.ensure_indexed(bases)           # first-run only; already-indexed folders = pure DB read
        return idx.list_images(bases, int(limit))

    def refresh_library(self, limit: int = 8000) -> list:
        """Force a re-index of changed folders + return the fresh list (the Library ↻ refresh button)."""
        return self.list_library(limit=limit, refresh=True)

    # ---- tags (Spec C #8) ---------------------------------------------------------

    def _resolve_full(self, file: str, dir: str = "") -> str:
        """Resolve a (file, dir) pair from the JS side into ONE absolute path — `dir`
        disambiguates duplicate basenames across library folders (list_library de-dupes by name
        for DISPLAY only; the DB/tag identity is the full path). Falls back to the legacy
        basename-only `_resolve()` when dir is empty (session-gallery tiles already carry an
        absolute path in `file`)."""
        if dir:
            cand = os.path.join(dir, os.path.basename(file or ""))
            if os.path.exists(cand):
                return cand
        return self._resolve(file)

    def _sidecar_meta_for_embed(self, path: str) -> dict:
        """The generation metadata to mirror into the embedded copy on a tag edit (AC-8.6) —
        reuses read_meta's sidecar lookup so the embed carries the real provider/model/seed/
        prompt/negative/params, not just the tag list."""
        m = self.read_meta(os.path.basename(path))
        params = m.get("params") or {}
        return {"provider": m.get("service"), "model": m.get("model"), "seed": m.get("seed"),
                "prompt": m.get("prompt"), "negative": params.get("negative_prompt"), "params": params}

    def _reembed_tags(self, path: str, tags: list) -> None:
        """Mirror a manual tag edit into the file's durable embedded copy (AC-8.2/8.6). Never
        blocks: on failure the DB row (already updated) stays the source of truth."""
        try:
            from engine import embed_meta
            meta = self._sidecar_meta_for_embed(path)
            meta["tags"] = tags
            embed_meta.write_embedded_meta(path, meta)
        except Exception as e:
            print(f"tag embed failed for {path}: {e}")

    def get_image_tags(self, file: str, dir: str = "") -> dict:
        path = self._resolve_full(file, dir)
        if not path or not os.path.exists(path):
            return {"tags": []}
        return {"tags": self._index().get_tags(path)}

    def add_tag(self, file: str, tag: str, dir: str = "") -> dict:
        tag = (tag or "").strip()
        path = self._resolve_full(file, dir)
        if not tag or not path or not os.path.exists(path):
            return {"ok": False, "error": "empty tag or file not found"}
        idx = self._index()
        ext = Path(path).suffix.lower()
        idx.ensure_row(path, os.path.dirname(path), os.path.basename(path),
                       "video" if ext in (".mp4", ".webm", ".mov") else "image")
        tags = idx.add_tag(path, tag)
        self._reembed_tags(path, tags)
        return {"ok": True, "tags": tags}

    def remove_tag(self, file: str, tag: str, dir: str = "") -> dict:
        path = self._resolve_full(file, dir)
        if not path or not os.path.exists(path):
            return {"ok": False, "error": "file not found"}
        tags = self._index().remove_tag(path, tag)
        self._reembed_tags(path, tags)
        return {"ok": True, "tags": tags}

    # ---- vision auto-tagging (AC-8.7) ----------------------------------------------

    def vision_tagging_status(self) -> dict:
        from engine import vision_tagging
        return {"configured": vision_tagging.is_configured(), "endpoint": vision_tagging.base_url_label()}

    def start_vision_tag_backfill(self, limit: int = 200) -> dict:
        """Kicks off a non-blocking background batch over the untagged backlog (AC-8.7). Off
        unless a vision endpoint resolves; never blocks the caller (returns immediately, the
        batch runs on its own daemon thread)."""
        from engine import vision_tagging
        if not vision_tagging.is_configured():
            return {"ok": False, "error": "no vision endpoint configured"}
        bases = [d for d in self._library_dirs() if os.path.isdir(d)] or [self.config["output_directory"]]
        idx = self._index()
        paths = idx.untagged_paths(bases, limit=int(limit))
        if not paths:
            return {"ok": True, "queued": 0}
        import threading
        threading.Thread(target=vision_tagging.batch_tag, args=(paths, idx), daemon=True).start()
        return {"ok": True, "queued": len(paths)}

    # ---- presets: Style / Recipe (Spec C #4) ----------------------------------------
    # Two distinct objects, never conflated (CONTEXT.md glossary): a Style is reusable/prompt-
    # optional; a Recipe reproduces ONE exact image and is provider-pinned. Both live in
    # library.db (same store as the index, AC-4.1/4.5) via LibraryIndex's styles/recipes tables.

    def save_style(self, data: dict) -> dict:
        pid = self._index().save_preset("styles", data or {})
        return {"ok": True, "id": pid}

    def save_recipe(self, data: dict) -> dict:
        pid = self._index().save_preset("recipes", data or {})
        return {"ok": True, "id": pid}

    def list_styles(self) -> list:
        return self._index().list_presets("styles")

    def list_recipes(self) -> list:
        return self._index().list_presets("recipes")

    def rename_style(self, preset_id: int, name: str) -> dict:
        self._index().rename_preset("styles", int(preset_id), name)
        return {"ok": True}

    def rename_recipe(self, preset_id: int, name: str) -> dict:
        self._index().rename_preset("recipes", int(preset_id), name)
        return {"ok": True}

    def delete_style(self, preset_id: int) -> dict:
        self._index().delete_preset("styles", int(preset_id))
        return {"ok": True}

    def delete_recipe(self, preset_id: int) -> dict:
        self._index().delete_preset("recipes", int(preset_id))
        return {"ok": True}

    def set_default_style(self, preset_id: int) -> dict:
        self._index().set_default_preset("styles", int(preset_id))
        return {"ok": True}

    def set_default_recipe(self, preset_id: int) -> dict:
        self._index().set_default_preset("recipes", int(preset_id))
        return {"ok": True}

    def get_default_presets(self) -> dict:
        """Applied on launch (AC-4.2) — boot() reads this once and applies each default that exists."""
        idx = self._index()
        return {"style": idx.get_default_preset("styles"), "recipe": idx.get_default_preset("recipes")}

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
        try:
            self._index().set_folder_enabled(path, enabled)  # keep the index flag in sync (pure DB flip)
        except Exception:
            pass
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
            if service == "novita":
                key = os.environ.get("NOVITA_API_KEY")
                if not key:
                    return {"label": "no key", "kind": "none"}
                d = json.loads(urllib.request.urlopen(urllib.request.Request(
                    "https://api.novita.ai/openapi/v1/billing/balance/detail",
                    headers={"Authorization": f"Bearer {key}"}), timeout=15).read())
                bal = float(d.get("availableBalance") or 0) / 10000  # availableBalance is 1/10000 USD
                return {"label": f"${bal:.2f}", "kind": "low" if bal < 2 else "ok"}
        except Exception as e:
            return {"label": f"balance unavailable ({type(e).__name__})", "kind": "none"}
        # Providers without a live balance API — consistent footer label from key presence (no more blanks).
        _labels = {"together": "usage-based · together.ai", "runware": "usage-based · runware.ai",
                   "cliproxy": "self-hosted gateway", "agnes": "usage-based · AGNES",
                   "ideogram": "subscription", "ideogram-api": "usage-based", "civitai": "LoRA source"}
        has_key = bool(self.keys_status.get(service))
        return {"label": (_labels.get(service, "usage-based") if has_key else "no key"),
                "kind": "info" if has_key else "none"}

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
