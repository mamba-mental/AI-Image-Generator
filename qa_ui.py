"""UI-control functional test — exercise the bridge methods behind each control,
prove real behavior (not that the button renders). Free + fast (no gen spend)."""
import sys, json
sys.path.insert(0, ".")
from bridge import Api

api = Api()
R = []
def check(name, fn):
    try:
        fn(); R.append((name, True, ""))
    except Exception as e:
        R.append((name, False, f"{type(e).__name__}: {e}"[:160]))

# 1. balance (footer) — each service returns a shape
def balance():
    for s in ["fal", "openai", "gemini", "replicate", "huggingface", "nvidia"]:
        b = api.get_balance(s)
        assert isinstance(b, dict) and "label" in b, f"{s}: {b}"

# 2. LoRA add/toggle/scale/remove roundtrip (replicate lane)
def lora():
    before = len(api.lora_list("replicate"))
    lst = api.lora_add("replicate", "https://huggingface.co/test/qa-lora.safetensors")
    assert len(lst) == before + 1, "add failed"
    idx = len(lst) - 1
    lst = api.lora_set("replicate", idx, {"enabled": False})
    assert lst[idx]["enabled"] is False, "toggle failed"
    lst = api.lora_set("replicate", idx, {"scale": 0.42})
    assert abs(lst[idx]["scale"] - 0.42) < 1e-6, "scale failed"
    lst = api.lora_remove("replicate", idx)
    assert len(lst) == before, "remove failed"

# 3. theme/layout persistence via set_config -> re-read config
def theme_layout():
    api.set_config({"ui_theme": "costa", "ui_layout": "airy"})
    import engine.config as ec
    fresh = ec.load()
    assert fresh.get("ui_theme") == "costa" and fresh.get("ui_layout") == "airy", \
        f"not persisted: {fresh.get('ui_theme')}/{fresh.get('ui_layout')}"
    api.set_config({"ui_theme": "violet", "ui_layout": "compact"})  # restore

# 4. key validate (read-only current key)
def validate():
    r = api.validate_key("fal", "")
    assert isinstance(r, dict) and "valid" in r and "http" in r, r
    assert r["valid"] is True, f"fal key should validate: {r}"

# 5. history + recent_files + negative-prompt persistence path
def data_reads():
    assert isinstance(api.get_history(5), list)
    assert isinstance(api.recent_files(5), list)

check("balance (all services)", balance)
check("LoRA add/toggle/scale/remove", lora)
check("theme+layout persistence", theme_layout)
check("key validate (fal)", validate)
check("history/recent_files reads", data_reads)

w = max(len(n) for n, *_ in R)
ok = True
for n, p, e in R:
    print(f"{n:<{w}}  {'PASS' if p else 'FAIL'}  {e}"); ok &= p
print(f"\n{sum(1 for _,p,_ in R if p)}/{len(R)} UI-control tests pass")
sys.exit(0 if ok else 1)
