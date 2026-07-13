#!/usr/bin/env python3
"""P1 acceptance harness: schema-driven fal adapter. Exit 0 = GREEN. --live runs AC-9."""
import json, os, re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WEBUI = ROOT / "webui"
RESULTS = []

def check(name, fn):
    try:
        fn(); RESULTS.append((name, True, ""))
    except Exception as e:
        RESULTS.append((name, False, f"{type(e).__name__}: {e}"))

def ac1():
    import providers
    from providers.base import Provider
    reg = providers.registry()
    assert "fal" in reg, f"fal not registered: {list(reg)}"
    fal = reg["fal"]
    for m in ("list_models", "form_spec", "submit"):
        assert callable(getattr(fal, m, None)), f"fal missing {m}"

def ac2():
    import providers
    fal = providers.registry()["fal"]
    models = fal.list_models()
    assert len(models) >= 100, f"only {len(models)} models"
    for m in models[:20]:
        assert m["id"] and m["label"] and m["kind"] in ("image", "video"), m

def ac3():
    import providers
    spec = providers.registry()["fal"].form_spec("fal-ai/flux-2/turbo")
    assert isinstance(spec, list) and spec, "empty spec"
    widgets = {f["widget"] for f in spec}
    assert widgets <= {"select", "slider", "number", "toggle", "text", "loras", "image"}, widgets
    names = {f["name"] for f in spec}
    assert "image_size" in names and "num_images" in names, names
    imgsize = next(f for f in spec if f["name"] == "image_size")
    assert imgsize["widget"] == "select" and "square" in imgsize.get("enum", []) and len(imgsize["enum"]) >= 3, imgsize

def ac4():
    import schema
    fields = schema.props_to_formspec({
        "mode": {"type": "string", "enum": ["a", "b"]},
        "flag": {"type": "boolean", "default": True},
        "steps": {"type": "integer", "minimum": 1, "maximum": 50, "default": 8},
        "count": {"type": "integer", "default": 4},
        "label": {"type": "string"},
        "loras": {"type": "array", "items": {}},
        "image_url": {"type": "string"},
    }, required=[])
    by = {f["name"]: f["widget"] for f in fields}
    assert by["mode"] == "select" and by["flag"] == "toggle" and by["steps"] == "slider"
    assert by["count"] == "number" and by["label"] == "text"
    assert by["loras"] == "loras" and by["image_url"] == "image", by

def ac5():
    import providers
    fal = providers.registry()["fal"]
    lora_spec = fal.form_spec("fal-ai/flux-2/lora")
    turbo_spec = fal.form_spec("fal-ai/flux-2/turbo")
    assert any(f["widget"] == "loras" for f in lora_spec), "lora model missing loras field"
    assert not any(f["widget"] == "loras" for f in turbo_spec), "turbo wrongly has loras field"

def ac6():
    import bridge
    api = bridge.Api(start_server=False)
    for m in ("catalog", "form_spec", "generate"):
        assert callable(getattr(api, m, None)), f"bridge missing {m}"
    cat = api.catalog("fal", "image")
    assert cat and all(c["kind"] == "image" for c in cat), "catalog fal/image bad"
    spec = api.form_spec("fal-ai/flux-2/turbo")
    assert isinstance(spec, list) and spec, "bridge form_spec empty"

def ac7():
    js = (WEBUI / "form.js").read_text(encoding="utf-8")
    assert "renderForm" in js and "collectParams" in js, "form.js missing fns"
    r = subprocess.run(["node", str(WEBUI / "form.js")], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"form.js self-check failed: {r.stderr[-300:] or r.stdout[-300:]}"

def ac8():
    r = subprocess.run([sys.executable, str(ROOT / "app_web.py"), "--smoke"],
                       capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    assert r.returncode == 0 and "SMOKE OK" in r.stdout, f"rc={r.returncode} {r.stdout[-200:]}{r.stderr[-200:]}"

def ac9_live():
    import providers, time, pathlib as pl
    fal = providers.registry()["fal"]
    t0 = time.time()
    out = fal.submit("fal-ai/flux-2/turbo",
                     {"prompt": "a single green leaf on white", "num_images": 1,
                      "image_size": "square", "output_format": "jpeg"})
    assert out.get("files"), f"no files: {out}"
    p = pl.Path(out["files"][0])
    assert p.exists() and p.stat().st_mtime >= t0 - 5, "file not landed"
    assert p.suffix.lower() in (".jpg", ".jpeg"), f"output_format=jpeg not honored: {p.name}"

def main():
    live = "--live" in sys.argv
    for n, f in [("AC-1 provider iface", ac1), ("AC-2 fal live catalog", ac2),
                 ("AC-3 live form_spec", ac3), ("AC-4 widget mapping", ac4),
                 ("AC-5 lora conditionality", ac5), ("AC-6 bridge facade", ac6),
                 ("AC-7 form.js", ac7), ("AC-8 smoke", ac8)]:
        check(n, f)
    if live:
        check("AC-9 LIVE fal gen", ac9_live)
    w = max(len(n) for n, *_ in RESULTS)
    ok = True
    for n, p, e in RESULTS:
        print(f"{n:<{w}}  {'PASS' if p else 'FAIL'}  {e}"); ok &= p
    print(f"\nOVERALL: {'GREEN' if ok else 'RED'}" + ("" if live else "  (AC-9 live not run)"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
