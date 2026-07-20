"""Regenerate engine/fal_models.json from fal's LIVE explore catalog.

Pulls the FULL catalog per category from fal.ai's explore JSON API (the same data behind
fal.ai/explore), then fetches each model's OpenAPI input schema so the UI param forms scale
with zero hand-authoring. Each model carries {id,label,category,output,description,params[]
(name/type/enum/default/min/max/required/description),thumb,price,supports_relaxed_safety}.

Usage:
  python scripts/build_fal_catalog.py                    # full pull, all media categories
  python scripts/build_fal_catalog.py --categories text-to-image,text-to-video
  python scripts/build_fal_catalog.py --max-per-category 20   # quick test run
  python scripts/build_fal_catalog.py --no-cache              # ignore the schema cache

Needs FAL_KEY only for the openapi fetch fallback (the explore list is keyless).
Schema fetches are cached under scripts/.fal_schema_cache/ so re-runs resume instantly.
Cloudflare 403s bare curl/urllib -> every request sends a browser User-Agent.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXPLORE_API = "https://fal.ai/api/models"      # keyless explore JSON (browser UA required)
SCHEMA_API = "https://fal.ai/api/openapi/queue/openapi.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CACHE_DIR = Path(__file__).resolve().parent / ".fal_schema_cache"

# The app's media categories (site list minus Training / LLM / JSON / Workflow — not media gen).
CATEGORIES = [
    "text-to-image", "image-to-image",
    "text-to-video", "image-to-video", "video-to-video", "audio-to-video",
    "text-to-audio", "audio-to-audio", "video-to-audio",
    "text-to-speech", "speech-to-speech",
    "speech-to-text", "audio-to-text", "video-to-text", "image-to-text",
    "vision",
    "text-to-3d", "image-to-3d", "3d-to-3d",
]
OUTPUT_BY_CAT = {"image": "image", "video": "video", "audio": "audio", "speech": "audio",
                 "text": "text", "3d": "3d", "vision": "text", "json": "text"}
INPUT_MEDIA_KEYS = {
    "image_url": "needs_input_image", "video_url": "needs_input_video",
    "audio_url": "needs_input_audio", "model_mesh_url": "needs_input_mesh",
    "input_image_url": "needs_input_image", "reference_image_url": "needs_input_image",
}
# params whose PRESENCE means the model can be relaxed for editorial/NSFW work (plan doc section 3)
SAFETY_PARAM_NAMES = {"enable_safety_checker", "safety_tolerance", "enable_output_safety_checker"}

# --- content-capability grading: does the model actually ALLOW NSFW (not just expose a toggle)? ---
# Providers that hard-moderate UPSTREAM regardless of fal's enable_safety_checker — verified: nano-banana
# has aggressive IMAGE_SAFETY that blocks nudity even with the checker off; Google/OpenAI policy bans
# erotic content. These REFUSE NSFW, so they're excluded from the permissive modes.
UPSTREAM_MODERATED = ("nano-banana", "gemini", "imagen", "gpt-image", "dall-e", "dalle",
                      "nucleus", "google/", "openai/")
# Open-weights families known to comply with a disabled checker (community-known permissive bases).
OPEN_FAMILIES = ("flux", "stable-diffusion", "sdxl", "sd-", "sd3", "sd35", "hidream", "sana",
                 "seedream", "seedance", "qwen", "wan", "chroma", "pony", "lustify", "juggernaut",
                 "dreamshaper", "realvis", "realistic-vision", "nsfw", "uncensored", "lumina",
                 "kolors", "playground", "auraflow", "cogview", "hunyuan")
# Curated known-uncensored seed — graded `verified` before any empirical run; the harness expands this.
CURATED_VERIFIED = {
    "fal-ai/flux/dev", "fal-ai/flux/schnell", "fal-ai/flux-lora", "fal-ai/flux-general",
    "fal-ai/flux-general/image-to-image", "fal-ai/lora", "fal-ai/stable-diffusion-v35-large",
    "fal-ai/hidream-i1-full", "fal-ai/sana",
}
EMPIRICAL = {}  # id -> {grade, score, ...} loaded from engine/nsfw_capability.json in main() (ground truth)


def content_capability(endpoint_id: str, label: str, supports_relaxed: bool) -> str:
    """upstream_moderated | permissive | verified | filtered.
    `verified` comes ONLY from an empirical NSFW-classifier pass (the honest bar). A single
    benchmark `refused` does NOT demote — a tasteful benchmark under-triggers, so it isn't proof
    of incapability; the model stays `permissive` if it exposes a toggle on an open-weights family
    (or is curated-known). `unknown` (gen/classify error) likewise falls through to the heuristic."""
    ev = EMPIRICAL.get(endpoint_id)
    if ev and ev.get("grade") == "verified":
        return "verified"
    text = ((endpoint_id or "") + " " + (label or "")).lower()
    if any(p in text for p in UPSTREAM_MODERATED):
        return "upstream_moderated"
    if supports_relaxed and (endpoint_id in CURATED_VERIFIED or any(f in text for f in OPEN_FAMILIES)):
        return "permissive"
    return "filtered"


def _get(url: str, auth: bool = False, timeout: int = 45) -> dict:
    headers = {"User-Agent": UA}
    if auth and os.environ.get("FAL_KEY"):
        headers["Authorization"] = f"Key {os.environ['FAL_KEY']}"
    req = urllib.request.Request(url, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def list_category_full(cat: str, cap: int) -> list:
    """Page the explore API for every non-deprecated/removed model in a category."""
    items, page = [], 1
    while True:
        try:
            d = _get(f"{EXPLORE_API}?categories={urllib.parse.quote(cat)}&page={page}")
        except Exception as e:
            print(f"  {cat} page {page}: LIST FAILED {e}")
            break
        for it in d.get("items", []):
            if it.get("deprecated") or it.get("removed"):
                continue
            items.append(it)
            if cap and len(items) >= cap:
                return items
        pages = d.get("pages", 1)
        if page >= pages:
            break
        page += 1
    return items


def output_kind(cat: str) -> str:
    return OUTPUT_BY_CAT.get(cat.split("-")[-1], OUTPUT_BY_CAT.get(cat, "image"))


def _fetch_schema(endpoint_id: str, use_cache: bool) -> dict:
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / (endpoint_id.replace("/", "__") + ".json")
    if use_cache and cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    d = _get(f"{SCHEMA_API}?endpoint_id={urllib.parse.quote(endpoint_id, safe='')}", auth=True)
    try:
        cache.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass
    return d


def _resolve(p: dict, schemas: dict, depth: int = 0) -> dict:
    """Follow $ref / anyOf / allOf to the concrete {type,enum,minimum,maximum} the UI needs.
    Keeps the outer property's default/description/title (fal puts those on the wrapper)."""
    if depth > 4 or not isinstance(p, dict):
        return p if isinstance(p, dict) else {}
    if "$ref" in p:
        target = schemas.get(p["$ref"].split("/")[-1], {})
        return _resolve(target, schemas, depth + 1)
    for key in ("anyOf", "allOf", "oneOf"):
        if key in p:
            merged = {k: v for k, v in p.items() if k not in ("anyOf", "allOf", "oneOf")}
            for sub in p[key]:
                r = _resolve(sub, schemas, depth + 1)
                if r.get("type") == "null":
                    continue
                for k, v in r.items():
                    merged.setdefault(k, v)  # first concrete member wins; outer keys already set
            return merged
    return p


