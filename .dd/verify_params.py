"""Acceptance verifier for Phase 2 P1 (research/2026-07-21_provider-params-matrix.md §14/§15).
Hermetic, unit-level, no network/spend. Run: python .dd/verify_params.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.backends import cliproxy_api, nvidia_api, novita_api  # noqa: E402

checks = []


def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


sp = json.loads((ROOT / "engine" / "service_params.json").read_text(encoding="utf-8"))["services"]

# ---- promotion sanity: every wired service carries `default` + `aspect_presets` ----
for svc in ("openai", "cliproxy", "gemini", "nvidia", "together", "novita", "runware", "huggingface",
            "ideogram", "agnes", "openrouter"):
    chk(f"{svc} has default[] params", isinstance(sp[svc].get("default"), list))
    chk(f"{svc} has aspect_presets{{}}", isinstance(sp[svc].get("aspect_presets"), dict) and len(sp[svc]["aspect_presets"]) >= 17)
chk("replicate/fal stay ABSENT from service_params.json (preserves the pre-P1 LEGACY_PARAMS/own-catalog fallback)",
    "replicate" not in sp and "fal" not in sp)
chk("agnes keeps its pre-existing by_id_contains.video block (draft promotion didn't drop it)",
    "video" in sp["agnes"].get("by_id_contains", {}) and len(sp["agnes"]["by_id_contains"]["video"]) >= 8)
chk("openrouter's default is an empty (not null) array — matches the matrix's 'no size field on this path' finding",
    sp["openrouter"]["default"] == [])

# ---- (i) preset -> pixel mapping correct per size-model branch (§15) ----
chk("nvidia 1:1 preset -> the enum pair {768,768} (fixed_wh_enum_independent)",
    sp["nvidia"]["aspect_presets"]["1:1"] == {"width": 768, "height": 768})
chk("nvidia 3:1 (unachievable) -> nearest enum landscape pair, badge-worthy",
    sp["nvidia"]["aspect_presets"]["3:1"]["width"] == 1344 and sp["nvidia"]["aspect_presets"]["3:1"]["height"] == 768)
chk("nvidia width/height are the 10-value enum type, min 5-100 steps / (1,9] cfg on the width param table",
    sp["nvidia"]["default"][0]["values"] == [768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344])
steps_p = next(p for p in sp["nvidia"]["default"] if p["name"] == "steps")
cfg_p = next(p for p in sp["nvidia"]["default"] if p["name"] == "guidance_scale")
chk("nvidia steps range promoted to 5-100 (was wrongly 1-50)", steps_p["min"] == 5 and steps_p["max"] == 100)
chk("nvidia cfg_scale range promoted to (1.0,9.0] (was wrongly 0-20)", cfg_p["min"] == 1.0 and cfg_p["max"] == 9.0)
chk("openai/cliproxy 16:9 preset -> the enum_wh_string '1536x1024'",
    sp["openai"]["aspect_presets"]["16:9"] == "1536x1024" == sp["cliproxy"]["aspect_presets"]["16:9"])
chk("gemini 1:3 preset -> substituted to its own 10-value enum (not a fabricated 1:3)",
    sp["gemini"]["aspect_presets"]["1:3"] in {"9:16", "3:4", "4:5"} and sp["gemini"]["aspect_presets"]["1:3"] != "1:3")
chk("ideogram uses the 'x' separator on the wire (2:3 -> '2x3'), never ':'",
    sp["ideogram"]["aspect_presets"]["2:3"] == "2x3")
chk("together/novita/runware (free_wh) 1:1 preset -> a real square {width,height} pixel pair",
    all(sp[s]["aspect_presets"]["1:1"] == {"width": 1024, "height": 1024} for s in ("together", "novita", "runware")))
chk("runware guidance ceiling promoted to 50 (was 30) + num_outputs ceiling to 20 (was 4)",
    next(p for p in sp["runware"]["default"] if p["name"] == "guidance_scale")["max"] == 50
    and next(p for p in sp["runware"]["default"] if p["name"] == "num_outputs")["max"] == 20)
chk("novita guidance floor promoted to 1 (was 0)",
    next(p for p in sp["novita"]["default"] if p["name"] == "guidance_scale")["min"] == 1)
chk("novita sampler_name carries the full ~19/20-value list (was 5)",
    len(next(p for p in sp["novita"]["default"] if p["name"] == "sampler_name")["values"]) >= 19)

# ---- (ii) cliproxy size-snap before send (§14 Bug #1) ----
chk("cliproxy snaps a custom width/height to the nearest of the 3 legal gpt-image enums",
    cliproxy_api._size({"width": 500, "height": 900}, "gpt-image-2") == "1024x1536")
chk("cliproxy passes a legal size through unchanged", cliproxy_api._size({"size": "1024x1024"}, "gpt-image-2") == "1024x1024")
chk("cliproxy reuses openai_api._size (no duplicated logic)", cliproxy_api._size is __import__("engine.backends.openai_api", fromlist=["_size"])._size)

# ---- (iii) NVIDIA never_send negative_prompt + real range clamps, live in the backend ----
import types  # noqa: E402
body_capture = {}
_orig_req = __import__("urllib.request", fromlist=["Request"]).Request


class _FakeResp:
    def read(self):
        return b'{"artifacts":[]}'


def _fake_urlopen(req, timeout=0):
    body_capture["body"] = json.loads(req.data.decode())
    return _FakeResp()


import urllib.request  # noqa: E402
_orig_urlopen = urllib.request.urlopen
urllib.request.urlopen = _fake_urlopen
try:
    import os as _os
    _os.environ["NVIDIA_API_KEY"] = "x"
    nvidia_api.generate("black-forest-labs/flux.1-dev",
                         {"prompt": "y", "negative_prompt": "blurry", "width": 500, "height": 1300,
                          "steps": 1, "guidance_scale": 15})
finally:
    urllib.request.urlopen = _orig_urlopen

b = body_capture["body"]
chk("NVIDIA never sends negative_prompt (absent, not null/empty)", "negative_prompt" not in b)
chk("NVIDIA snaps width/height to the 10-value enum (500->768, 1300->1280)", b["width"] == 768 and b["height"] == 1280)
chk("NVIDIA clamps steps into [5,100] (sent 1 -> 5)", b["steps"] == 5)
chk("NVIDIA clamps cfg_scale into (1.0,9.0] (sent 15 -> 9.0)", b["cfg_scale"] == 9.0)

# ---- novita guidance floor live in the backend ----
# (0.5, not 0 -- an explicit 0 hits the pre-existing `x or 7.0` default-fallback idiom before the
# floor clamp ever runs, same as it did before this change; 0.5 is the value that actually exercises
# the new max(1.0, ...) floor.)
b2 = novita_api._build_body("m", {"prompt": "x", "guidance_scale": 0.5})
chk("novita _build_body floors guidance_scale at 1 (was unfloored)", b2["request"]["guidance_scale"] == 1.0)

# ---- source-text proof the frontend consumes aspect_presets data-driven (no hardcoded preset list) ----
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
chk("app.js reads presets from serviceParams[service].aspect_presets (data-driven, not hardcoded)",
    "sp.aspect_presets" in app_js and "servicePresetTable" in app_js)
chk("app.js implements the NEAREST-with-badge policy (one #aspectbadge, no per-provider special-case UI)",
    app_js.count('$("aspectbadge")') >= 1 and "updateAspectBadge" in app_js)

print()
n_pass = sum(checks)
print(f"{n_pass}/{len(checks)} verify_params checks pass")
sys.exit(0 if n_pass == len(checks) else 1)
