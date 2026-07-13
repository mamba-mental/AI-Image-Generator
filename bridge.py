#!/usr/bin/env python3
"""
Python<->JS bridge for AI Studio Void web UI (pywebview).
v2: multi-provider registry (webui/models.json) per the credit-access ladder —
fal (image+video) / Together / OpenAI / Replicate / Gemini / HF(keyless-greyed).
Every data-api="<name>" in webui/index.html resolves to a public method here.
Higgsfield is RETIRED (0 credits) and deliberately absent.
"""
import base64, json, os, threading, time, urllib.request
import http.server, socketserver
from pathlib import Path

import providers as _providers  # provider adapters (fal live; more in P4)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / "generated_images"
MEDIA_DIR = ROOT / "generated_media"
IMG_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)

DIMS_TO_FAL = {
    "1:1": "square", "4:3": "landscape_4_3", "16:9": "landscape_16_9",
    "3:4": "portrait_3_4", "9:16": "portrait_9_16", "2K": "square_hd",
}
DIMS_TO_WH = {
    "1:1": (1024, 1024), "4:3": (1152, 896), "16:9": (1344, 768),
    "3:4": (896, 1152), "9:16": (768, 1344), "2K": (2048, 2048),
}
DIMS_TO_OPENAI = {
    "1:1": "1024x1024", "4:3": "1536x1024", "16:9": "1536x1024",
    "3:4": "1024x1536", "9:16": "1024x1536", "2K": "1024x1024",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}


_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

def _http_json(url, headers, body=None, timeout=60):
    # Browser UA: some provider edges (Cloudflare WAF) 403 the default Python-urllib UA.
    headers = {"User-Agent": _UA, **headers}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class _MediaHandler(http.server.SimpleHTTPRequestHandler):
    """Serves generated_images/ under /gi/ and generated_media/ under /gm/.
    WebView2 will not load file:// media from a file:// page — localhost origin
    is load-bearing."""
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/gi/"):
            return str(IMG_DIR / path[4:])
        if path.startswith("/gm/"):
            return str(MEDIA_DIR / path[4:])
        return str(ROOT / path.lstrip("/"))