def _input_kind(name: str) -> str:
    """Map an input-media property name to a needs_input_* flag by keyword (broader than the exact map)."""
    if name in INPUT_MEDIA_KEYS:
        return INPUT_MEDIA_KEYS[name]
    if not (name.endswith("_url") or name.endswith("_urls")):
        return ""
    for kw, flag in (("image", "needs_input_image"), ("video", "needs_input_video"),
                     ("audio", "needs_input_audio"), ("mesh", "needs_input_mesh")):
        if kw in name:
            return flag
    return "needs_input_image"  # a bare *_url on an image/vision model → treat as an image input


def extract_params(endpoint_id: str, use_cache: bool) -> tuple:
    """OpenAPI input schema -> (params[], media-input flags, supports_relaxed_safety)."""
    try:
        d = _fetch_schema(endpoint_id, use_cache)
    except Exception:
        return [], {}, False
    schemas = d.get("components", {}).get("schemas", {})
    input_schema = next((s for n, s in schemas.items()
                         if n.lower().endswith("input") and isinstance(s, dict) and s.get("properties")), None)
    if not input_schema:
        return [], {}, False
    props = input_schema["properties"]
    supports_relaxed = any(k in props for k in SAFETY_PARAM_NAMES)  # from the FULL schema, pre-cap
    params, flags = [], {}
    required = set(input_schema.get("required", []))
    for pname, raw in props.items():
        if pname == "prompt":
            continue
        kind = _input_kind(pname)
        if kind:
            flags[kind] = True
            continue
        if pname == "loras":
            continue
        p = _resolve(raw, schemas)                       # follow $ref/anyOf to the concrete type
        desc = (raw.get("description") or p.get("description") or "")[:220]
        if pname == "image_size":  # $ref preset OR custom {w,h} — emit as picker + optional w/h
            params.append({"name": "image_size", "type": "enum",
                           "values": ["square_hd", "square", "portrait_4_3", "portrait_16_9",
                                      "landscape_4_3", "landscape_16_9"],
                           "default": p.get("default", "landscape_4_3"), "description": desc})
            params.append({"name": "width", "type": "int", "min": 256, "max": 2048, "optional": True})
            params.append({"name": "height", "type": "int", "min": 256, "max": 2048, "optional": True})
            continue
        # effective view: resolved type/enum from p, authoritative default/bounds from the outer wrapper
        eff = dict(p)
        for k in ("default", "minimum", "maximum", "title"):
            if k in raw:
                eff[k] = raw[k]
        entry = {"name": pname}
        ptype = eff.get("type")
        if "enum" in eff:
            entry.update(type="enum", values=eff["enum"])
        elif ptype == "boolean":
            entry["type"] = "bool"
        elif ptype == "integer":
            entry["type"] = "int"
        elif ptype == "number":
            entry["type"] = "float"
        elif ptype == "string":
            entry["type"] = "string"
        else:
            continue
        if "default" in eff:
            entry["default"] = eff["default"]
        if "minimum" in eff:
            entry["min"] = eff["minimum"]
        if "maximum" in eff:
            entry["max"] = eff["maximum"]
        if pname not in required and "default" not in eff:
            entry["optional"] = True
        if desc:
            entry["description"] = desc
        params.append(entry)
    # safety params always kept; then defaults-first, cap at 18 so forms stay usable
    params.sort(key=lambda e: (0 if e["name"] in SAFETY_PARAM_NAMES else 1,
                               0 if "default" in e else 1, e["name"]))
    return params[:18], flags, supports_relaxed


