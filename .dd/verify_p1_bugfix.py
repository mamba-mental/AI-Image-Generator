#!/usr/bin/env python3
"""P1 bugfix harness: #4 img2img ext + #8 model-id purge/guard. --live runs AC-2."""
import json, re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
R = []
def check(n, f):
    try: f(); R.append((n, True, ""))
    except Exception as e: R.append((n, False, f"{type(e).__name__}: {e}"[:180]))

DEAD = {
    "config.json": None, "config.default.json": None,
    "_ids": ["dall-e-3", "stabilityai/stable-diffusion-3.5-large",
             "huggingface.co/CultriX/flux-nsfw-highress",
             "huggingface.co/lustlyai/Flux_Lustly.ai_Uncensored_nsfw_v1",
             "black-forest-labs/flux-1.1-pro-ultra",
             "huggingface.co/black-forest-labs/FLUX.1-dev",
             "https://huggingface.co/CultriX/flux-nsfw-highress"],
}

def ac1():
    from engine import save
    assert hasattr(save, "_pick_ext"), "save._pick_ext missing"
    assert save._pick_ext("https://x.fal.media/a/b/img.jpg", "application/octet-stream", "d.png") == ".jpg"
    assert save._pick_ext("https://x/v.mp4", "application/octet-stream", "d.png") == ".mp4"
    assert save._pick_ext("https://x/noext", "image/png", "d.tmp") == ".png"
    assert save._pick_ext("https://x/mesh.glb", "application/octet-stream", "d.png") == ".glb"

def ac3():
    for fn in ("config.json", "config.default.json"):
        p = ROOT / fn
        if not p.exists():
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        recents = " ".join(json.dumps(cfg.get(k, [])) for k in cfg if k.startswith("recent_models_"))
        for did in DEAD["_ids"]:
            assert did not in recents, f"{fn}: dead id still present -> {did}"

def ac4():
    import bridge
    n = bridge.Api._normalize_model_id if hasattr(bridge.Api, "_normalize_model_id") else None
    assert n, "bridge.Api._normalize_model_id missing"
    api = bridge.Api()
    assert api._normalize_model_id("huggingface", "huggingface.co/x/y") == "x/y"
    assert api._normalize_model_id("replicate", "https://huggingface.co/a/b") == "a/b"
    assert api._normalize_model_id("fal", "fal-ai/flux/dev") == "fal-ai/flux/dev"
    assert api._normalize_model_id("openai", "gpt-image-2") == "gpt-image-2"
    assert api._normalize_model_id("huggingface", "") == ""

def ac5():
    r = subprocess.run([sys.executable, str(ROOT / "main.py"), "--smoke"],
                       capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    assert r.returncode == 0 and "SMOKE OK" in r.stdout, f"rc={r.returncode} {r.stdout[-200:]}{r.stderr[-200:]}"

def ac2_live():
    import bridge, time, pathlib as pl
    bridge.Api()
    from engine.backends import fal_api
    inp = next(pl.Path(ROOT / "generated_images").glob("*.png"), None) or \
          next((pl.Path(p) for p in [__import__("engine.config", fromlist=["load"]).load()["output_directory"]]
                for f in pl.Path(p).glob("*.png")), None)
    src = str(inp) if inp else None
    assert src, "no local image to use as img2img input"
    t = time.time()
    res = fal_api.generate("fal-ai/flux-pro/kontext",
                           {"prompt": "make it a watercolor", "image": src, "_inputs": {"image": src}},
                           progress=lambda m: None)
    from engine import save, config as ec
    out = save.make_output_paths(ec.load()["output_directory"], 1, ".png")
    saved, errs = save.persist_results(res, out)
    assert saved, f"nothing saved: {errs}"
    ext = pl.Path(saved[0]).suffix.lower()
    assert ext in (".jpg", ".jpeg", ".png", ".webp"), f"kontext saved as {ext} (blank-tile bug) after {time.time()-t:.0f}s"

def main():
    live = "--live" in sys.argv
    for n, f in [("AC-1 pick_ext url-first", ac1), ("AC-3 dead-ids purged", ac3),
                 ("AC-4 normalize guard", ac4), ("AC-5 smoke", ac5)]:
        check(n, f)
    if live:
        check("AC-2 LIVE kontext img ext", ac2_live)
    w = max(len(n) for n, *_ in R)
    ok = True
    for n, p, e in R:
        print(f"{n:<{w}}  {'PASS' if p else 'FAIL'}  {e}"); ok &= p
    print(f"\nOVERALL: {'GREEN' if ok else 'RED'}" + ("" if live else "  (AC-2 live not run)"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
