"""Acceptance verifier for .dd/lora-support-contract.md (Phase 4).
Asserts each provider's EXACT LoRA request shape (research/2026-07-20_lora-syntax-per-provider.md)
via the backends' pure builders + a urlopen-capture for Together, plus Civitai ref conversion.
Run: python .dd/verify_lora.py"""
import inspect
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bridge  # noqa: E402
from engine.backends import fal_api, replicate_api, together_api, runware_api, novita_api, hf_api  # noqa: E402

checks = []
def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))

LO = [{"url": "lora-A", "scale": 0.8, "enabled": True},
      {"url": "lora-B", "scale": 0.5, "enabled": True}]

# AC-1 — managers for all six LoRA-capable services + exposed in get_state
api = bridge.Api()
api._persist = lambda: None  # no config writes during the test
for s in ("fal", "together", "runware", "novita", "huggingface", "replicate"):
    chk(f"AC-1 {s} has a LoRA manager", s in api.lora_managers)
st = api.get_state()
chk("AC-1 get_state.loras exposes all six",
    all(s in st["loras"] for s in ("fal", "together", "runware", "novita", "huggingface", "replicate")))

# AC-2 — fal loras:[{path,scale}], gated to LoRA endpoints
a1 = fal_api._build_args({"id": "fal-ai/flux-lora", "params": []}, {"prompt": "x", "enabled_loras": LO})
chk("AC-2 fal LoRA endpoint -> loras:[{path,scale}]",
    a1.get("loras") == [{"path": "lora-A", "scale": 0.8}, {"path": "lora-B", "scale": 0.5}])
a2 = fal_api._build_args({"id": "fal-ai/flux/dev", "params": []}, {"prompt": "x", "enabled_loras": LO})
chk("AC-2 fal base model -> NO loras", "loras" not in a2)

# AC-3 — Replicate per-model (multi vs single)
r_multi = replicate_api._build_input({"prompt": "x", "enabled_loras": LO}, "owner/flux-dev-multi-lora")
chk("AC-3 replicate multi-lora -> hf_loras[]+lora_scales[]",
    r_multi.get("hf_loras") == ["lora-A", "lora-B"] and r_multi.get("lora_scales") == [0.8, 0.5])
r_single = replicate_api._build_input({"prompt": "x", "enabled_loras": LO}, "owner/flux-dev-lora")
chk("AC-3 replicate flux-dev-lora -> lora_weights+extra_lora",
    r_single.get("lora_weights") == "lora-A" and r_single.get("extra_lora") == "lora-B"
    and r_single.get("extra_lora_scale") == 0.5)

# AC-4 — Together image_loras (max 2, gated) via urlopen-capture
_orig = together_api.urllib.request.urlopen
_cap = {}
class _R:
    def read(self):
        return json.dumps({"data": [{"url": "http://x/1.png"}]}).encode()
def _fake(req, timeout=0):
    _cap["body"] = json.loads(req.data.decode())
    return _R()
together_api.urllib.request.urlopen = _fake
os.environ.setdefault("TOGETHER_API_KEY", "x")
together_api.generate("black-forest-labs/FLUX.1-dev-lora", {"prompt": "x", "enabled_loras": LO})
chk("AC-4 together dev-lora -> image_loras:[{path,scale}]",
    _cap["body"].get("image_loras") == [{"path": "lora-A", "scale": 0.8}, {"path": "lora-B", "scale": 0.5}])
_cap.clear()
together_api.generate("black-forest-labs/FLUX.1-schnell", {"prompt": "x", "enabled_loras": LO})
chk("AC-4 together non-lora model -> NO image_loras", "image_loras" not in _cap["body"])
together_api.urllib.request.urlopen = _orig

# AC-5 — Runware / Novita exact shapes
chk("AC-5 runware lora:[{model,weight}]",
    runware_api._build_task("m", {"prompt": "x", "enabled_loras": LO}).get("lora")
    == [{"model": "lora-A", "weight": 0.8}, {"model": "lora-B", "weight": 0.5}])
chk("AC-5 novita request.loras:[{model_name,strength}]",
    novita_api._build_body("m", {"prompt": "x", "enabled_loras": LO})["request"].get("loras")
    == [{"model_name": "lora-A", "strength": 0.8}, {"model_name": "lora-B", "strength": 0.5}])

# AC-6 — HF stacks weights (source reflection; no offline client)
chk("AC-6 hf stacks lora_weights list", '[lo["url"] for lo in _loras]' in inspect.getsource(hf_api))

# AC-7 — Civitai ref conversion + add
chk("AC-7 civitai runware -> AIR", api.civitai_ref_for("runware", 123, 456) == "civitai:123@456")
chk("AC-7 civitai fal -> download URL", api.civitai_ref_for("fal", 123, 456) == "https://civitai.com/api/download/models/456")
add = api.civitai_add_lora("runware", 123, 456)
chk("AC-7 civitai_add_lora adds AIR to runware", add.get("ok") and any(l["url"] == "civitai:123@456" for l in add["loras"]))
chk("AC-7 civitai_add_lora rejects novita (catalog-only)", api.civitai_add_lora("novita", 1, 2).get("ok") is False)

# AC-8 — UI gate widened (source reflection)
appjs = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
chk("AC-8 renderLoras gate widened + fal model-gated",
    'LORA_SERVICES = ["huggingface", "replicate", "fal", "together", "runware", "novita"]' in appjs
    and "falModelSupportsLora" in appjs)

print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
