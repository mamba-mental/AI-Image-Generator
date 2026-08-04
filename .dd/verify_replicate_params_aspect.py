"""Replicate: show FULL param set (cap 16->40) + a schema-derived aspect-ratio dropdown.
Run: python .dd/verify_replicate_params_aspect.py
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bridge import _replicate_input_params  # noqa: E402
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ---- AC-1: cap raised — flux-vlta (21 raw) no longer loses seed/width ----
tok = json.load(open(ROOT / "config.json", encoding="utf-8"))["replicate_api_key"]
req = urllib.request.Request("https://api.replicate.com/v1/models/lucataco/flux-vlta",
                             headers={"Authorization": f"Bearer {tok}", "User-Agent": "Mozilla/5.0"})
d = json.load(urllib.request.urlopen(req, timeout=20))
parsed = {p["name"] for p in _replicate_input_params(d)}
chk("AC-1 cap raised: flux-vlta keeps seed + width (were cut by the 16-cap)",
    "seed" in parsed and "width" in parsed, f"{len(parsed)} params parsed")

# ---- AC-2: replicateAspectTable derives from the model's schema (node-eval) ----
def grab(fn):
    m = re.search(r"function " + fn + r"\([^)]*\)\s*\{.*?\n\}", app_js, re.S)
    return m.group(0) if m else ""


wh = re.search(r"const REPLICATE_WH_PRESETS = \{.*?\};", app_js, re.S)
node = (wh.group(0) + "\n" + grab("replicateAspectTable") + "\n"
        "let M; const currentModel=()=>M;\n"
        # case A: aspect_ratio enum -> enum table
        "M={params:[{name:'aspect_ratio',type:'enum',values:['1:1','16:9','9:16']},{name:'seed',type:'int'}]};\n"
        "const A=replicateAspectTable();\n"
        # case B: width+height, no aspect_ratio -> WH presets
        "M={params:[{name:'width',type:'int'},{name:'height',type:'int'}]};\n"
        "const B=replicateAspectTable();\n"
        # case C: neither -> null
        "M={params:[{name:'seed',type:'int'}]};\n"
        "const C=replicateAspectTable();\n"
        "process.stdout.write(JSON.stringify({A,B,C}));")
try:
    p = subprocess.run(["node", "-e", node], capture_output=True, text=True, timeout=15)
    r = json.loads(p.stdout) if p.returncode == 0 else {}
    chk("AC-2a aspect_ratio enum -> ratio table", r.get("A", {}).get("16:9") == "16:9", str(r.get("A")))
    chk("AC-2b width+height (no enum) -> WH presets", isinstance(r.get("B", {}).get("16:9"), dict), str(r.get("B", {}).get("16:9")))
    chk("AC-2c neither -> null (no aspect dropdown)", r.get("C") is None)
except Exception as e:  # noqa: BLE001
    chk("AC-2 replicateAspectTable", False, f"{type(e).__name__}: {e} {p.stderr[:150] if 'p' in dir() else ''}")

# ---- AC-3: servicePresetTable routes replicate to the derived table ----
spt = grab("servicePresetTable")
chk("AC-3 servicePresetTable routes replicate -> replicateAspectTable",
    'service === "replicate"' in spt and "replicateAspectTable()" in spt)

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
