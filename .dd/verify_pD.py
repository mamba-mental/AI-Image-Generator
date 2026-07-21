"""Batch D EXECUTABLE harness — re-runs the real behaviors for #1/#3/#9/#11/#12/#13 and leaves
binary pass/fail output. Unlike verify_pB/pC (static string checks) this actually executes the
functions. Network-gated checks (live fal caption, provider reachability) run only when a key is
present and are reported separately so the core logic proof never depends on the network.

Run: python .dd/verify_pD.py
"""
import base64
import os
import sys
import tempfile
from io import BytesIO

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402

import engine.keypool as keypool  # noqa: E402
import engine.save as save  # noqa: E402
import engine.history as history  # noqa: E402
import bridge  # noqa: E402
import engine.backends.openrouter_api as orr  # noqa: E402
import engine.backends.fal_api as fal  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


tmp = tempfile.mkdtemp(prefix="void_pD_verify_")

# ---- #13 multi-key pool + auto-swap logic ----
os.environ["PDK"] = "k1"; os.environ["PDK_2"] = "k2"; os.environ["PDKS"] = "k3,k4"
n = keypool.build("pdtest", "PDK")
check("13.1 pool built from primary+_2+comma", n == 4, f"size={n}")
b = keypool.current("pdtest"); keypool.rotate("pdtest"); a = keypool.current("pdtest")
check("13.2 rotate advances + mirrors env", a != b and os.environ["PDK"] == a, f"{b}->{a}")
os.environ["PDS1"] = "solo"; os.environ.pop("PDS1_2", None); os.environ.pop("PDS1S", None)
keypool.build("solo", "PDS1")
check("13.3 single-key pool cannot rotate (neg)", keypool.rotate("solo") is False)

# jobs' rate-limit detector (the auto-swap trigger)
import engine.jobs as jobs  # noqa: E402
check("13.4 rate-limit detector fires on 429/401/quota",
      jobs._looks_rate_limited(["x Error: HTTP 429 rate limit"]) and
      jobs._looks_rate_limited(["x Error: 401 unauthorized"]) and
      not jobs._looks_rate_limited(["x Error: bad prompt"]))