def build_entry(item: dict, use_cache: bool) -> dict:
    endpoint_id = item.get("id") or item.get("modelId")
    cat = item.get("category", "")
    params, flags, safe = extract_params(endpoint_id, use_cache)
    entry = {
        "id": endpoint_id,
        "label": item.get("title") or endpoint_id,
        "category": cat,
        "output": output_kind(cat),
        "description": (item.get("shortDescription") or "")[:220],
        "params": params,
        "thumb": item.get("thumbnailUrl") or "",
        "price": item.get("pricingInfoOverride") or item.get("billingMessage") or "",
        "supports_relaxed_safety": safe,
        "content_capability": content_capability(endpoint_id, item.get("title") or endpoint_id, safe),
    }
    entry.update(flags)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--categories", default="", help="comma-list; default = all media categories")
    ap.add_argument("--max-per-category", type=int, default=0, help="0 = all (full pull)")
    ap.add_argument("--no-cache", action="store_true", help="ignore the on-disk schema cache")
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()
    use_cache = not args.no_cache

    global EMPIRICAL
    emp = Path(__file__).resolve().parent.parent / "engine" / "nsfw_capability.json"
    if emp.exists():
        try:
            EMPIRICAL = json.loads(emp.read_text(encoding="utf-8")).get("models", {})
            print(f"loaded {len(EMPIRICAL)} empirical NSFW grades (override the heuristic)")
        except Exception:
            EMPIRICAL = {}

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] or CATEGORIES
    items = []
    for cat in cats:
        got = list_category_full(cat, args.max_per_category)
        print(f"{cat}: {len(got)} models")
        items.extend(got)
    # de-dup by endpoint id (a model can appear under multiple categories)
    seen, uniq = set(), []
    for it in items:
        eid = it.get("id") or it.get("modelId")
        if eid and eid not in seen:
            seen.add(eid)
            uniq.append(it)
    print(f"fetching {len(uniq)} schemas ({args.threads} threads, cache={'on' if use_cache else 'off'})...")
    t0 = time.time()
    with ThreadPoolExecutor(args.threads) as pool:
        entries = list(pool.map(lambda it: build_entry(it, use_cache), uniq))
    print(f"schemas done in {time.time()-t0:.0f}s; "
          f"{sum(1 for e in entries if e['params'])} with params; "
          f"{sum(1 for e in entries if e['supports_relaxed_safety'])} relaxable")

    dest = Path(__file__).resolve().parent.parent / "engine" / "fal_models.json"
    if dest.exists():  # back up before overwrite (Job 1 global rule)
        bak = dest.with_suffix(f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        bak.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"backed up old catalog -> {bak.name}")
    out = {
        "version": 3,
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "generator": "scripts/build_fal_catalog.py (full explore-API pull + openapi schemas)",
        "note": "params are FORM HINTS with descriptions; engine passes dicts through verbatim. "
                "supports_relaxed_safety = model exposes enable_safety_checker/safety_tolerance. Regenerate via the script.",
        "models": entries,
    }
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    bycat = {}
    for e in entries:
        bycat[e["category"]] = bycat.get(e["category"], 0) + 1
    print(f"wrote {dest} — {len(entries)} models across {len(bycat)} categories")
    for c, n in sorted(bycat.items()):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
