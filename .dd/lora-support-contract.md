# dd-router contract — LoRA generalization + Civitai (Phase 4)

**Slug:** lora-support
**Repo:** mamba-mental/AI-Image-Generator
**Verify:** `.dd/verify_lora.py` (python; per-provider request-shape assertions, table-driven from `research/2026-07-20_lora-syntax-per-provider.md`)

## Problem
LoRA was HF + Replicate only, single-LoRA, and fal was excluded. PRIME wants multi-LoRA across providers + Civitai browse-and-add, with each provider's **exact** documented syntax (wrong syntax silently fails). The bridge's `enabled_loras` injection is already provider-neutral; the work is managers + correct per-backend translation + UI + Civitai.

## Acceptance criteria (RED → GREEN)

- **AC-1 — Managers for all LoRA-capable services.** `Api.lora_managers` has `fal, together, runware, novita, huggingface, replicate`; `get_state()["loras"]` exposes all six; each persists to its own `recent_loras_<svc>` config key.
- **AC-2 — fal (`loras:[{path,scale}]`, gated).** `fal_api._build_args` translates `enabled_loras` → `loras:[{path,scale}]` ONLY on LoRA-capable endpoints (flux-lora / flux-general / *-lora-gallery / */lora); a base model (flux/dev, flux/schnell) gets **no** `loras`.
- **AC-3 — Replicate (per-model, multi).** `_build_input` for a `*multi-lora*` model → `hf_loras:[str]` + `lora_scales:[num]`; otherwise → `lora_weights` + `extra_lora` (+ `*_scale`), first 2.
- **AC-4 — Together (`image_loras:[{path,scale}]`, max 2, gated).** Sent only on `FLUX.1-dev-lora` / `FLUX.2-dev`; a non-LoRA model gets none.
- **AC-5 — Runware / Novita exact shapes.** Runware `lora:[{model,weight}]`; Novita `request.loras:[{model_name,strength}]`.
- **AC-6 — HF stacks weights.** `enabled_loras` → `lora_weights:[url,…]` (list) + a single `lora_scale`.
- **AC-7 — Civitai ref conversion + add.** `Api.civitai_ref_for("runware",m,v)=="civitai:m@v"`; other services → `https://civitai.com/api/download/models/<v>`. `civitai_add_lora` adds that ref to the active manager; **novita is rejected** (its LoRAs are a proprietary catalog, not CivitAI). `civitai_search` returns `{ok, items:[{modelId,versionId,name,baseModel,nsfw,thumb,downloadUrl,air}]}` (live-gated; structural shape asserted).
- **AC-8 — UI gate widened.** `renderLoras` shows the panel for all six services; for `fal` it is gated on the selected model being LoRA-capable (`falModelSupportsLora`).

## Verify plan
`.dd/verify_lora.py`: builds the request via each backend's pure builder (`_build_args`, `_build_input`, `_build_task`, `_build_body`) or a urlopen-capture (together) and asserts the exact key names/shape; multi-LoRA stacking (2 LoRAs); `civitai_ref_for`/`civitai_add_lora` on a real `Api()` with `_persist` stubbed; AC-6/AC-8 by source reflection. Prints `[PASS]/[FAIL]`; exit non-zero on any fail.
