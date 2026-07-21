"""Acceptance verifier for .dd/uncensored-providers-contract.md (Phase 3).
Structural (always): registration, key mapping, services/params/seeds, request-body shape,
response parsing. Live (key-gated): Together (+ Runware/Novita if keyed) produce a VIEWABLE
uncensored render on the benchmark prompt. Run: python .dd/verify_providers.py"""
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import config as ecfg                       # noqa: E402
from engine.backends import BACKENDS, runware_api, novita_api  # noqa: E402
import engine.backends.together_api as tg               # noqa: E402
import bridge                                            # noqa: E402

checks = []
def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))

# AC-1 — backends registered + callable
for s in ("together", "runware", "novita"):
    chk(f"AC-1 {s} registered + callable", callable(BACKENDS.get(s)))

# AC-2 — key mappings
chk("AC-2 runware key mapping", ecfg.KEY_FIELDS.get("runware") == ("runware_api_key", "RUNWARE_API_KEY"))
chk("AC-2 novita key mapping", ecfg.KEY_FIELDS.get("novita") == ("novita_api_key", "NOVITA_API_KEY"))

# full Api() — resolves keys to env (needed for AC-7) + gives real get_state()
api = bridge.Api()
state = api.get_state()

# AC-3 — services + param schemas + seeds
chk("AC-3 services include together/runware/novita",
    all(s in state["services"] for s in ("together", "runware", "novita")))
sp = state["service_params"]
chk("AC-3 runware param schema declares checkNSFW",
    "runware" in sp and any(p["name"] == "checkNSFW" for p in sp["runware"]["default"]))
chk("AC-3 novita param schema declares enable_nsfw_detection",
    "novita" in sp and any(p["name"] == "enable_nsfw_detection" for p in sp["novita"]["default"]))
rm = state["recent_models"]
chk("AC-3 runware + novita model seeds present", bool(rm.get("runware")) and bool(rm.get("novita")))

# AC-4 — correct disable-safety param in each request body (structural, no network for together)
_orig_urlopen = tg.urllib.request.urlopen
_cap = {}
class _Resp:
    def read(self):
        return json.dumps({"data": [{"url": "http://x/1.png"}]}).encode()
def _fake(req, timeout=0):
    _cap["body"] = json.loads(req.data.decode())
    return _Resp()
tg.urllib.request.urlopen = _fake
os.environ.setdefault("TOGETHER_API_KEY", "x")  # ensure the key-guard passes for the structural call
tg.generate("black-forest-labs/FLUX.1-schnell", {"prompt": "x", "disable_safety_checker": True})
tg.urllib.request.urlopen = _orig_urlopen       # restore for the live probe
chk("AC-4 together body carries disable_safety_checker=true", _cap.get("body", {}).get("disable_safety_checker") is True)
chk("AC-4 runware task carries checkNSFW=false",
    runware_api._build_task("m", {"prompt": "x", "checkNSFW": False}).get("checkNSFW") is False)
chk("AC-4 novita nests enable_nsfw_detection under request",
    novita_api._build_body("m", {"prompt": "x", "enable_nsfw_detection": False})["request"].get("enable_nsfw_detection") is False)

# AC-6 — response parsing
chk("AC-6 runware _parse extracts imageURL", runware_api._parse({"data": [{"imageURL": "http://x/1.png"}]}) == ["http://x/1.png"])
chk("AC-6 runware _parse errors on empty", "Error" in runware_api._parse({"data": []})[0])
chk("AC-6 novita _imgs extracts image_url", novita_api._imgs({"images": [{"image_url": "http://x/1.jpg"}]}) == ["http://x/1.jpg"])

# AC-7 — live uncensored render (key-gated; a skip is NOT a fail)
PROMPT = "artistic nude figure study of a woman, tasteful fine-art photography, soft studio light"
def _viewable(url):
    from PIL import Image, ImageStat
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    st = ImageStat.Stat(Image.open(io.BytesIO(raw)).convert("L"))
    return (st.mean[0] > 12 or st.stddev[0] > 8), st.mean[0]

def live_probe(svc, model, extra):
    key = os.environ.get(dict(ecfg.KEY_FIELDS)[svc][1])
    if not key or key in ("x", ""):
        print(f"[SKIP] AC-7 {svc} live probe — no key configured")
        return
    res = BACKENDS[svc](model, {"prompt": PROMPT, "num_outputs": 1, **extra})
    url = next((r for r in res if isinstance(r, str) and r.startswith("http")), None)
    if not url:
        chk(f"AC-7 {svc} live returned an image", False, f"got: {str(res)[:160]}")
        return
    ok, mean = _viewable(url)
    chk(f"AC-7 {svc} live uncensored render viewable (mean={mean:.1f})", ok)

live_probe("together", "black-forest-labs/FLUX.1-schnell", {"disable_safety_checker": True})
live_probe("runware", (rm.get("runware") or ["runware:100@1"])[0], {"checkNSFW": False})
live_probe("novita", (rm.get("novita") or ["sd_xl_base_1.0"])[0], {"enable_nsfw_detection": False})

print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)} structural)")
sys.exit(0 if all(checks) else 1)