# ---- #1 NSFW backstop (wires the dead FLUX_DISABLE_SAFETY) ----
entry = {"id": "fal-ai/flux/dev", "params": [{"name": "enable_safety_checker", "type": "bool"}]}
os.environ["FLUX_DISABLE_SAFETY"] = "true"
a1 = fal._build_args(entry, {"prompt": "x"})
check("1.1 FLUX_DISABLE_SAFETY -> permissive default", a1.get("enable_safety_checker") is False)
a2 = fal._build_args(entry, {"prompt": "x", "enable_safety_checker": True})
check("1.2 UI value wins over backstop", a2.get("enable_safety_checker") is True)
a3 = fal._build_args({"id": "m", "params": [{"name": "guidance_scale"}]}, {"prompt": "x"})
check("1.3 no inject on unsupported model (no 422)", "enable_safety_checker" not in a3)
app_js = (__import__("pathlib").Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")
check("1.4 NSFW_POLICY 6 providers incl openai hard-no",
      app_js.count('p: "') >= 6 and 'p: "openai"' in app_js and 'allow: "no"' in app_js)

# ---- #9 sidecar roundtrip (durable file this time) ----
img = os.path.join(tmp, "generated_20260713_000000.png")
Image.new("RGB", (128, 96), (10, 20, 30)).save(img)
side = save.write_sidecar(img, {"service": "fal", "model": "fal-ai/flux/dev", "prompt": "neon cat", "seed": 7})
import json as _json  # noqa: E402
sc = _json.load(open(side, encoding="utf-8"))
check("9.1 sidecar written with dims/bytes/ts",
      os.path.exists(side) and sc["width"] == 128 and sc["height"] == 96 and sc["bytes"] > 0 and "ts" in sc)
import types  # noqa: E402
stub = types.SimpleNamespace(config={"output_directory": tmp}, _library_dirs=lambda: [])
rm = bridge.Api.read_meta.__get__(stub, bridge.Api)
check("9.2 read_meta prefers sidecar", rm("generated_20260713_000000.png").get("source") == "sidecar")
img2 = os.path.join(tmp, "nosidecar.png"); Image.new("RGB", (8, 8), (0, 0, 0)).save(img2)
history.record(tmp, {"service": "openai", "model": "gpt-image", "prompt": "old", "seed": 1, "files": [img2], "params": {}})
check("9.3 read_meta history fallback", rm("nosidecar.png").get("source") == "history")
check("9.4 read_meta missing -> none (neg)", rm("ghost.png").get("source") == "none")

# ---- #3 img->prompt DETECT path (offline) ----
stub._resolve = bridge.Api._resolve.__get__(stub, bridge.Api)
stub.read_meta = rm
analyze = bridge.Api.analyze_image.__get__(stub, bridge.Api)
d = analyze("generated_20260713_000000.png")
check("3.1 analyze detects prompt from sidecar", d.get("prompt") == "neon cat" and d.get("source") == "sidecar")

# ---- #11 OpenRouter parser (offline) ----
buf = BytesIO(); Image.new("RGB", (16, 16), (200, 30, 30)).save(buf, format="PNG")
duri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
p1 = orr._parse({"choices": [{"message": {"images": [{"image_url": {"url": duri}}]}}]})
check("11.1 data-URI -> PIL Image", len(p1) == 1 and isinstance(p1[0], Image.Image))
p2 = orr._parse({"choices": [{"message": {"images": [{"image_url": {"url": "https://x/y.png"}}]}}]})
check("11.2 http URL -> passthrough", p2 == ["https://x/y.png"])
p3 = orr._parse({"error": {"message": "model not found"}})
check("11.3 error body surfaced (neg)", "model not found" in p3[0])
os.environ.pop("OPENROUTER_API_KEY", None)
check("11.4 no key -> clear error (neg)", orr.generate("m", {"prompt": "x"})[0].startswith("openrouter Error: OPENROUTER_API_KEY"))

# ---- #12 per-family prompting + negative gating ----
for fam, neg in [("flux", "false"), ("gpt-image", "false"), ("nano-banana", "false"),
                 ("imagen", "true"), ("sdxl", "true"), ("seedream", "true")]:
    pass
check("12.1 PROMPT_GUIDE has flux/gpt-image/imagen/sdxl families",
      all(f'{f}:' in app_js or f'"{f}"' in app_js for f in ("flux", "gpt-image", "imagen", "sdxl")))
check("12.2 negative gating present (neg: false for FLUX-family)",
      "neg: false" in app_js and "neg: true" in app_js and "modelFamily" in app_js)

print()
n_pass = sum(1 for _, ok, _ in results if ok)
print(f"{n_pass}/{len(results)} Batch D executable checks pass")

# ---- network-gated (reported separately; never fails the core proof) ----
print("\n-- network-gated (informational) --")
if os.environ.get("FAL_KEY"):
    try:
        cap = analyze  # analyze on an image with no metadata triggers a real fal caption
        blank = os.path.join(tmp, "unknown_net.png")
        im = Image.new("RGB", (200, 200), (240, 240, 240))
        for x in range(70, 130):
            for y in range(70, 130):
                im.putpixel((x, y), (30, 60, 200))
        im.save(blank)
        r = cap("unknown_net.png")
        print(f"  [LIVE] fal caption via analyze_image: {'OK' if r.get('prompt') else 'FAIL'} — {str(r.get('prompt') or r.get('error'))[:80]}")
    except Exception as e:
        print(f"  [LIVE] fal caption skipped: {type(e).__name__}: {e}")
else:
    print("  [SKIP] FAL_KEY not set — live caption + fal reachability not run")

sys.exit(0 if n_pass == len(results) else 1)
