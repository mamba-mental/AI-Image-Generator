"""Ingest external image sets (NSFW sweeps + recovered Replicate history) INTO the omni-image
library so they're searchable by prompt/model/params like native gens.

The library reads per-image metadata from a `<image>.<ext>.json` sidecar (engine/library_index.py
_read_sidecar) with top-level keys service/model/prompt/seed/category (+ nested params). This tool
writes exactly that sidecar next to each source image, then (with --register) adds the folder to
config.json `library_directories` and indexes it into `.cache/library.db`.

SOURCES (pick one):
  --sweep    <json>   NSFW sweep dataset (data/nsfw-verified-test1*.json or nsfw-verified*.json)
  --manifest <json>   Replicate recovery manifest (scripts/.replicate_recover/manifest.json)

  --images-root <dir> base dir the record image paths are relative to. Defaults:
                        sweep    -> C:/AI CoWork/dashboards
                        manifest -> <this repo>/scripts/.replicate_recover
  --category <str>    override the sidecar category
  --register          also add the touched folders to config.json library_directories AND index
                      them into .cache/library.db (idempotent)

  python scripts/ingest_to_library.py --sweep "C:/AI CoWork/dashboards/data/nsfw-verified-test1-<tag>.json" --register
  python scripts/ingest_to_library.py --manifest scripts/.replicate_recover/manifest.json --register
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
DASH = Path(r"C:/AI CoWork/dashboards")
RECOVER = REPO / "scripts" / ".replicate_recover"
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def write_sidecar(img: Path, meta: dict) -> None:
    """Write `<image>.<ext>.json` — the exact filename engine/library_index._read_sidecar reads."""
    side = Path(str(img) + ".json")
    side.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def ingest_sweep(sweep_path: Path, images_root: Path, category: str | None) -> tuple[int, set]:
    data = json.loads(sweep_path.read_text(encoding="utf-8"))
    test = data.get("test")
    prompt = data.get("prompt", "")            # Test 1 has full text; Test 2 has only prompt_sha256
    cat = category or (f"nsfw-test-{test}" if test else "nsfw-test")
    written, folders = 0, set()
    for m in data.get("models", []):
        sample = m.get("sample")
        if not sample:
            continue
        img = (images_root / sample).resolve()
        if not img.exists():
            continue
        meta = _clean({
            "service": m.get("provider", ""),
            "model": m.get("model", ""),
            "prompt": prompt,                  # shared across the sweep's models
            "seed": "",
            "category": cat,
            "params": _clean({"grade": m.get("grade"), "votes": m.get("votes"),
                              "mean": m.get("mean"), "label": m.get("label"), "test": test}),
        })
        write_sidecar(img, meta)
        written += 1
        folders.add(str(img.parent))
    return written, folders


def ingest_manifest(manifest_path: Path, images_root: Path, category: str | None) -> tuple[int, set]:
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    cat = category or "replicate-legacy"
    written, folders = 0, set()
    for r in records:
        inp = r.get("input") or {}
        prompt = r.get("prompt") or (inp.get("prompt", "") if isinstance(inp, dict) else "")
        seed = str(inp.get("seed", "")) if isinstance(inp, dict) else ""
        params = {k: v for k, v in inp.items() if k != "prompt"} if isinstance(inp, dict) else {}
        if r.get("version"):
            params["version"] = r["version"]
        for rel in (r.get("images") or []):
            img = (images_root / rel).resolve()
            if not img.exists():
                continue
            meta = _clean({
                "service": "replicate",
                "model": r.get("model", ""),
                "prompt": prompt,
                "seed": seed,
                "category": cat,
                "params": _clean(params),
            })
            write_sidecar(img, meta)
            written += 1
            folders.add(str(img.parent))
    return written, folders


def register_and_index(folders: set) -> None:
    """Add the top-level source dirs to config.json library_directories + index into .cache/library.db.
    Idempotent. Registers the SHALLOWEST touched dir per source so rglob picks up subfolders."""
    sys.path.insert(0, str(REPO))
    from engine import config as _config

    # collapse folders to their shallowest common roots we care about
    roots = set()
    for f in folders:
        p = Path(f)
        parts = [x.lower() for x in p.parts]
        # register the meaningful scope dir (covers all tag subfolders via rglob), never the
        # whole dashboards dir: nsfw-img / assets/nsfw-verified / .replicate_recover/images.
        root = f
        for marker in ("nsfw-img", "nsfw-verified", "images"):
            if marker in parts:
                root = str(Path(*p.parts[: parts.index(marker) + 1]))
                break
        roots.add(root)

    cfg = _config.load()
    dirs = list(cfg.get("library_directories") or [])
    have = {str(Path(d)).lower() for d in dirs}
    added = []
    for r in sorted(roots):
        if str(Path(r)).lower() not in have:
            dirs.append(r)
            added.append(r)
    if added:
        cfg["library_directories"] = dirs
        _config.save(cfg)
        print("registered library_directories:")
        for a in added:
            print("  +", a)
    else:
        print("library_directories already registered (no change)")

    # index into the same DB the app uses (WAL — safe alongside a running app)
    try:
        from engine.library_index import LibraryIndex
        db = REPO / ".cache" / "library.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        idx = LibraryIndex(str(db))
        total = 0
        for r in sorted(roots):
            n = idx.index_folder(r)
            total += (n or 0)
            print(f"  indexed {r} ({n} images)")
        print(f"indexed {total} images into {db}")
    except Exception as e:  # noqa: BLE001
        print(f"NOTE: sidecars written, but auto-index failed ({type(e).__name__}: {str(e)[:80]}).")
        print("      Register is done; the app will index on its next refresh_library().")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest sweep/Replicate images into the omni-image library.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sweep", help="NSFW sweep dataset JSON")
    src.add_argument("--manifest", help="Replicate recovery manifest JSON")
    ap.add_argument("--images-root", default=None, help="base dir the image paths are relative to")
    ap.add_argument("--category", default=None, help="override sidecar category")
    ap.add_argument("--register", action="store_true", help="add folders to config + index into library.db")
    args = ap.parse_args()

    if args.sweep:
        root = Path(args.images_root) if args.images_root else DASH
        written, folders = ingest_sweep(Path(args.sweep), root, args.category)
    else:
        root = Path(args.images_root) if args.images_root else RECOVER
        written, folders = ingest_manifest(Path(args.manifest), root, args.category)

    print(f"wrote {written} sidecars across {len(folders)} folder(s)")
    if args.register and folders:
        register_and_index(folders)
    elif args.register:
        print("nothing to register (0 sidecars written — check --images-root / that images exist)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
