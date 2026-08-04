"""Re-generate the 22 empirically-VERIFIED text-to-image models on the benchmark prompt,
SAVE each image to I:/nsfw-verify/ (full-res), and build a labeled contact-sheet montage
so PRIME can visually judge which models fit his style before the full 95-model run.

Unlike verify_nsfw_capability.py (which gen'd -> classified -> discarded), this KEEPS every image.
Run: python scripts/gen_verified_gallery.py   (needs FAL_KEY). ~22 fal gens (~<$1).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CAP = json.loads((ROOT / "engine" / "nsfw_capability.json").read_text(encoding="utf-8"))
CAT = {m["id"]: m for m in json.loads((ROOT / "engine" / "fal_models.json").read_text(encoding="utf-8"))["models"]}
# Console pages + their data live under C:/AI CoWork/dashboards (served at :31960).
DASH = Path(r"C:/AI CoWork/dashboards")
DEFAULT_OUT = Path("I:/nsfw-verify")            # base (untagged) full-res archive
DEFAULT_PROMPT = "artistic nude figure study of a woman, tasteful fine-art photography, soft studio light"
OUT = DEFAULT_OUT                                # overridden per-run in main()
PROMPT = DEFAULT_PROMPT                          # overridden per-run in main()


def _ensure_fal_key():
    """Resolve the fal key the way the app does (config.json 'fal_api_key' -> FAL_KEY env), so a
    subprocess-launched run isn't at the mercy of the parent server's start-time environment."""
    if os.environ.get("FAL_KEY"):
        return
    try:
        sys.path.insert(0, str(ROOT))
        from engine import config as _config
        _config.resolve_keys(_config.load())
    except Exception as e:  # noqa: BLE001
        print(f"  (config key-load failed: {type(e).__name__})", flush=True)
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("FAL_KEY not set - add 'fal_api_key' to config.json or export FAL_KEY.")


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
        res = fal_client.subscribe(mid, arguments={"prompt": PROMPT, **permissive_params(m)}, with_logs=False, client_timeout=180)
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
    global PROMPT, OUT
    ap = argparse.ArgumentParser(description="Re-generate the fal-verified models on a prompt + save images.")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="the Test-1 prompt to render (default: fine-art nude)")
    ap.add_argument("--tag", default=None, help="date-version slug. When set, images go to "
                    "dashboards/nsfw-img/<tag>/ and dashboards/data/nsfw-verified-test1-<tag>.json is written.")
    args = ap.parse_args()
    _ensure_fal_key()
    PROMPT = (args.prompt or "").strip() or DEFAULT_PROMPT
    tag = (args.tag or "").strip() or None
    OUT = (DASH / "nsfw-img" / tag) if tag else DEFAULT_OUT
    OUT.mkdir(parents=True, exist_ok=True)

    # Test 1 scope = fal text-to-image models graded "verified" in the capability file. Resolve the
    # BARE fal model id from the "provider:id" key so fal_client.subscribe gets a real model id.
    verified = []
    for k, v in CAP["models"].items():
        if v.get("grade") != "verified":
            continue
        provider = v.get("provider") or (k.split(":", 1)[0] if ":" in k else "fal")
        if provider != "fal":
            continue
        mid = v.get("model") or (k.split(":", 1)[-1] if ":" in k else k)
        verified.append((mid, v))

    print(f"generating {len(verified)} fal-verified models -> {OUT} (SPENDING fal credits)...", flush=True)
    t0 = time.time()
    cap_by_mid = {mid: v for mid, v in verified}
    results = []
    with ThreadPoolExecutor(4) as pool:
        for r in pool.map(gen_one, [mid for mid, _ in verified]):
            results.append(r)
            print(f"  {'OK ' if r['ok'] else 'ERR'} {r['id']}" + ("" if r["ok"] else f"  ({r.get('err')})"), flush=True)
    ok = [r for r in results if r.get("ok")]
    (OUT / "_manifest.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n{len(ok)}/{len(results)} generated in {time.time()-t0:.0f}s", flush=True)

    # Tagged run → emit the reproducible Test-1 console dataset the page consumes (shape mirrors
    # data/nsfw-verified-test1.json). Untagged run keeps the legacy archive + contact-sheet only,
    # so the working base dataset is never overwritten.
    if tag:
        sample_prefix = f"nsfw-img/{tag}/"
        rows = []
        for r in results:
            mid = r["id"]
            cap = cap_by_mid.get(mid, {})
            fn = re.sub(r"[^a-z0-9]+", "_", mid.lower()).strip("_") + ".jpg"
            rows.append({
                "provider": "fal", "model": mid, "label": r.get("label") or mid,
                "grade": "verified" if r.get("ok") else "blacked",
                "votes": cap.get("nsfw_votes"), "mean": cap.get("mean"),
                "sample": (sample_prefix + fn) if r.get("ok") else "", "test": 1,
            })
        rows.sort(key=lambda x: (x["grade"] != "verified", x["model"]))
        data_path = DASH / "data" / f"nsfw-verified-test1-{tag}.json"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(json.dumps({
            "test": 1, "prompt": PROMPT, "prompt_label": "Test 1 — custom rerun",
            "provider_note": "fal text-to-image models graded verified, re-rendered on this prompt",
            "tested_total": len(results), "verified_count": len(ok),
            "generated_at": time.strftime("%Y-%m-%d"), "tag": tag, "models": rows,
        }, indent=1), encoding="utf-8")
        print("console dataset:", data_path, flush=True)
    elif ok:
        sheet = build_contact_sheet(results, str(ROOT / "scripts" / "_contact-sheet.jpg"))
        # also drop a copy on the NAS next to the images
        import shutil
        shutil.copy(sheet, OUT / "_contact-sheet.jpg")
        print("contact sheet:", sheet)


if __name__ == "__main__":
    main()
