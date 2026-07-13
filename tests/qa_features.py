"""AI Studio Void — feature QA harness.
For every fal category: pick a representative model, verify (a) the required input
is derived correctly, (b) _build_args attaches the right *_url for that input, and
(c) output extraction handles the category's output type. Catches pseudo-functionality
(controls that look wired but drop the input / mishandle the output)."""
import json, sys
sys.path.insert(0, ".")
from engine.backends import fal_api

# category prefix -> expected input kind (what the model consumes)
SRC_KIND = {"image": "image", "video": "video", "audio": "audio", "speech": "audio", "3d": "mesh"}
INPUT_ARG = {"image": "image_url", "video": "video_url", "audio": "audio_url", "mesh": "model_mesh_url"}
SAMPLE = {"image": "C:/tmp/x.png", "video": "C:/tmp/x.mp4", "audio": "C:/tmp/x.mp3", "mesh": "C:/tmp/x.glb"}

def expected_input(cat):
    src = cat.split("-to-")[0]
    return SRC_KIND.get(src)  # None for text-to-* and vision

models = json.load(open("engine/fal_models.json", encoding="utf-8"))
lst = models if isinstance(models, list) else models.get("models", [])
by_cat = {}
for m in lst:
    by_cat.setdefault(m.get("category", "?"), []).append(m)

# monkeypatch fal upload so we don't hit the network — return a fake URL for a local path
fal_api.fal_client.upload_file = lambda p: f"https://fake.fal/{str(p).split('/')[-1]}"

results = []
for cat in sorted(by_cat):
    models_c = by_cat[cat]
    m = models_c[0]
    exp_in = expected_input(cat)
    row = {"cat": cat, "n": len(models_c), "model": m["id"], "issues": []}
    # (b) build args with the expected input attached (mimic what bridge.generate passes)
    params = {"prompt": "test"}
    if exp_in:
        params["_inputs"] = {exp_in: SAMPLE[exp_in]}
        params["image"] = SAMPLE[exp_in] if exp_in == "image" else None
    try:
        args = fal_api._build_args(m, params)
        if exp_in:
            want = INPUT_ARG[exp_in]
            if want not in args:
                row["issues"].append(f"input dropped: expected '{want}' in fal args, got {list(args.keys())}")
        else:
            leaked = [k for k in args if k.endswith("_url")]
            if leaked:
                row["issues"].append(f"unexpected input arg for text/vision cat: {leaked}")
    except Exception as e:
        row["issues"].append(f"_build_args crash: {type(e).__name__}: {e}")
    # (c) output extraction for the category's declared output type
    out_kind = m.get("output", "image")
    fake = {"image": {"images": [{"url": "http://x/a.png"}]},
            "video": {"video": {"url": "http://x/a.mp4"}},
            "audio": {"audio": {"url": "http://x/a.mp3"}},
            "text":  {"text": "hello"},
            "mesh":  {"model_mesh": {"url": "http://x/a.glb"}},
            "3d":    {"model_mesh": {"url": "http://x/a.glb"}}}.get(out_kind, {"images": [{"url": "http://x/a.png"}]})
    got = fal_api._extract_outputs(fake, out_kind)
    if not got:
        row["issues"].append(f"output not extracted for output='{out_kind}' (keys {list(fake.keys())})")
    results.append(row)

ok = [r for r in results if not r["issues"]]
bad = [r for r in results if r["issues"]]
print(f"{'CAT':22} {'N':>3}  STATUS")
for r in results:
    st = "OK" if not r["issues"] else "FAIL"
    print(f"{r['cat']:22} {r['n']:>3}  {st}")
    for i in r["issues"]:
        print(f"    - {i}")
print(f"\n{len(ok)}/{len(results)} categories pass input+output handling; {len(bad)} FAIL")
sys.exit(0 if not bad else 1)
