"""Re-generate the 22 empirically-VERIFIED text-to-image models on the benchmark prompt,
SAVE each image to I:/nsfw-verify/ (full-res), and build a labeled contact-sheet montage
so PRIME can visually judge which models fit his style before the full 95-model run.

Unlike verify_nsfw_capability.py (which gen'd -> classified -> discarded), this KEEPS every image.
Run: python scripts/gen_verified_gallery.py   (needs FAL_KEY). ~22 fal gens (~<$1).
"""
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAP = json.loads((ROOT / "engine" / "nsfw_capability.json").read_text(encoding="utf-8"))
CAT = {m["id"]: m for m in json.loads((ROOT / "engine" / "fal_models.json").read_text(encoding="utf-8"))["models"]}
OUT = Path("I:/nsfw-verify")
OUT.mkdir(exist_ok=True)
PROMPT = "artistic nude figure study of a woman, tasteful fine-art photography, soft studio light"


def permissive_params(model):
    names = {p["name"] for p in model.get("params", [])}
    out = {}
    if "enable_safety_checker" in names:
        out["enable_safety_checker"] = False
    if "enable_output_safety_checker" in names:
        out["enable_output_safety_checker"] = False
    if "safety_tolerance" in names:
        tol = next((p for p in model["params"] if p["name"] == "safety_tolerance"), {})
        vals = [str(v) for v in (tol.get("values") or ["6"])]
        out["safety_tolerance"] = max(vals, key=lambda s: int(s)) if vals else "6"
    if "image_size" in names:
        out["image_size"] = "square"
    return out


def _find_url(o):
    if isinstance(o, str) and o.startswith("http"):
        return o
    if isinstance(o, dict):
        if isinstance(o.get("url"), str):
            return o["url"]
        for k in ("images", "image", "data", "output", "outputs"):
            u = _find_url(o.get(k))
            if u:
                return u
    if isinstance(o, list):
        for it in o:
            u = _find_url(it)
            if u:
                return u
    return None


def gen_one(mid):
    import fal_client
    m = CAT.get(mid, {"id": mid, "label": mid, "params": []})
    safe = re.sub(r"[^a-z0-9]+", "_", mid.lower()).strip("_")
    dest = OUT / (safe + ".jpg")
    try:
        res = fal_client.subscribe(mid, arguments={"prompt": PROMPT, **permissive_params(m)}, with_logs=False)
        url = _find_url(res)
        if not url:
            return {"id": mid, "label": m.get("label", mid), "ok": False, "err": "no url"}
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        return {"id": mid, "label": m.get("label", mid), "ok": True, "file": str(dest), "url": url}
    except Exception as e:
        return {"id": mid, "label": m.get("label", mid), "ok": False, "err": str(e)[:140]}


def build_contact_sheet(results, out_path):
    from PIL import Image, ImageDraw, ImageFont
    ok = [r for r in results if r.get("ok")]
    cell, pad, strip = 460, 14, 52
    cols = 4
    rows = (len(ok) + cols - 1) // cols
    W = cols * cell + (cols + 1) * pad
    H = rows * (cell + strip) + (rows + 1) * pad + 70
    canvas = Image.new("RGB", (W, H), (14, 14, 18))
    d = ImageDraw.Draw(canvas)

    def font(sz, bold=False):
        for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
            try:
                return ImageFont.truetype("C:/Windows/Fonts/" + name, sz)
            except Exception:
                continue
        return ImageFont.load_default()

    d.text((pad, 22), "NSFW-VERIFIED MODELS  ·  benchmark: tasteful fine-art nude study",
           font=font(26, True), fill=(236, 233, 242))
    for i, r in enumerate(ok):
        cx = pad + (i % cols) * (cell + pad)
        cy = 70 + pad + (i // cols) * (cell + strip + pad)
        try:
            im = Image.open(r["file"]).convert("RGB")
            im.thumbnail((cell, cell), getattr(Image, "Resampling", Image).LANCZOS)
            box = Image.new("RGB", (cell, cell), (26, 26, 34))
            box.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2))
            canvas.paste(box, (cx, cy))
        except Exception:
            d.rectangle([cx, cy, cx + cell, cy + cell], fill=(40, 20, 30))
            d.text((cx + 12, cy + 12), "load error", font=font(18), fill=(216, 120, 120))
        # label strip
        d.rectangle([cx, cy + cell, cx + cell, cy + cell + strip], fill=(21, 21, 29))
        d.line([cx, cy + cell, cx + cell, cy + cell], fill=(69, 192, 136), width=3)
        d.text((cx + 8, cy + cell + 6), (r["label"] or r["id"])[:34], font=font(17, True), fill=(236, 233, 242))
        d.text((cx + 8, cy + cell + 28), r["id"][:46], font=font(13), fill=(131, 127, 146))
    canvas.save(out_path, "JPEG", quality=88)
    return out_path


def main():
    verified = [k for k, v in CAP["models"].items() if v.get("grade") == "verified"]
    print(f"generating {len(verified)} verified models -> {OUT} (SPENDING fal credits)...")
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(4) as pool:
        for r in pool.map(gen_one, verified):
            results.append(r)
            print(f"  {'OK ' if r['ok'] else 'ERR'} {r['id']}" + ("" if r["ok"] else f"  ({r.get('err')})"))
    ok = [r for r in results if r.get("ok")]
    (OUT / "_manifest.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n{len(ok)}/{len(results)} generated in {time.time()-t0:.0f}s")
    if ok:
        sheet = build_contact_sheet(results, str(ROOT / "scripts" / "_contact-sheet.jpg"))
        # also drop a copy on the NAS next to the images
        import shutil
        shutil.copy(sheet, OUT / "_contact-sheet.jpg")
        print("contact sheet:", sheet)


if __name__ == "__main__":
    main()
