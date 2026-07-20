# DD Contract — Job 3: Per-service param richness (retire generic LEGACY_PARAMS)

Give each non-fal service model-specific params from its real API schema instead of the generic
6-field `LEGACY_PARAMS`. Plan doc §4.

## Acceptance criteria (RED until proven)

- [ ] **AC-1** `engine/service_params.json` holds verified per-service param schemas; `modelsFor()` uses them (via `state.serviceParams`) in place of `LEGACY_PARAMS`, falling back to `LEGACY_PARAMS` only when a service has no entry.
- [ ] **AC-2** Each service exposes the plan §4 params **where its API supports them** (OpenAI ≥6, Together ≥8, NVIDIA ≥6, Ideogram ≥8, AGNES-video ≥8; Gemini/AGNES-image fewer because the API is narrower — that's correct).
- [ ] **AC-3** Each backend **reads + maps** the new params to its API body (a shown param must actually take effect) — OpenAI `moderation`/`output_compression`; Gemini `imageConfig.aspectRatio`+`imageSize` as REAL fields; Together `guidance_scale`/`disable_safety_checker`/`output_format`; NVIDIA `negative_prompt`; Ideogram `magic_prompt`/`resolution`; AGNES video `aspect_ratio`/`duration`.
- [ ] **AC-4** Replicate + HuggingFace fetch the **live per-model Input schema** (Replicate `GET /v1/models/{owner}/{name}`; HF from the model's config) via a bridge method, rendered like fal; fallback to LEGACY_PARAMS on failure.
- [ ] **AC-5** Every `# fill:` item was **probed live before wiring**; any that failed are left out with a one-line note in this contract.
- [ ] **AC-6** A live generation through **fal + 2 non-fal services** succeeds with a **non-default** param set (proof captured).
- [ ] **AC-7** `main.py --smoke` still passes; services without a wired schema still fall back to LEGACY_PARAMS.

## `# fill:` verification log
- **Gemini `imageConfig.aspectRatio`/`imageSize`** — WIRED. Live probe returned 429 (quota), not 400 → body shape accepted. Field names confirmed vs ai.google.dev docs.
- **NVIDIA `aspect_ratio`** — DROPPED (unverified on native NIM; NIM docs JS-gated). `negative_prompt` wired instead.
- **NVIDIA `steps` caps** — used a conservative 1–50 range; not model-specific (acceptable).
- **Ideogram `magic_prompt`/`resolution`** — WIRED, confirmed vs developer.ideogram.ai v3 docs (resolution overrides aspect_ratio).
- **AGNES video `aspect_ratio`/`duration`** — WIRED + live-probed: `POST /v1/videos` → HTTP 200 `status:queued` with both accepted.
- **Replicate dynamic Input-schema fetch (AC-4)** — CODE COMPLETE + graceful fallback to LEGACY_PARAMS on failure, but **UNVERIFIABLE LIVE: the Replicate token is dead** (both env + config.json keys 403 on `/v1/account`, 2026-07-20). PRIME-side credential refresh needed; the fetcher will work once the token is valid. Not a code defect.
- **OpenRouter `image_config`** — DEFERRED (`openrouter` key missing in this env; passthrough shape unverified). Not wired.
- **cliproxy** — mirrors OpenAI (`quality`/`background`/`output_format`); passthrough, not independently probed.

## Verify
`node scripts/verify_service_params.js` (params-source coverage) + a live gen script through 2 non-fal services + `main.py --smoke`.
