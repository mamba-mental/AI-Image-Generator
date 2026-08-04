"""LoRA fix — the frontend now attaches params.enabled_loras, and the backend converts it to each
model's real lora field names. Binary: enabled_loras in -> lora fields out.
Run: python .dd/verify_lora_fix.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.backends.replicate_api import _build_input  # noqa: E402
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ---- AC-1: frontend attaches enabled_loras to the generate request ----
gen = app_js[app_js.find("const genParams ="):app_js.find("const r = await api().generate")]
chk("AC-1 request builds enabled_loras from enabled state.loras",
    "genParams.enabled_loras = activeLoras" in gen
    and "state.loras[lsvc]" in gen and ".filter(l => l.enabled)" in gen)

# ---- AC-2: single-LoRA model -> lora_weights + lora_scale ----
lo = [{"url": "user/flux-lora-x", "scale": 0.8, "enabled": True}]
inp = _build_input({"enabled_loras": lo}, "black-forest-labs/flux-dev-lora")
chk("AC-2 single LoRA -> lora_weights", inp.get("lora_weights") == "user/flux-lora-x", str(inp.get("lora_weights")))
chk("AC-2 single LoRA -> lora_scale", inp.get("lora_scale") == 0.8, str(inp.get("lora_scale")))

# ---- AC-3: multi-lora model -> hf_loras + lora_scales arrays ----
los = [{"url": "a/one", "scale": 1.0, "enabled": True}, {"url": "b/two", "scale": 0.5, "enabled": True}]
inp2 = _build_input({"enabled_loras": los}, "lucataco/flux-dev-multi-lora")
chk("AC-3 multi-lora -> hf_loras array", inp2.get("hf_loras") == ["a/one", "b/two"], str(inp2.get("hf_loras")))
chk("AC-3 multi-lora -> lora_scales array", inp2.get("lora_scales") == [1.0, 0.5], str(inp2.get("lora_scales")))

# ---- AC-4: disabled/none -> no lora fields; enabled_loras itself never sent as a raw input ----
inp3 = _build_input({"enabled_loras": [{"url": "x/y", "scale": 1, "enabled": False}]}, "black-forest-labs/flux-dev-lora")
chk("AC-4 disabled LoRA -> no lora_weights", "lora_weights" not in inp3)
chk("AC-4 enabled_loras is stripped from the raw input (engine-only)", "enabled_loras" not in inp3)

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
