#!/usr/bin/env python3
"""Binary acceptance harness: void-web-powerstudio contract. Exit 0 = GREEN, 1 = RED.
Usage: python .dd/verify_void_web.py [--live]   (--live runs AC-8, one real fal generation)
"""
import json, os, re, subprocess, sys, tempfile, time, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WEBUI = ROOT / "webui"
RESULTS = []

def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as e:
        RESULTS.append((name, False, f"{type(e).__name__}: {e}"))

def read_index():
    p = WEBUI / "index.html"
    assert p.exists(), "webui/index.html missing"
    return p.read_text(encoding="utf-8")

# ---------- AC-1 smoke boot ----------
def ac1():
    r = subprocess.run([sys.executable, str(ROOT / "app_web.py"), "--smoke"],
                       capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    assert r.returncode == 0, f"rc={r.returncode} err={r.stderr[-400:]}"
    assert "SMOKE OK" in r.stdout, f"stdout={r.stdout[-400:]}"

# ---------- AC-2 UI integrity ----------
def ac2():
    html = read_index()
    for tab in ("Image", "Video", "Virality"):
        assert re.search(rf'data-tab="{tab.lower()}"', html), f"missing tab {tab}"
    for dis in ("video", "virality"):
        m = re.search(rf'data-tab="{dis}"[^>]*>', html)
        assert m and "data-disabled" in m.group(0), f"{dis} tab not marked disabled"
        assert 'data-reason="' in m.group(0), f"{dis} tab missing data-reason"
    chips = set(re.findall(r'data-provider="([a-z]+)"', html))
    assert chips == {"fal", "replicate", "hf", "gemini"}, f"provider chips = {chips}"
    for f in WEBUI.rglob("*"):
        if f.is_file() and f.suffix in (".html", ".js", ".css", ".json"):
            body = f.read_text(encoding="utf-8", errors="ignore")
            # Naming Higgsfield in a disabled-tab reason is truthful; forbid it as a live path only.
            scrub = re.sub(r'data-reason="[^"]*"', "", body).lower()
            assert "higgsfield" not in scrub, f"higgsfield routing ref in {f.name}"

# ---------- AC-3 no dead buttons ----------
def ac3():
    import bridge
    html = read_index()
    apis = set(re.findall(r'data-api="([a-zA-Z_]+)"', html))
    assert apis, "no data-api attributes found in index.html"
    for name in apis:
        assert callable(getattr(bridge.Api, name, None)), f"dead button: data-api={name} has no Api.{name}"

# ---------- AC-4 generate dry-run spec (SBE example) ----------
def ac4():
    import bridge
    api = bridge.Api(start_server=False)
    spec = api.generate(prompt="test drone", model="fal-ai/flux-2/turbo", batch=2,
                        seed=7, dims="3:4", dry_run=True)
    assert "queue.fal.run" in spec["url"] and "flux-2/turbo" in spec["url"], spec["url"]
    assert spec["headers"]["Authorization"].startswith("Key "), "auth header"
    p = spec["payload"]
    assert p["prompt"] == "test drone" and p["num_images"] == 2 and p["seed"] == 7
    assert p["image_size"] == "portrait_3_4", p.get("image_size")

# ---------- AC-5 LoRA roundtrip ----------
def ac5():
    import bridge
    with tempfile.TemporaryDirectory() as td:
        api = bridge.Api(start_server=False, state_dir=td)
        api.lora_add("https://civitai.example/void-test.safetensors", 0.85)
        api.lora_set_scale(0, 0.6)
        api.lora_toggle(0)
        loras = api.lora_list()
        assert loras[0]["scale"] == 0.6 and loras[0]["enabled"] is False, loras
        api2 = bridge.Api(start_server=False, state_dir=td)
        assert api2.lora_list()[0]["scale"] == 0.6, "LoRA state did not persist"

# ---------- AC-6 gallery + media server ----------
def ac6():
    import bridge
    api = bridge.Api(start_server=True, media_port=0)
    try:
        items = api.gallery(limit=8)
        assert items, "gallery empty"
        for it in items:
            assert it["url"].startswith("http://127.0.0.1:"), it["url"]
        req = urllib.request.urlopen(items[0]["url"], timeout=10)
        assert req.status == 200 and req.headers.get_content_type().startswith("image/"), \
            f"{req.status} {req.headers.get_content_type()}"
    finally:
        api.shutdown()

# ---------- AC-7 prompt history persistence ----------
def ac7():
    import bridge
    with tempfile.TemporaryDirectory() as td:
        api = bridge.Api(start_server=False, state_dir=td)
        api.history_add("neon fox in rain")
        api2 = bridge.Api(start_server=False, state_dir=td)
        assert "neon fox in rain" in api2.history_list(), api2.history_list()

# ---------- AC-8 LIVE story gate ----------
def ac8_live():
    import bridge
    api = bridge.Api(start_server=True, media_port=0)
    try:
        t0 = time.time()
        out = api.generate(prompt="tiny chrome orb on black velvet, macro, rim light",
                           model="fal-ai/flux-2/turbo", batch=1, seed=None, dims="1:1",
                           dry_run=False)
        assert out["files"], f"no files returned: {out}"
        newest = pathlib.Path(out["files"][0])
        assert newest.exists() and newest.stat().st_mtime >= t0 - 5, "file not landed"
        first = api.gallery(limit=1)[0]
        assert newest.name in first["url"], f"gallery[0]={first['url']}"
    finally:
        api.shutdown()

def main():
    live = "--live" in sys.argv
    check("AC-1 smoke boot", ac1)
    check("AC-2 UI integrity", ac2)
    check("AC-3 no dead buttons", ac3)
    check("AC-4 generate dry-run spec", ac4)
    check("AC-5 LoRA roundtrip", ac5)
    check("AC-6 gallery + media server", ac6)
    check("AC-7 prompt history", ac7)
    if live:
        check("AC-8 LIVE fal story gate", ac8_live)
    width = max(len(n) for n, *_ in RESULTS)
    ok = True
    for name, passed, err in RESULTS:
        print(f"{name:<{width}}  {'PASS' if passed else 'FAIL'}  {err}")
        ok &= passed
    print(f"\nOVERALL: {'GREEN' if ok else 'RED'}" + ("" if live else "  (AC-8 live gate not run — use --live)"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
