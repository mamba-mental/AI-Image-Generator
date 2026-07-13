"""
fal.ai adapter — live catalog + live per-model schema + queue submit.

Catalog:  https://fal.ai/api/models?page=N&categories=<cat>   (1-indexed, 40/page)
Schema:   https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>  (per-model Input)
Submit:   https://queue.fal.run/<id>  (submit -> poll status_url -> fetch response_url)

Catalog + schemas are cached to disk (fast UI, refreshable); generation is always live.
"""
import json, os, time, urllib.request
from pathlib import Path

import schema as schema_mod
from .base import Provider

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
CACHE.mkdir(exist_ok=True)
IMG_DIR = ROOT / "generated_images"
MEDIA_DIR = ROOT / "generated_media"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
# fal category -> our kind. text/image-to-image = image; *-to-video = video.
CAT_KIND = {
    "text-to-image": "image", "image-to-image": "image",
    "text-to-video": "video", "image-to-video": "video",
}
CATALOG_TTL = 24 * 3600


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _post(url, headers, body, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"User-Agent": _UA, **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class FalProvider(Provider):
    name = "fal"
    label = "fal.ai"
    key_env = "FAL_KEY"

    # ---------- catalog ----------
    def list_models(self, kind=None, refresh=False):
        cat = self._catalog(refresh=refresh)
        if kind:
            cat = [m for m in cat if m["kind"] == kind]
        return cat

    def _catalog(self, refresh=False):
        cf = CACHE / "fal_catalog.json"
        if not refresh and cf.exists() and (time.time() - cf.stat().st_mtime) < CATALOG_TTL:
            try:
                return json.loads(cf.read_text(encoding="utf-8"))
            except Exception:
                pass
        models = self._fetch_catalog()
        if models:
            cf.write_text(json.dumps(models), encoding="utf-8")
            return models
        # network failed — serve stale cache if we have it, else empty
        if cf.exists():
            return json.loads(cf.read_text(encoding="utf-8"))
        return []

    def _fetch_catalog(self):
        out, seen = [], set()
        for cat, knd in CAT_KIND.items():
            page = 1
            while True:
                try:
                    d = _get(f"https://fal.ai/api/models?page={page}&categories={cat}")
                except Exception:
                    break
                items = d.get("items", [])
                if not items:
                    break
                for it in items:
                    mid = it.get("id")
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    out.append({"id": mid, "label": it.get("title") or mid, "kind": knd,
                                "desc": it.get("shortDescription", "")})
                if page >= d.get("pages", page):
                    break
                page += 1
        return out

    # ---------- schema ----------
    def form_spec(self, model_id, refresh=False):
        sc = self._schema(model_id, refresh=refresh)
        input_props, required = self._input_props(sc)
        return schema_mod.props_to_formspec(input_props, required)

    def _schema(self, model_id, refresh=False):
        safe = model_id.replace("/", "__")
        sf = CACHE / f"fal_schema_{safe}.json"
        if not refresh and sf.exists():
            try:
                return json.loads(sf.read_text(encoding="utf-8"))
            except Exception:
                pass
        sc = _get(f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={model_id}")
        sf.write_text(json.dumps(sc), encoding="utf-8")
        return sc

    def _input_props(self, openapi):
        """Pull the <Model>Input schema's properties + required from a fal openapi doc."""
        schemas = openapi.get("components", {}).get("schemas", {})
        inp = next((k for k in schemas if k.endswith("Input")), None)
        if not inp:
            return {}, []
        node = schemas[inp]
        return node.get("properties", {}), node.get("required", [])

    # ---------- submit ----------
    def submit(self, model_id, params: dict, kind=None):
        key = os.environ.get(self.key_env, "")
        if not key:
            return {"error": "FAL_KEY not set"}
        kind = kind or self._kind_of(model_id)
        headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
        payload = {k: v for k, v in params.items() if v not in (None, "")}
        try:
            files = self._submit_and_wait(model_id, headers, payload,
                                          timeout=600 if kind == "video" else 240, kind=kind)
            return {"files": files, "model": model_id}
        except Exception as e:
            return {"error": f"fal submit failed: {type(e).__name__}: {e}"}

    def _kind_of(self, model_id):
        for m in self._catalog():
            if m["id"] == model_id:
                return m["kind"]
        return "video" if "video" in model_id or "veo" in model_id or "kling" in model_id else "image"

    def _submit_and_wait(self, model_id, headers, payload, timeout, kind):
        submit = _post(f"https://queue.fal.run/{model_id}", headers, payload)
        status_url, resp_url = submit.get("status_url"), submit.get("response_url")
        if not status_url:
            return self._save(submit, kind)
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = _get_auth(status_url, headers)
            s = st.get("status")
            if s == "COMPLETED":
                return self._save(_get_auth(resp_url, headers), kind)
            if s in ("FAILED", "ERROR"):
                raise RuntimeError(st)
            time.sleep(2.5 if kind == "video" else 1.5)
        raise TimeoutError(f"fal queue timed out after {timeout}s")

    def _save(self, result, kind):
        urls = []
        if kind == "video":
            v = result.get("video") or {}
            if v.get("url"):
                urls = [v["url"]]
        if not urls:
            urls = [im["url"] for im in result.get("images", []) if im.get("url")]
        if not urls:
            raise RuntimeError(f"no media in result: {list(result.keys())}")
        dest = MEDIA_DIR if kind == "video" else IMG_DIR
        dest.mkdir(exist_ok=True)
        saved, stamp = [], time.strftime("%Y%m%d-%H%M%S")
        for i, u in enumerate(urls):
            ext = os.path.splitext(u.split("?")[0])[1] or (".mp4" if kind == "video" else ".png")
            suffix = "_image" if len(urls) == 1 else f"_batch{i+1}of{len(urls)}"
            out = dest / f"{stamp}{suffix}{ext}"
            req = urllib.request.Request(u, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                out.write_bytes(r.read())
            saved.append(str(out))
        return saved


def _get_auth(url, headers, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())