class Api:
    def __init__(self, start_server=True, media_port=0, state_dir=None):
        self.state_dir = Path(state_dir) if state_dir else ROOT
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._cfg_path = self.state_dir / "void_web_config.json"
        self._hist_path = self.state_dir / "prompt_history.json"
        self._cfg = self._load_json(self._cfg_path, {"loras": []})
        self._registry = self._load_json(ROOT / "webui" / "models.json", {"providers": {}, "models": []})
        from loramanager import LoRAManager
        self._lora = LoRAManager(backend="fal")
        self._lora.load_from_config(self._cfg.get("loras", []))
        self._httpd = None
        self._port = None
        if start_server:
            self._start_media_server(media_port)

    # ---------- infra ----------
    def _load_json(self, p, default):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save_cfg(self):
        self._cfg["loras"] = self._lora.get_loras()
        self._cfg_path.write_text(json.dumps(self._cfg, indent=2), encoding="utf-8")

    def _start_media_server(self, port):
        self._httpd = socketserver.TCPServer(("127.0.0.1", port), _MediaHandler)
        self._port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def shutdown(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def _base(self):
        return f"http://127.0.0.1:{self._port}"

    # ---------- catalog ----------
    def providers(self):
        """[{name, label, ready}] — ready = its env key is set. Greyed chips never fake-active."""
        out = []
        for name, meta in self._registry["providers"].items():
            out.append({"name": name, "label": meta["label"],
                        "ready": bool(os.environ.get(meta["key_env"]))})
        return out

    def models(self):
        """Full static registry (non-fal providers / legacy UI). fal uses catalog() live."""
        return self._registry

    # ---------- schema-driven catalog + forms (P1) ----------
    def catalog(self, provider, kind=None, refresh=False):
        """[{id,label,kind}] for a provider. fal = live; others = static registry."""
        adapter = _providers.get(provider)
        if adapter:
            return adapter.list_models(kind=kind, refresh=refresh) if refresh else adapter.list_models(kind=kind)
        out = [{"id": m["id"], "label": m["label"], "kind": m["kind"]}
               for m in self._registry["models"] if m["provider"] == provider]
        return [m for m in out if not kind or m["kind"] == kind]

    def form_spec(self, model_id, provider=None):
        """Live FormSpec for fal; static FormSpec for other providers."""
        if provider is None:
            provider = self._provider_of(model_id)
        adapter = _providers.get(provider)
        if adapter:
            return adapter.form_spec(model_id)
        return self._static_form_spec(model_id)

    def _provider_of(self, model_id):
        for p in _providers.registry():
            if any(m["id"] == model_id for m in _providers.get(p).list_models()):
                return p
        entry = next((m for m in self._registry["models"] if m["id"] == model_id), None)
        return entry["provider"] if entry else "fal"

    _DIMS = ["1:1", "4:3", "16:9", "3:4", "9:16", "2K"]

    def _static_form_spec(self, model_id):
        """Basic per-param form for non-fal models (from models.json 'params')."""
        entry = next((m for m in self._registry["models"] if m["id"] == model_id), {})
        want = set(entry.get("params", []))
        fields = []
        if "batch" in want:
            fields.append({"name": "num_images", "widget": "number", "int": True, "default": 1, "label": "Batch"})
        if "dims" in want:
            fields.append({"name": "dims", "widget": "select", "enum": self._DIMS, "default": "1:1", "label": "Dimensions"})
        if "guidance" in want:
            fields.append({"name": "guidance", "widget": "slider", "min": 0, "max": 10, "step": 0.5, "default": 3.5, "int": False, "label": "Guidance"})
        if "seed" in want:
            fields.append({"name": "seed", "widget": "number", "int": True, "label": "Seed"})
        if entry.get("image_input"):
            fields.append({"name": entry["image_input"], "widget": "image", "multi": entry["image_input"].endswith("s"), "label": "Source image"})
        return fields

    # ---------- LoRA stack ----------
    def lora_add(self, url, scale=0.8):
        ok = self._lora.add_lora(url, float(scale), True)
        self._save_cfg()
        return ok

    def lora_remove(self, index):
        self._lora.remove_lora(int(index)); self._save_cfg(); return self._lora.get_loras()

    def lora_set_scale(self, index, scale):
        self._lora.set_scale(int(index), float(scale)); self._save_cfg(); return self._lora.get_loras()

    def lora_toggle(self, index):
        cur = self._lora.get_lora_by_index(int(index))
        if cur is not None:
            self._lora.set_enabled(int(index), not cur.get("enabled", True))
            self._save_cfg()
        return self._lora.get_loras()

    def lora_list(self):
        return self._lora.get_loras()

    # ---------- prompt history ----------
    def history_add(self, prompt):
        hist = self._load_json(self._hist_path, [])
        prompt = (prompt or "").strip()
        if prompt:
            hist = [prompt] + [h for h in hist if h != prompt]
            self._hist_path.write_text(json.dumps(hist[:200], indent=2), encoding="utf-8")
        return hist[:200]

    def history_list(self):
        return self._load_json(self._hist_path, [])

    # ---------- gallery ----------
    def gallery(self, limit=24):
        items = []
        for d, prefix in ((IMG_DIR, "gi"), (MEDIA_DIR, "gm")):
            for f in d.iterdir():
                if not f.is_file():
                    continue
                ext = f.suffix.lower()
                k = "image" if ext in IMAGE_EXTS else ("video" if ext in VIDEO_EXTS else None)
                if k is None:
                    continue
                items.append({"name": f.name, "kind": k, "mtime": f.stat().st_mtime,
                              "url": f"{self._base}/{prefix}/{f.name}"})
        items.sort(key=lambda x: x["mtime"], reverse=True)
        return items[:int(limit)]

    # ---------- generate (P1: params dict from the schema-driven form) ----------
    def generate(self, model_id, params, provider="fal"):
        """params carries 'prompt' + the model's schema fields (from webui/form.js collectParams)."""
        params = dict(params or {})
        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            return {"error": "empty prompt"}
        try:
            adapter = _providers.get(provider)
            if adapter:  # fal (live schema path)
                spec = adapter.form_spec(model_id)
                if any(f.get("widget") == "loras" for f in spec):
                    enabled = [l for l in self._lora.get_loras() if l.get("enabled")]
                    if enabled:
                        params["loras"] = [{"path": l["url"], "scale": l["scale"]} for l in enabled]
                return adapter.submit(model_id, params)
            return self._gen_legacy(provider, model_id, params)  # non-fal (static path)
        except Exception as e:
            return {"error": f"{provider} generation failed: {type(e).__name__}: {e}"}

    def _gen_legacy(self, provider, model_id, params):
        prompt = params.get("prompt", "")
        batch = int(params.get("num_images", 1))
        seed = params.get("seed")
        dims = params.get("dims", "1:1")
        guidance = params.get("guidance", 3.5)
        if provider == "together":
            return self._gen_together(prompt, model_id, batch, False)
        if provider == "openai":
            return self._gen_openai(prompt, model_id, batch, dims, False)
        if provider == "replicate":
            return self._gen_replicate(prompt, model_id, seed, dims, guidance, False)
        if provider == "gemini":
            return self._gen_gemini(prompt, model_id, dims, False)
        if provider == "hf":
            if not os.environ.get("HUGGINGFACE_TOKEN"):
                return {"error": "HUGGINGFACE_TOKEN not set — HF is greyed until a token is added to .env"}
            return self._gen_hf(prompt, model_id, seed)
        return {"error": f"unknown provider '{provider}'"}

    # ----- fal (image + video) -----
    def _gen_fal(self, prompt, model, entry, kind, batch, seed, dims, guidance, dry_run, image_data):
        key = os.environ.get("FAL_KEY", "")
        enabled_loras = [l for l in self._lora.get_loras() if l.get("enabled")]
        if enabled_loras and model == "fal-ai/flux-2/turbo":
            model = "fal-ai/flux-2/lora"
            entry = next((m for m in self._registry["models"] if m["id"] == model), entry)
        payload = {"prompt": prompt}
        if kind == "image":
            payload["num_images"] = int(batch)
            payload["image_size"] = DIMS_TO_FAL.get(dims, "square")
            if seed is not None:
                payload["seed"] = int(seed)
            if entry.get("uses_loras") and enabled_loras:
                payload["loras"] = [{"path": l["url"], "scale": l["scale"]} for l in enabled_loras]
        img_param = entry.get("image_input")
        if img_param and image_data:
            payload[img_param] = [image_data] if img_param.endswith("s") else image_data
        spec = {"url": f"https://queue.fal.run/{model}",
                "headers": {"Authorization": f"Key {key}", "Content-Type": "application/json"},
                "payload": payload}
        if dry_run:
            return spec
        if not key:
            return {"error": "FAL_KEY not set"}
        files = self._fal_submit_and_wait(spec, timeout=600 if kind == "video" else 180, kind=kind)
        return {"files": files, "model": model}

    def _fal_submit_and_wait(self, spec, timeout=180, kind="image"):
        def _get(url):
            req = urllib.request.Request(url, headers=spec["headers"])
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        submit = _http_json(spec["url"], spec["headers"], spec["payload"])
        status_url, resp_url = submit.get("status_url"), submit.get("response_url")
        if not status_url:
            return self._save_result(submit, kind)
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = _get(status_url)
            if st.get("status") == "COMPLETED":
                return self._save_result(_get(resp_url), kind)
            if st.get("status") in ("FAILED", "ERROR"):
                raise RuntimeError(st)
            time.sleep(2.5 if kind == "video" else 1.5)
        raise TimeoutError(f"fal queue timed out after {timeout}s")

    def _save_result(self, result, kind):
        """Handles fal image ({images:[{url}]}) and video ({video:{url}}) result shapes."""
        urls = []
        if kind == "video":
            v = result.get("video") or {}
            if v.get("url"):
                urls = [v["url"]]
        if not urls:
            urls = [im["url"] for im in result.get("images", []) if im.get("url")]
        if not urls:
            raise RuntimeError(f"no media in result: {list(result.keys())}")
        return self._download(urls, MEDIA_DIR if kind == "video" else IMG_DIR,
                              default_ext=".mp4" if kind == "video" else ".png")

    def _download(self, urls, dest, default_ext=".png"):
        saved = []
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for i, u in enumerate(urls):
            ext = os.path.splitext(u.split("?")[0])[1] or default_ext
            suffix = "_image" if len(urls) == 1 else f"_batch{i+1}of{len(urls)}"
            out = dest / f"{stamp}{suffix}{ext}"
            # Browser UA: provider CDNs (e.g. Together's Cloudflare-fronted shrt links) 403 the urllib UA.
            req = urllib.request.Request(u, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                out.write_bytes(r.read())
            saved.append(str(out))
        return saved

    def _save_b64(self, b64_list, dest, ext=".png"):
        saved = []
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for i, b in enumerate(b64_list):
            suffix = "_image" if len(b64_list) == 1 else f"_batch{i+1}of{len(b64_list)}"
            out = dest / f"{stamp}{suffix}{ext}"
            out.write_bytes(base64.b64decode(b))
            saved.append(str(out))
        return saved

    # ----- Together -----
    def _gen_together(self, prompt, model, batch, dry_run):
        key = os.environ.get("TOGETHER_API_KEY", "")
        spec = {"url": "https://api.together.xyz/v1/images/generations",
                "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                "payload": {"model": model, "prompt": prompt, "n": int(batch)}}
        if dry_run:
            return spec
        if not key:
            return {"error": "TOGETHER_API_KEY not set"}
        res = _http_json(spec["url"], spec["headers"], spec["payload"], timeout=180)
        data = res.get("data", [])
        urls = [d["url"] for d in data if d.get("url")]
        b64s = [d["b64_json"] for d in data if d.get("b64_json")]
        files = (self._download(urls, IMG_DIR) if urls else []) + \
                (self._save_b64(b64s, IMG_DIR) if b64s else [])
        if not files:
            raise RuntimeError(f"no images in Together response: {list(res.keys())}")
        return {"files": files, "model": model}

    # ----- OpenAI -----
    def _gen_openai(self, prompt, model, batch, dims, dry_run):
        key = os.environ.get("OPENAI_API_KEY", "")
        spec = {"url": "https://api.openai.com/v1/images/generations",
                "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                "payload": {"model": model, "prompt": prompt, "n": int(batch),
                            "size": DIMS_TO_OPENAI.get(dims, "1024x1024")}}
        if dry_run:
            return spec
        if not key:
            return {"error": "OPENAI_API_KEY not set"}
        res = _http_json(spec["url"], spec["headers"], spec["payload"], timeout=300)
        b64s = [d["b64_json"] for d in res.get("data", []) if d.get("b64_json")]
        urls = [d["url"] for d in res.get("data", []) if d.get("url")]
        files = (self._save_b64(b64s, IMG_DIR) if b64s else []) + \
                (self._download(urls, IMG_DIR) if urls else [])
        if not files:
            raise RuntimeError("no images in OpenAI response")
        return {"files": files, "model": model}

    # ----- Replicate (legacy path, ported from generate_image.py minus the NSFW trigger hack) -----
    SDXL_VERSION = "stability-ai/sdxl:c221b2b8ef527988fb59bf24a8b97c4561f1c671f73bd389f866bfb27c061316"

    def _gen_replicate(self, prompt, model, seed, dims, guidance, dry_run):
        if dry_run:
            return {"url": "replicate.run", "headers": {"Authorization": "Token ***"},
                    "payload": {"model": model, "prompt": prompt}}
        if not os.environ.get("REPLICATE_API_TOKEN"):
            return {"error": "REPLICATE_API_TOKEN not set"}
        import replicate
        w, h = DIMS_TO_WH.get(dims, (1024, 1024))
        inp = {"prompt": prompt, "width": w, "height": h, "guidance_scale": float(guidance or 7.5)}
        if seed is not None:
            inp["seed"] = int(seed)
        ref = self.SDXL_VERSION if model == "stability-ai/sdxl" else model
        out = replicate.run(ref, input=inp)
        urls = [str(u) for u in (out if isinstance(out, list) else [out])]
        return {"files": self._download(urls, IMG_DIR), "model": model}

    # ----- Gemini (ported from app.py _call_gemini_api: generateContent + inlineData) -----
    def _gen_gemini(self, prompt, model, dims, dry_run):
        key = os.environ.get("GEMINI_API_KEY", "")
        w, h = DIMS_TO_WH.get(dims, (1024, 1024))
        full = f"Generate an image: {prompt}"
        if w != h:
            full += f". {'Landscape' if w > h else 'Portrait'} aspect ratio approximately {w}:{h}."
        spec = {"url": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                "headers": {"Content-Type": "application/json"},
                "payload": {"contents": [{"parts": [{"text": full}]}],
                            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}}
        if dry_run:
            return spec
        if not key:
            return {"error": "GEMINI_API_KEY not set"}
        res = _http_json(spec["url"], spec["headers"], spec["payload"], timeout=180)
        b64s = []
        for cand in res.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if inline.get("data"):
                    b64s.append(inline["data"])
        if not b64s:
            raise RuntimeError("no image parts in Gemini response")
        return {"files": self._save_b64(b64s, IMG_DIR), "model": model}

    # ----- HF (requires token; chip greyed until then) -----
    def _gen_hf(self, prompt, model, seed):
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=os.environ["HUGGINGFACE_TOKEN"])
        img = client.text_to_image(prompt, model=model)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = IMG_DIR / f"{stamp}_image.png"
        img.save(out)
        return {"files": [str(out)], "model": model}


if __name__ == "__main__":
    a = Api(start_server=True)
    print("bridge v2 OK, port", a._port)
    print("providers:", [(p["name"], p["ready"]) for p in a.providers()])
    print("models:", len(a.models()["models"]))
    a.shutdown()
