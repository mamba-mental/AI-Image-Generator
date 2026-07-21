"""Durable embedded-metadata format (Spec C AC-8.6) — the portable copy of a generation's
`ai_studio_meta` blob, so tags/prompt/params survive a Library-Index rebuild or the image
leaving the app entirely (the DB is the fast index; this is the durable, self-describing copy —
research/2026-07-21_preset-tagging-output-modeling.md §(b)).

Format (byte-exact per AC-8.6):
  PNG        -> iTXt chunk keyed "ai_studio_meta" (UTF-8, uncompressed).
  JPEG/WEBP  -> EXIF UserComment (tag 0x9286, Exif SubIFD 0x8769) = the 8-byte charset prefix
                b"ASCII\\0\\0\\0" + UTF-8 JSON bytes, PLUS an XMP dc:subject mirror of tags[]
                (XMP is the tolerant fallback — it survives tools that strip EXIF only).

Pillow (already a dependency) covers all three natively — verified live round-trip 2026-07-21,
no new dependency needed (PngInfo.add_itxt / Image.Exif().get_ifd / save(exif=,xmp=)).

Never blocks a save: write_embedded_meta() catches everything and returns False on failure —
the caller logs it and the DB row stays the source of truth either way (AC-8.6).
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

META_KEY = "ai_studio_meta"
_USERCOMMENT_TAG = 0x9286
_EXIF_IFD = 0x8769
_CHARSET_ASCII = b"ASCII\x00\x00\x00"
_META_FIELDS = ("provider", "model", "seed", "prompt", "negative", "params", "tags")


def _blob(meta: dict) -> dict:
    """The exact {provider,model,seed,prompt,negative,params,tags[]} shape (AC-8.6)."""
    m = meta or {}
    return {
        "provider": m.get("provider") or m.get("service"),
        "model": m.get("model"),
        "seed": m.get("seed"),
        "prompt": m.get("prompt"),
        "negative": m.get("negative") if m.get("negative") is not None else m.get("negative_prompt"),
        "params": m.get("params") or {},
        "tags": list(m.get("tags") or []),
    }


def _xml_escape(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xmp_subject(tags: list) -> bytes:
    items = "".join(f"<rdf:li>{_xml_escape(t)}</rdf:li>" for t in tags)
    xml = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:subject><rdf:Bag>{items}</rdf:Bag></dc:subject>"
        "</rdf:Description></rdf:RDF></x:xmpmeta>"
    )
    return xml.encode("utf-8")


def write_embedded_meta(path, meta: dict) -> bool:
    """Write the durable ai_studio_meta copy into the image at `path`. Never raises."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return False
    blob = _blob(meta)
    payload = json.dumps(blob, ensure_ascii=False).encode("utf-8")
    try:
        frame = Image.open(p)
        frame.load()  # fully decode + release the read handle so we can overwrite the same path
        if ext == ".png":
            info = PngInfo()
            info.add_itxt(META_KEY, payload.decode("utf-8"))
            frame.save(p, "PNG", pnginfo=info)
        else:
            exif = Image.Exif()
            ifd = exif.get_ifd(_EXIF_IFD)
            ifd[_USERCOMMENT_TAG] = _CHARSET_ASCII + payload
            kwargs = {"exif": exif.tobytes(), "xmp": _xmp_subject(blob["tags"])}
            if ext in (".jpg", ".jpeg"):
                kwargs["quality"] = "keep"  # reuses the original quantization — no re-compression
                frame.save(p, "JPEG", **kwargs)
            else:
                if frame.info.get("lossless"):
                    kwargs["lossless"] = True
                frame.save(p, "WEBP", **kwargs)
        return True
    except Exception as e:
        print(f"embed_meta write failed for {p.name}: {type(e).__name__}: {e}")
        return False


def read_embedded_meta(path) -> dict | None:
    """Read the ai_studio_meta blob back (round-trip / re-import recovery, AC-8.5). None on any
    failure or absence — never raises."""
    p = Path(path)
    ext = p.suffix.lower()
    try:
        with Image.open(p) as im:
            if ext == ".png":
                raw = im.text.get(META_KEY) if hasattr(im, "text") else im.info.get(META_KEY)
                if raw is None:
                    return None
                return json.loads(str(raw))
            if ext in (".jpg", ".jpeg", ".webp"):
                exif = im.getexif()
                ifd = exif.get_ifd(_EXIF_IFD)
                raw = ifd.get(_USERCOMMENT_TAG)
                if not raw or not bytes(raw).startswith(_CHARSET_ASCII):
                    return None
                return json.loads(bytes(raw)[len(_CHARSET_ASCII):].decode("utf-8"))
    except Exception:
        return None
    return None


if __name__ == "__main__":
    # ponytail: smallest runnable self-check — round-trip each format in a temp dir.
    import sys
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as td:
        for ext in (".png", ".jpg", ".webp"):
            fp = Path(td) / f"t{ext}"
            Image.new("RGB", (8, 8), "red").save(fp)
            meta = {"provider": "fal", "model": "x/y", "seed": 1, "prompt": "p", "negative": "n",
                    "params": {"a": 1}, "tags": ["red", "square"]}
            wrote = write_embedded_meta(fp, meta)
            back = read_embedded_meta(fp)
            good = wrote and back and back["tags"] == meta["tags"] and back["provider"] == "fal"
            print(f"{ext}: write={wrote} read_ok={bool(back)} match={good}")
            ok = ok and good
    print("ALL PASS" if ok else "FAILED")
    sys.exit(0 if ok else 1)
