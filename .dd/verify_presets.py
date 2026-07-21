"""Acceptance verifier for Spec C #4 — Style/Recipe presets.
Hermetic (mktemp fixtures, no NAS). The DB layer (Style vs Recipe distinct persistence,
defaults) is tested directly here; the pure apply/substitution/param-map logic lives in
web/presets.js (browser + node, same dual-consumption pattern as content_mode.js) and is
tested by scripts/verify_presets_apply.js — this script shells out to it and folds the result
into ONE pass/fail, per the spec's "each is a binary check". Run: python .dd/verify_presets.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bridge  # noqa: E402
from engine import library_index as LI  # noqa: E402

checks = []
def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


tmp = Path(tempfile.mkdtemp(prefix="voidpresets_"))
idx = LI.LibraryIndex(str(tmp / "library.db"))

# ---- Style vs Recipe persisted DISTINCTLY in their own tables ----
sid = idx.save_preset("styles", {"name": "Editorial", "negative": "blurry", "prompt_template": "cinematic, {prompt}",
                                  "params": {"guidance_scale": 3.5}, "model": ""})
rid = idx.save_preset("recipes", {"name": "Exact shot", "provider": "together", "model": "flux-dev",
                                   "seed": "12345", "prompt": "a red dragon", "negative": "",
                                   "params": {"guidance_scale": 7}})
styles = idx.list_presets("styles")
recipes = idx.list_presets("recipes")
chk("Style persisted in the styles table", any(s["id"] == sid and s["name"] == "Editorial" for s in styles))
chk("Recipe persisted in the recipes table", any(r["id"] == rid and r["name"] == "Exact shot" for r in recipes))
chk("Style row has NO provider/seed columns (distinct shape)", "provider" not in styles[0] and "seed" not in styles[0])
chk("Recipe row carries provider+seed (distinct shape)", recipes[0]["provider"] == "together" and recipes[0]["seed"] == "12345")
chk("params_json round-trips as a real dict", idx.get_preset("styles", sid)["params"]["guidance_scale"] == 3.5)

# ---- AC-4.2 — recall + ONE default per type ----
sid2 = idx.save_preset("styles", {"name": "Fashion", "prompt_template": "runway, {prompt}"})
idx.set_default_preset("styles", sid2)
defaults = [s for s in idx.list_presets("styles") if s["is_default"]]
chk("exactly one default style after set_default_preset", len(defaults) == 1 and defaults[0]["id"] == sid2)
idx.set_default_preset("styles", sid)
defaults2 = [s for s in idx.list_presets("styles") if s["is_default"]]
chk("switching the default clears the previous one (one per type)", len(defaults2) == 1 and defaults2[0]["id"] == sid)
chk("get_default_preset returns the current default", idx.get_default_preset("styles")["id"] == sid)
chk("no default recipe yet -> get_default_preset returns None", idx.get_default_preset("recipes") is None)

# ---- rename / delete (AC-4.5 manager operations) ----
idx.rename_preset("styles", sid2, "Fashion Renamed")
chk("rename_preset persists", idx.get_preset("styles", sid2)["name"] == "Fashion Renamed")
idx.delete_preset("styles", sid2)
chk("delete_preset removes the row", idx.get_preset("styles", sid2) is None)

idx.close()

# ---- bridge wiring smoke (Api surface PRIME's UI actually calls) ----
api = bridge.Api.__new__(bridge.Api)
api.config = {"output_directory": str(tmp), "library_directories": []}
api._library_index_path = lambda: str(tmp / "index2.json")
api._persist = lambda: None
r1 = api.save_style({"name": "Bridge Style", "prompt_template": "{prompt}, moody"})
chk("bridge save_style returns an id", r1.get("ok") and isinstance(r1.get("id"), int))
r2 = api.save_recipe({"name": "Bridge Recipe", "provider": "fal", "model": "flux/dev",
                       "seed": "1", "prompt": "p", "params": {}})
chk("bridge save_recipe returns an id", r2.get("ok") and isinstance(r2.get("id"), int))
chk("bridge list_styles sees it", any(s["name"] == "Bridge Style" for s in api.list_styles()))
chk("bridge list_recipes sees it", any(r["name"] == "Bridge Recipe" for r in api.list_recipes()))
api.set_default_style(r1["id"])
chk("bridge set_default_style + get_default_presets", (api.get_default_presets().get("style") or {}).get("id") == r1["id"])
api.rename_recipe(r2["id"], "Renamed Recipe")
chk("bridge rename_recipe", any(r["name"] == "Renamed Recipe" for r in api.list_recipes()))
api.delete_style(r1["id"])
chk("bridge delete_style", not any(s["id"] == r1["id"] for s in api.list_styles()))
if hasattr(api, "_lib_idx"):
    api._lib_idx.close()

# ---- pure apply logic (substitution 0/1/N, idempotent, non-blanking, cross-provider map) ----
node = subprocess.run(["node", str(ROOT / "scripts" / "verify_presets_apply.js")],
                       cwd=str(ROOT), capture_output=True, text=True)
print(node.stdout.strip())
if node.stderr.strip():
    print(node.stderr.strip(), file=sys.stderr)
chk("web/presets.js apply logic (node harness) all green", node.returncode == 0)

print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
