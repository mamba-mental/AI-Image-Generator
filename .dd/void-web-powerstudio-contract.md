# *DD Contract: Void Power-User Studio web UI (Direction 4 ship)

Build type: Web app / frontend feature + backend bridge (spans two rows — methods unioned)
Methods (>=3): story-tdd (outer) · sbe (spec/examples) · tdd (inner)
Stack + tools: Python 3.13 -> pytest (inner + SBE fixtures) · executable acceptance harness `.dd/verify_void_web.py` (binary PASS/FAIL) · live story gate via real fal REST call
Approved design: `C:\AI CoWork\dashboards\void-ui-mock-power-user-studio.html` (PRIME picked Direction 4, said "ship")

## Acceptance (the done-gate)
- AC-1 Smoke boot: `python app_web.py --smoke` exits 0 and prints `SMOKE OK` (bridge constructs, catalog loads, media server binds, no window). -> verify_void_web.py::ac1 [RED]
- AC-2 UI integrity: `webui/index.html` exists; has Image/Video/Virality tabs; Virality AND Video tabs carry `data-disabled` + `data-reason` (Virality: Higgsfield retired; Video: v2); provider chips are EXACTLY the wired set {fal, replicate, hf, gemini}; no case-insensitive "higgsfield" anywhere in webui/. -> ::ac2 [RED]
- AC-3 No dead buttons: every `data-api="<name>"` in webui/index.html resolves to a public method on bridge.Api. -> ::ac3 [RED]
- AC-4 Generate spec (dry-run, no network): Api.generate(dry_run=True) returns request spec {url contains queue.fal.run + model path, headers Authorization startswith "Key ", payload has prompt/image_size/seed/num_images, loras list included when stack enabled}. -> ::ac4 [RED]
- AC-5 LoRA stack: add/toggle/set_scale/list roundtrip through loramanager persists to config. -> ::ac5 [RED]
- AC-6 Gallery + media server: Api.gallery(limit=8) returns newest media; every returned URL is http://127.0.0.1:<port>/... and GETs 200 with image/* content-type (WebView2 cannot load file:// media from a file:// page — localhost server is load-bearing). -> ::ac6 [RED]
- AC-7 Prompt history: Api.history_add + history_list persists across Api re-instantiation (config/prompt_history.json). -> ::ac7 [RED]
- AC-8 LIVE story gate (story-tdd outer): run `.dd/verify_void_web.py --live` once at the end — real fal generation (flux.2 turbo tier, ~$0.005) from the bridge lands a new file in generated_media/ and appears first in Api.gallery(). -> ::ac8 [RED, run-once]

## Examples / spec (SBE)
- generate dry-run example: prompt="test drone", model="fal-ai/flux-2-turbo", batch=2, seed=7, dims="3:4", loras=[{path,scale 0.85,on}] -> spec.payload == {prompt:"test drone", num_images:2, seed:7, image_size:"portrait_4_3", loras:[...]} [unmet]
- gallery example: newest file in generated_images/ is item[0] with url http://127.0.0.1:PORT/gi/<name> [unmet]

## Inner cycle (TDD)
- first failing unit: verify_void_web.py::ac4 (generate dry-run routes to fal) [RED]

## Non-goals (guard scope-creep)
- Together backend (chip omitted v1 — key exists but unwired; no dead chip)
- Virality Predictor port (Higgsfield-only, retired) — disabled tab with reason only
- Video generation wiring (v2) — disabled tab with reason only
- Deleting/altering Tkinter app.py (stays as fallback entry)
- Touching pre-existing uncommitted changes on branch ui-enhancements-replicate (not ours)

Status: GREEN — all 8 ACs PASS (incl. AC-8 live fal generation 2026-07-12). Build shipped.
