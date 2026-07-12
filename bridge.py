#!/usr/bin/env python3
"""
Python<->JS bridge for AI Studio Void web UI (pywebview).
Exposes a truthful Api surface consumed by webui/app.js. Every data-api="<name>"
in webui/index.html resolves to a public method here.

Backends wired v1:
  - fal   : primary, fal REST via queue.fal.run (FLUX.2 turbo, or flux-2/lora when a LoRA stack is active)
  - replicate / hf / gemini : legacy, kept behind their API keys
Higgsfield is RETIRED (0 credits) and deliberately absent from this surface.
"""
import json, os, threading, time, functools, urllib.request, urllib.error
import http.server, socketserver
from pathlib import Path

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

# dims label -> fal image_size enum
DIMS_TO_FAL = {
    "1:1": "square", "4:3": "landscape_4_3", "16:9": "landscape_16_9",
    "3:4": "portrait_3_4", "9:16": "portrait_9_16", "2K": "square_hd",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}

# Provider chips shown in the UI == exactly what this bridge can route.
PROVIDERS = ["fal", "replicate", "hf", "gemini"]


class _MediaHandler(http.server.SimpleHTTPRequestHandler):
    """Serves generated_images/ under /gi/ and generated_media/ under /gm/.
    WebView2 will not load file:// media from a file:// page, so a localhost
    origin is load-bearing, not optional."""
    def log_message(self, *a):  # silence
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
        # Reuse the existing LoRA manager unchanged.
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
        return PROVIDERS

    def models(self):
        """Static curated catalog per provider (truthful — only wired paths)."""
        return {
            "fal": ["fal-ai/flux-2/turbo", "fal-ai/flux-2/flash", "fal-ai/flux-2",
                    "fal-ai/flux-2-pro", "fal-ai/flux-2/lora"],
            "replicate": ["stability-ai/sdxl"],
            "hf": ["black-forest-labs/FLUX.1-schnell", "stabilityai/stable-diffusion-3.5-large"],
            "gemini": ["gemini-2.5-flash-image", "gemini-3-pro-image-preview"],
        }

    # ---------- LoRA stack (delegates to LoRAManager) ----------
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
            self._hist_path.write_text(json.dumps(hist[:100], indent=2), encoding="utf-8")
        return hist[:100]

    def history_list(self):
        return self._load_json(self._hist_path, [])

    # ---------- gallery ----------
    def gallery(self, limit=24):
        items = []
        for d, prefix, kind in ((IMG_DIR, "gi", "image"), (MEDIA_DIR, "gm", None)):
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

    # ---------- generate ----------
    def generate(self, prompt, model="fal-ai/flux-2/turbo", provider="fal",
                 batch=1, seed=None, dims="1:1", guidance=3.5,
                 prompt_enhance=False, dry_run=False):
        prompt = (prompt or "").strip()
        if not prompt:
            return {"error": "empty prompt"}
        if provider == "fal":
            return self._gen_fal(prompt, model, batch, seed, dims, guidance, dry_run)
        return {"error": f"provider '{provider}' not wired in v1 (legacy paths pending)"}

    def _gen_fal(self, prompt, model, batch, seed, dims, guidance, dry_run):
        key = os.environ.get("FAL_KEY", "")
        enabled_loras = [l for l in self._lora.get_loras() if l.get("enabled")]
        # Turbo has no LoRA input — auto-route to the LoRA endpoint when a stack is active.
        if enabled_loras and model == "fal-ai/flux-2/turbo":
            model = "fal-ai/flux-2/lora"
        payload = {
            "prompt": prompt,
            "num_images": int(batch),
            "image_size": DIMS_TO_FAL.get(dims, "square"),
        }
        if seed is not None:
            payload["seed"] = int(seed)
        if model.endswith("/lora") and enabled_loras:
            payload["loras"] = [{"path": l["url"], "scale": l["scale"]} for l in enabled_loras]
        spec = {
            "url": f"https://queue.fal.run/{model}",
            "headers": {"Authorization": f"Key {key}", "Content-Type": "application/json"},
            "payload": payload,
        }
        if dry_run:
            return spec
        if not key:
            return {"error": "FAL_KEY not set in environment"}
        try:
            files = self._fal_submit_and_wait(spec)
            return {"files": files, "model": model}
        except Exception as e:
            return {"error": f"fal generation failed: {type(e).__name__}: {e}"}

    def _fal_submit_and_wait(self, spec, timeout=180):
        def _post(url, body):
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers=spec["headers"], method="POST")
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())

        def _get(url):
            req = urllib.request.Request(url, headers=spec["headers"])
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())

        submit = _post(spec["url"], spec["payload"])
        status_url = submit.get("status_url")
        resp_url = submit.get("response_url")
        if not status_url:  # some models return inline
            return self._download_images(submit)
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = _get(status_url)
            if st.get("status") == "COMPLETED":
                return self._download_images(_get(resp_url))
            if st.get("status") in ("FAILED", "ERROR"):
                raise RuntimeError(st)
            time.sleep(1.5)
        raise TimeoutError("fal queue timed out")

    def _download_images(self, result):
        urls = [im["url"] for im in result.get("images", []) if im.get("url")]
        saved = []
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for i, u in enumerate(urls):
            ext = os.path.splitext(u.split("?")[0])[1] or ".png"
            suffix = "_image" if len(urls) == 1 else f"_batch{i+1}of{len(urls)}"
            out = IMG_DIR / f"{stamp}{suffix}{ext}"
            with urllib.request.urlopen(u, timeout=60) as r:
                out.write_bytes(r.read())
            saved.append(str(out))
        return saved


if __name__ == "__main__":
    a = Api(start_server=True)
    print("bridge OK, port", a._port, "providers", a.providers())
    print("gallery sample:", [i["name"] for i in a.gallery(3)])
    a.shutdown()
