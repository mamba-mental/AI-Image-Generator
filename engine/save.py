"""Result persistence — port of app.py result handling (:1801-1838), extended for
video/audio outputs from fal. A result is one of:
  - URL string (downloaded; extension from content-type)
  - PIL.Image (saved as PNG)
  - "…Error…" string (collected, not saved)
Returns (saved_paths, error_messages).
"""
import json
import mimetypes
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

_CT_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "video/mp4": ".mp4", "video/webm": ".webm",
    "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "model/gltf-binary": ".glb", "model/obj": ".obj", "model/stl": ".stl",
    "application/octet-stream": ".bin", "text/plain": ".txt",
}


def generated_root(base: str) -> str:
    """The stable folder generations live under, INSIDE the configured output root:
    `<base>/generated` — always a real, scannable subfolder, never the base/NAS root itself.
    Registering this one folder in the Library scan set makes every dated child findable (#6)."""
    return os.path.join(base, "generated") if base else ""


def month_dir(base: str) -> str:
    """The dated bucket a generation lands in: `<base>/generated/YYYY-MM`."""
    return os.path.join(generated_root(base), time.strftime("%Y-%m"))


def _seed_slug(seed) -> str:
    """Seed → 6-char base36 slug (000000 when absent) — part of the collision-proof filename."""
    try:
        n = abs(int(seed))
    except (TypeError, ValueError):
        return "000000"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = digits[r] + s
    return (s or "0").rjust(6, "0")[-6:]


def make_output_paths(output_dir: str, count: int, ext: str = ".png", seed=None) -> list:
    """Build save paths under `<output_dir>/generated/YYYY-MM/` (#6: no more dumping into the NAS
    root). Filename `YYYYMMDD-HHMMSS-<ms>-<seq4>-<seedslug>.<ext>` is sortable and collision-proof:
    the millisecond stamp + per-call index can't collide within a run, and the seed slug + second
    resolution keep separate runs distinct.
    # ponytail: ms-stamp + call-index is collision-proof without a per-folder DB sequence/lock.
    """
    d = month_dir(output_dir)
    Path(d).mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ms = int((time.time() % 1) * 1000)
    slug = _seed_slug(seed)
    return [os.path.join(d, f"{stamp}-{ms:03d}-{i + 1:04d}-{slug}{ext}") for i in range(count)]


def validate_output_root(path: str) -> tuple:
    """Guard for the output/library folder (#6, AC-6.3). Rejects a drive root (`X:\\`), a filesystem
    root (`/`), a UNC share root (`\\\\host\\share`), and a non-writable/nonexistent dir. Returns
    (ok: bool, message: str). This is what stops `output_directory` ever being `I:\\` again."""
    if not path or not str(path).strip():
        return False, "output folder is empty"
    p = Path(str(path))
    if str(p) in ("/", "\\"):
        return False, "can't use the filesystem root — pick a real subfolder"
    if p.anchor and p == Path(p.anchor):
        # drive root (I:\) or UNC share root (\\host\share) — Path.anchor covers both on Windows
        return False, "can't use a drive/share root — pick a real subfolder inside it"
    if not p.exists():
        return False, "that folder doesn't exist"
    if not os.access(str(p), os.W_OK):
        return False, "that folder isn't writable"
    return True, "ok"


_KNOWN_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov",
              ".mp3", ".wav", ".m4a", ".flac", ".glb", ".obj", ".stl"}


def _pick_ext(url: str, ct: str, dest: str) -> str:
    """Extension from the URL path FIRST (fal output URLs carry the true ext), content-type as
    fallback. Fixes kontext etc. served as application/octet-stream saving as .bin (blank tile)."""
    from urllib.parse import urlparse
    url_ext = Path(urlparse(url).path).suffix.lower()
    if url_ext in _KNOWN_EXT:
        return url_ext
    return _CT_EXT.get(ct) or mimetypes.guess_extension(ct) or Path(dest).suffix or ".bin"


def _download(url: str, dest: str) -> str:
    """Download url; extension from the URL path (content-type fallback). Returns final path."""
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    ct = (response.headers.get("content-type") or "").split(";")[0].strip()
    ext = _pick_ext(url, ct, dest)
    final = str(Path(dest).with_suffix(ext))
    with open(final, "wb") as f:
        f.write(response.content)
    return final


def write_sidecar(media_path: str, meta: dict) -> str:
    """Write <media>.<ext>.json beside a saved file with generation metadata (#9 overlay source).
    Enriches with timestamp, byte size, and image dimensions. Sidecar suffix keeps it out of the
    gallery/library file scans (they filter on media extensions, not .json)."""
    p = Path(media_path)
    enriched = dict(meta)
    enriched.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    try:
        enriched["bytes"] = p.stat().st_size
    except OSError:
        pass
    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            with Image.open(p) as im:
                enriched["width"], enriched["height"] = im.size
        except Exception:
            pass
    side = str(p) + ".json"
    try:
        with open(side, "w", encoding="utf-8") as f:
            json.dump(enriched, f, indent=2, default=str)
    except Exception as e:
        print(f"sidecar write failed: {e}")
    return side


def persist_results(results: list, output_paths: list) -> tuple:
    saved, errors = [], []
    for i, result in enumerate(results):
        if i >= len(output_paths):
            break
        dest = output_paths[i]
        try:
            if isinstance(result, str) and result.startswith("http"):
                final = _download(result, dest)
                saved.append(final)
            elif isinstance(result, dict) and "text" in result:
                # text output (STT / vision / captioning) -> .txt beside media outputs
                final = str(Path(dest).with_suffix(".txt"))
                with open(final, "w", encoding="utf-8") as f:
                    f.write(str(result["text"]))
                saved.append(final)
            elif isinstance(result, Image.Image):
                result.save(dest)
                saved.append(dest)
            elif isinstance(result, str) and "Error" in result:
                errors.append(result)
            elif result is not None:
                errors.append(f"Unknown result type for item {i + 1}: {type(result).__name__}")
        except Exception as e:
            errors.append(f"Error saving item {i + 1}: {e}")
    return saved, errors
