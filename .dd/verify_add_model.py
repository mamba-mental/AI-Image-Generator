"""ATDD/SBE/TDD harness for the "add a model by id/URL" feature.
Contract: .dd/add-model-feature-contract.md   Run: python .dd/verify_add_model.py
"""
import re
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ---- AC-1: parseModelRef normalizes id/URL cases (node-eval the real JS fn) ----
m = re.search(r"function parseModelRef\(raw\)\s*\{.*?\n\}", app_js, re.S)
CASES = [
    ("https://replicate.com/aisha-ai-official/flux.1dev-uncensored-jibmix", "aisha-ai-official/flux.1dev-uncensored-jibmix"),
    ("https://replicate.com/owner/model/versions/47f609a66d7fc329", "owner/model:47f609a66d7fc329"),
    ("owner/model", "owner/model"),
    ("black-forest-labs/flux-dev:abc12345", "black-forest-labs/flux-dev:abc12345"),
    ("   ", ""),
]
if not m:
    chk("AC-1 parseModelRef found", False)
else:
    node = m.group(0) + "\nconst C=" + __import__("json").dumps(CASES) + ";\n" \
        "process.stdout.write(JSON.stringify(C.map(([i,e])=>[parseModelRef(i),e,parseModelRef(i)===e])));"
    try:
        p = subprocess.run(["node", "-e", node], capture_output=True, text=True, timeout=15)
        out = __import__("json").loads(p.stdout) if p.returncode == 0 else []
        allok = out and all(r[2] for r in out)
        chk("AC-1 parseModelRef normalizes id/URL cases", allok,
            "; ".join(f"{r[0]}" + ("" if r[2] else f"!={r[1]}") for r in out) if out else p.stderr[:200])
    except Exception as e:  # noqa: BLE001
        chk("AC-1 parseModelRef normalizes id/URL cases", False, str(e))

# ---- AC-2: bridge.add_recent_model prepends + de-dupes + persists (real method, fake self) ----
try:
    import os
    import tempfile
    # isolate the merge-save's disk path to a throwaway file (not the real config)
    os.environ["VOID_CONFIG"] = str(Path(tempfile.gettempdir()) / "omni_addmodel_test.json")
    try:
        os.remove(os.environ["VOID_CONFIG"])
    except OSError:
        pass
    import engine.config as ec  # noqa: F401
    from bridge import Api as Bridge
    fake = types.SimpleNamespace(config={"recent_models_replicate": ["a/b", "c/d"]})
    fake._save_config = types.MethodType(Bridge._save_config, fake)
    r1 = Bridge.add_recent_model(fake, "replicate", "owner/new-model")
    ok1 = r1["ok"] and r1["models"][0] == "owner/new-model" and "a/b" in r1["models"]
    r2 = Bridge.add_recent_model(fake, "replicate", "a/b")   # existing -> moves to front, no dup
    ok2 = r2["models"][0] == "a/b" and r2["models"].count("a/b") == 1
    r3 = Bridge.add_recent_model(fake, "replicate", "  ")    # blank -> rejected
    chk("AC-2 add_recent_model prepends new id", ok1, str(r1["models"]))
    chk("AC-2 add_recent_model de-dupes existing id", ok2, str(r2["models"]))
    chk("AC-2 add_recent_model rejects blank", r3.get("ok") is False)
    chk("AC-2 last_used_model set", fake.config.get("last_used_model_replicate") == "a/b")
except Exception as e:  # noqa: BLE001
    chk("AC-2 add_recent_model behavior", False, f"{type(e).__name__}: {e}")

# ---- AC-3: search box offers "Use this model" when the query is a model ref ----
rms = re.search(r"function renderModelSuggest\(\)\s*\{.*?\n\}", app_js, re.S)
chk("AC-3 renderModelSuggest offers a Use-this-model action for a model ref",
    rms is not None and "looksLikeModelRef" in rms.group(0) and "data-usemodel" in rms.group(0))
chk("AC-3b the Use chip is wired to addUserModel",
    "btn.dataset.usemodel" in app_js and "addUserModel(" in app_js)

# ---- AC-4: dedicated "+ add model" input exists + wired ----
chk("AC-4 dedicated add-model input in index.html",
    'id="addmodelinput"' in index_html and 'id="addmodelbtn"' in index_html)
chk("AC-4b add-model input wired to addUserModel",
    '$("addmodelbtn")' in app_js and 'addUserModel(el.value)' in app_js)

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
