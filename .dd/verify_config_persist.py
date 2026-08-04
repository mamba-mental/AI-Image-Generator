"""Recent-models persistence: the app's save must MERGE recent_models_* with disk so an external
edit / second instance / config script never clobbers added models.
Run: python .dd/verify_config_persist.py
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point config_path() at a throwaway file (VOID_CONFIG override) — never touch the real config.
tmp = Path(tempfile.gettempdir()) / "omni_cfgtest.json"
os.environ["VOID_CONFIG"] = str(tmp)
from bridge import Api  # noqa: E402
import engine.config as ec  # noqa: E402

results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def bind(fake):
    fake._save_config = types.MethodType(Api._save_config, fake)
    fake.add_recent_model = types.MethodType(Api.add_recent_model, fake)
    return fake


# ---- the clobber scenario: in-memory config is STALE vs a newer disk write ----
tmp.write_text(json.dumps({"recent_models_replicate": ["disk/one", "disk/two"]}), encoding="utf-8")
fake = bind(types.SimpleNamespace(config={"recent_models_replicate": ["mem/a"]}))
fake._save_config()   # must UNION mem + disk, not overwrite
disk = json.loads(tmp.read_text(encoding="utf-8"))
chk("_save_config unions in-memory + disk (no clobber)",
    set(disk["recent_models_replicate"]) == {"mem/a", "disk/one", "disk/two"}, str(disk["recent_models_replicate"]))

# ---- add_recent_model persists to disk (front) + keeps the rest ----
r = fake.add_recent_model("replicate", "new/model")
disk2 = json.loads(tmp.read_text(encoding="utf-8"))
chk("add_recent_model persists the new model to disk", "new/model" in disk2["recent_models_replicate"])
chk("add_recent_model keeps the existing recents", "disk/one" in disk2["recent_models_replicate"] and "mem/a" in disk2["recent_models_replicate"])
chk("returned models list has the new model at front", r["ok"] and r["models"][0] == "new/model", str(r.get("models", [])[:3]))

# ---- a SECOND process adds a model to disk; our next save must NOT drop it ----
d3 = json.loads(tmp.read_text(encoding="utf-8"))
d3["recent_models_replicate"].append("other-instance/model")
tmp.write_text(json.dumps(d3), encoding="utf-8")
fake.add_recent_model("replicate", "another/one")     # triggers a merge-save
disk4 = json.loads(tmp.read_text(encoding="utf-8"))
chk("a concurrent instance's model survives our save",
    "other-instance/model" in disk4["recent_models_replicate"] and "another/one" in disk4["recent_models_replicate"])

try:
    tmp.unlink()
except Exception:
    pass
fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
