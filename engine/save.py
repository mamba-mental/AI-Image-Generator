"""Result persistence — port of app.py result handling (:1801-1838), extended for
video/audio outputs from fal. A result is one of:
  - URL string (downloaded; extension from content-type)
  - PIL.Image (saved as PNG)
  - "…Error…" string (collected, not saved)
Returns (saved_paths, error_messages).
"""
import mimetypes
import os
import time
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


def make_output_paths(output_dir: str, count: int, ext: str = ".png") -> list:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    if count == 1:
        return [os.path.join(output_dir, f"generated_{stamp}{ext}")]
    return [os.path.join(output_dir, f"generated_{stamp}_{i + 1}{ext}") for i in range(count)]


def _download(url: str, dest: str) -> str:
    """Download url; fix the extension from the response content-type. Returns final path."""
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    ct = (response.headers.get("content-type") or "").split(";")[0].strip()
    ext = _CT_EXT.get(ct) or mimetypes.guess_extension(ct) or Path(dest).suffix or ".bin"
    final = str(Path(dest).with_suffix(ext))
    with open(final, "wb") as f:
        f.write(response.content)
    return final


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
