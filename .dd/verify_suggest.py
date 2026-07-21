"""Acceptance verifier for E1 — the in-app Ask-AI model suggestion box (Spec B §4 AC-4.2/4.3/4.4),
plus an E2 sanity check that Novita's Model APIs are actually routed (not just seeded).

Hermetic: monkeypatches urllib.request.urlopen so no real cliproxy call fires. Asserts:
  (i)   the request to cliproxy carries ONLY accessible models in the system prompt
  (ii)  an answer naming a non-accessible model is filtered out before it reaches the caller
  (iii) the rendered picks reuse the SAME .msuggest-chip click-apply path as the instant-filter
        suggestions — source-text proof, matching the verify_pD.py convention for asserting
        app.js logic (app.js has no DOM outside a live pywebview window to drive headlessly)

Run: python .dd/verify_suggest.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bridge  # noqa: E402

checks = []


def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


# ---- hermetic Api stub (bypass heavy __init__, per verify_library.py's convention) ----
api = bridge.Api.__new__(bridge.Api)
api.config = {"output_directory": str(ROOT), "ui_content_mode": "safe"}
api.keys_status = {"fal": True, "novita": True, "openai": False, "nvidia": False, "replicate": False,
                    "huggingface": False, "gemini": False, "openrouter": False, "together": False,
                    "runware": False, "cliproxy": True, "ideogram": False, "agnes": False}

# small fixture catalog — avoids loading the real ~1.3k-row fal_models.json for this unit test
_orig_load_fal = bridge._load_fal_models
bridge._load_fal_models = lambda: [
    {"id": "fal-ai/flux/schnell", "label": "FLUX Schnell", "category": "text-to-image"},
    {"id": "fal-ai/flux/dev", "label": "FLUX Dev", "category": "text-to-image"},
]
_orig_recent = bridge.Api._recent_models_map
bridge.Api._recent_models_map = lambda self: {
    "novita": ["epicrealism_naturalSinRC1VAE_106430.safetensors"],
    "openai": ["gpt-image-2"],  # openai has NO key above -> must never reach the accessible set
}

accessible = api._accessible_models()
chk("AC-4.2 accessible set excludes un-keyed openai",
    not any(m["service"] == "openai" for m in accessible))
chk("AC-4.2 accessible set includes fal + novita checkpoints + novita Model APIs",
    any(m["service"] == "fal" for m in accessible)
    and any(m["id"] == "epicrealism_naturalSinRC1VAE_106430.safetensors" for m in accessible)
    and any(m["service"] == "novita" and m["id"] in bridge._load_novita_model_apis() for m in accessible))

# ---- (i) the cliproxy request carries ONLY accessible models in the system prompt ----
os.environ["CLIPROXY_API_KEY"] = '"testkey"'  # deliberately quote-wrapped -> exercises the strip guard
captured = {}


class _Resp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body


def _fake_urlopen(req, timeout=0):
    captured["req"] = req
    captured["payload"] = json.loads(req.data.decode())
    reply = ("Try fal-ai/flux/schnell · fal · fast + accessible. Also consider "
             "openai/gpt-image-nonexistent, which is not in your keys.")
    return _Resp(json.dumps({"choices": [{"message": {"content": reply}}]}).encode())


_orig_urlopen = urllib.request.urlopen
urllib.request.urlopen = _fake_urlopen
try:
    r = api.suggest_model("fast realistic photo")
finally:
    urllib.request.urlopen = _orig_urlopen

chk("quote-wrapped CLIPROXY_API_KEY stripped before use",
    captured["req"].headers.get("Authorization") == "Bearer testkey")
system_prompt = captured["payload"]["messages"][0]["content"]
chk("(i) system prompt lists every accessible id",
    all(m["id"] in system_prompt for m in accessible))
chk("(i) system prompt names NO un-keyed-provider id (openai's seed id absent)",
    "gpt-image-2" not in system_prompt)

# ---- (ii) a non-accessible model named in the reply is filtered out of picks ----
chk("suggest_model() returns ok:true", r.get("ok") is True)
chk("(ii) accessible pick present (fal-ai/flux/schnell)",
    any(p["id"] == "fal-ai/flux/schnell" for p in r.get("picks", [])))
chk("(ii) non-accessible id named in the reply text is NOT in picks",
    not any("gpt-image-nonexistent" in p["id"] for p in r.get("picks", [])))
chk("(ii) picks capped at 3", len(r.get("picks", [])) <= 3)

# ---- negative paths: no query / no key / no accessible models ----
chk("empty query -> ok:false", api.suggest_model("").get("ok") is False)
del os.environ["CLIPROXY_API_KEY"]
chk("no cliproxy key -> honest 'unreachable' error, not a crash",
    api.suggest_model("x").get("error", "").startswith("cliproxy unreachable"))
os.environ["CLIPROXY_API_KEY"] = "testkey"
api.keys_status = {k: False for k in api.keys_status}
chk("no accessible models -> honest error",
    "no accessible models" in api.suggest_model("x").get("error", ""))

bridge._load_fal_models = _orig_load_fal
bridge.Api._recent_models_map = _orig_recent

# ---- (iii) click-apply reuses the SAME listener as the instant-filter suggestions (source proof) ----
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
chk("(iii) askAI() renders picks as .msuggest-chip (identical markup to the instant-filter chips)",
    app_js.count('class="msuggest-chip" data-svc="${m.service}" data-id="${encodeURIComponent(m.id)}"') >= 2)
chk("(iii) exactly ONE #modelsuggest click listener drives click-apply for BOTH sources",
    app_js.count('$("modelsuggest").addEventListener("click"') == 1
    and "state.service = svc; state.inputFiles = {}; renderService(); refreshBalance();" in app_js
    and "state.model = id;" in app_js)
chk("(iii) Ask-AI button + Enter both fire the same askAI() reply path",
    '$("askaibtn") && $("askaibtn").addEventListener("click", askAI)' in app_js
    and 'e.key === "Enter"' in app_js and "askAI()" in app_js)

# ---- E2 sanity — the Model APIs are actually ROUTED, not just seeded for the dropdown ----
from engine.backends import novita_api  # noqa: E402
chk("E2 novita_model_apis() == MODEL_APIS keys",
    novita_api.novita_model_apis() == sorted(novita_api.MODEL_APIS.keys()))
novita_src = (ROOT / "engine" / "backends" / "novita_api.py").read_text(encoding="utf-8")
chk("E2 generate() routes a Model-API id to _generate_model_api before the legacy checkpoint path",
    "if model_id in MODEL_APIS:" in novita_src
    and novita_src.index("if model_id in MODEL_APIS:") < novita_src.index("body = _build_body(model_id, params)"))

print()
n_pass = sum(checks)
print(f"{n_pass}/{len(checks)} verify_suggest checks pass")
sys.exit(0 if n_pass == len(checks) else 1)
