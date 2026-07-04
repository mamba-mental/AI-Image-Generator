"""Regenerate engine/fal_models.json from fal's live platform API.

Top N models per media category (PRIME's directive 2026-07-03: top ~13 per category),
param hints auto-extracted from each model's OpenAPI schema so the UI forms scale
with zero hand-authoring.

Usage:  python scripts/build_fal_catalog.py [--per-category 13]
Needs:  FAL_KEY in env. ~5 min for ~300 schema fetches (8 threads).
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

MODELS_API = "https://api.fal.ai/v1/models"
SCHEMA_API = "https://fal.ai/api/openapi/queue/openapi.json"

# Media categories only (PRIME's site list minus Training / LLMs / JSON / Workflow / Unknown —
# those aren't media generation and need a different UI).
CATEGORIES = [
    "text-to-image", "image-to-image",
    "text-to-video", "image-to-video", "video-to-video", "audio-to-video",
    "text-to-audio", "audio-to-audio", "video-to-audio",
    "text-to-speech", "speech-to-speech",
    "speech-to-text", "audio-to-text", "video-to-text", "image-to-text",
    "vision",
    "text-to-3d", "image-to-3d", "3d-to-3d",
]

# outputs by category family (drives save-path handling + gallery tile type)
OUTPUT_BY_CAT = {
    "image": "image", "video": "video", "audio": "audio", "speech": "audio",
    "text": "text", "3d": "3d", "vision": "text", "json": "text",
}

INPUT_MEDIA_KEYS = {
    "image_url": "needs_input_image", "video_url": "needs_input_video",
    "audio_url": "needs_input_audio", "model_mesh_url": "needs_input_mesh",
    "input_image_url": "needs_input_image", "reference_image_url": "needs_input_image",
}


def _get(url: str, auth: bool = True) -> dict:
    headers = {"Authorization": f"Key {os.environ['FAL_KEY']}"} if auth else {}
    req = urllib.request.Request(url, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=45).read())


def list_category(cat: str, limit: int) -> list:
    try:
        d = _get(f"{MODELS_API}?category={urllib.parse.quote(cat)}&limit={limit}")
        return [m for m in d.get("models", [])
                if m.get("metadata", {}).get("status") == "active"
                and m.get("metadata", {}).get("kind") == "inference"]
    except Exception as e:
        print(f"  category {cat}: LIST FAILED {e}")
        return []


def output_kind(cat: str) -> str:
    tail = cat.split("-")[-1]
    return OUTPUT_BY_CAT.get(tail, OUTPUT_BY_CAT.get(cat, "image"))


def extract_params(endpoint_id: str) -> tuple:
    """OpenAPI input schema -> (param hints, media-input flags). Empty on failure."""
    try:
        d = _get(f"{SCHEMA_API}?endpoint_id={urllib.parse.quote(endpoint_id, safe='')}", auth=False)
        schemas = d.get("components", {}).get("schemas", {})
        input_schema = None
        for name, s in schemas.items():
            if name.lower().endswith("input") and isinstance(s, dict) and s.get("properties"):
                input_schema = s
                break
        if not input_schema:
            return [], {}
        params, flags = [], {}
        required = set(input_schema.get("required", []))
        for pname, p in input_schema["properties"].items():
            if pname == "prompt":
                continue
            if pname in INPUT_MEDIA_KEYS:
                flags[INPUT_MEDIA_KEYS[pname]] = True
                continue
            if pname.endswith("_url") or pname == "loras":
                continue  # secondary media/complex inputs — not form-rendered v1
            # fal's `image_size` is a $ref (preset enum OR custom {width,height}) so it
            # has no plain `type` and was being dropped — the reason dimensions vanished.
            # Emit it as a preset picker + optional custom width/height.
            if pname == "image_size":
                params.append({"name": "image_size", "type": "enum",
                               "values": ["square_hd", "square", "portrait_4_3",
                                          "portrait_16_9", "landscape_4_3", "landscape_16_9"],
                               "default": p.get("default", "landscape_4_3")})
                params.append({"name": "width", "type": "int", "min": 256, "max": 2048, "optional": True})
                params.append({"name": "height", "type": "int", "min": 256, "max": 2048, "optional": True})
                continue
            entry = {"name": pname}
            ptype = p.get("type")
            if "enum" in p:
                entry.update(type="enum", values=p["enum"])
            elif ptype == "boolean":
                entry["type"] = "bool"
            elif ptype == "integer":
                entry["type"] = "int"
            elif ptype == "number":
                entry["type"] = "float"
            elif ptype == "string":
                entry["type"] = "string"
            else:
                continue  # objects/arrays — pass-through only
            if "default" in p:
                entry["default"] = p["default"]
            if "minimum" in p:
                entry["min"] = p["minimum"]
            if "maximum" in p:
                entry["max"] = p["maximum"]
            if pname not in required and "default" not in p:
                entry["optional"] = True
            params.append(entry)
        # keep forms usable but don't hide real knobs: defaults first, cap at 14
        params.sort(key=lambda e: (0 if "default" in e else 1, e["name"]))
        return params[:14], flags
    except Exception:
        return [], {}


def build_entry(row: dict) -> dict:
    meta = row["metadata"]
    endpoint_id = row["endpoint_id"]
    cat = meta.get("category", "")
    params, flags = extract_params(endpoint_id)
    entry = {
        "id": endpoint_id,
        "label": meta.get("display_name") or endpoint_id,
        "category": cat,
        "output": output_kind(cat),
        "description": (meta.get("description") or "")[:180],
        "params": params,
    }
    entry.update(flags)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=13)
    args = ap.parse_args()
    if not os.environ.get("FAL_KEY"):
        sys.exit("FAL_KEY not in environment")

    rows = []
    for cat in CATEGORIES:
        got = list_category(cat, args.per_category)
        print(f"{cat}: {len(got)} models")
        rows.extend(got)

    print(f"fetching {len(rows)} schemas (8 threads)...")
    t0 = time.time()
    with ThreadPoolExecutor(8) as pool:
        entries = list(pool.map(build_entry, rows))
    print(f"schemas done in {time.time() - t0:.0f}s; "
          f"{sum(1 for e in entries if e['params'])} with param hints")

    out = {
        "version": 2,
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "generator": "scripts/build_fal_catalog.py (top-N per category via api.fal.ai/v1/models)",
        "note": "params are FORM HINTS; engine passes dicts through verbatim. Regenerate with the script.",
        "models": entries,
    }
    dest = Path(__file__).resolve().parent.parent / "engine" / "fal_models.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    cats = {}
    for e in entries:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    print(f"wrote {dest} — {len(entries)} models across {len(cats)} categories")
    for c, n in sorted(cats.items()):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
