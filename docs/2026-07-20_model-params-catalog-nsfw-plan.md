# AI Studio Void — Full Model Params + FAL Catalog + Content-Mode Plan

**Date:** 2026-07-20 · **Status:** researched, awaiting build approval · **Grounding:** 4 parallel research agents (verified live)

Goal: replace the app's generic per-model config with **model-specific parameters** for every service in the dropdown, pull the **entire FAL catalog** (not the ~12/13-per-category subset), and add a **content-mode toggle** (Safe / Editorial / Fashion / NSFW) that both filters the model list and wires each model's real safety params — with per-param help.

---

## 1. Current state (what already exists — extend, don't rebuild)

- **Param UI is already schema-driven.** `web/app.js` `paramControl(p)` (~L337) renders one widget per `model.params[]` entry. Supported widget types today: `enum`→`<select>`, `bool`→checkbox, `int`/`float`→range slider (uses min/max/step) or number input when `optional:true`, else text. **No image/file param type** (file inputs handled separately via category `<src>-to-<dst>` + `renderInputPickers()`).
- **`collectParams(model)`** (~L377) re-reads every `[data-p]` element, coercing by `params[].type`. Flat `params` dict → `bridge.py Api.generate()` → `engine/jobs.py REGISTRY.start()` → `BACKENDS[service](model_id, params, progress, cancel_event)`.
- **Help exists but is hardcoded:** `PARAM_HELP` dict (~L267, 14 entries by param *name*) → `title=` + `ⓘ .phelp` span in `renderParams()` (~L354). `SAFETY_LABELS` map for `safety_tolerance` enum text. Params without a name match get no tooltip.
- **NSFW toggle scaffold already present:** `state.nsfw` (L44, persisted via `set_config({ui_nsfw})`), `renderNsfw(model)`/`syncSafetyControls()`/`nsfwNote()` (L396–417), `NSFW_POLICY` doc (L294). **Only activates for `state.service === "fal"`** and only flips `enable_safety_checker`/`safety_tolerance`. Does NOT filter the model list.
- **Catalog generator exists:** `scripts/build_fal_catalog.py` (named in `fal_models.json`'s `generator` field). `bridge.py _load_fal_models()` reads the JSON verbatim (no filter) — more fal models need only a data regen.
- **Non-fal services use generic `LEGACY_PARAMS`** (app.js L30): a fixed 6-entry array (`width, height, num_inference_steps, guidance_scale, num_outputs, seed`) — identical for every non-fal service/model regardless of what the API accepts. `modelsFor(service,category)` (L207) wraps each `recent_models[service]` id as `{id, label:id, category:"text-to-image", params:LEGACY_PARAMS}`.
- **Backend safety hook:** `fal_api.py _build_args()` (L63–67) reads `FLUX_DISABLE_SAFETY` env → injects `enable_safety_checker=False` when a model declares it and caller didn't. `config.py resolve_keys()` (L188-189) hardcodes `FLUX_DISABLE_SAFETY=true` + `FLUX_GO_FAST=true`.

**`fal_models.json` shape:** `{version, generated_at, generator, note, models:[{id,label,category,output,description,params:[{name,type,default?,values?,min?,max?,optional?}],thumb?}]}`. No `step`, `label`, or per-param `description`/help embedded. 174 models total (text-to-image **12**, text-to-video **13**, image-to-image 13, image-to-video 13, …).

---

## 2. FAL catalog API (VERIFIED live 2026-07-20)

- **Enumerate:** `GET https://fal.ai/api/models?categories=<slug>&page=<n>` — **browser User-Agent required** (Cloudflare 403s bare curl/urllib). This is the JSON behind `fal.ai/explore`.
  - Live totals: **text-to-image = 194**, **text-to-video = 125** (user's "88" is stale), **image-to-video = 187**, whole catalog = **1,396**.
  - `pageSize` is **ignored** server-side (fixed 40/page). Paginate `page=1..pages`, reading `pages`/`total` from page 1.
  - Item fields: `id, title, category, tags[], shortDescription, thumbnailUrl, thumbnailAnimatedUrl, licenseType, hostingType(serverless|proxy), deprecated, removed, billingMessage, pricingInfoOverride, ...`.
- **Per-model params:** `GET https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>` (browser UA) → `components.schemas.<Name>Input.properties` = every param's `type, title, description, enum, default, required[], x-fal (file constraints), maxLength`. `info.x-fal-metadata` also carries category/thumbnail/docs URL/about.
- **Pricing:** embedded in the catalog item — `billingMessage` (e.g. "$0.060 per image") + `pricingInfoOverride` (markdown, 52/194 t2i populated). No separate endpoint. `mcp__fal-ai__get_pricing` works as a cross-check.
- **NSFW/restriction metadata: DOES NOT EXIST in the API.** No `nsfw`/`safety`/`restricted`/`contentRating` field on any of 1,396 models; `?category=nsfw`/`?tag=nsfw`/`?q=` are silently ignored. `tags[]` = capability/style only; `"fashion"`/`"nsfw"` appear only as free-text tags/prose. **→ content filtering must be PARAM-BASED, not catalog-tag-based.**
- **MCP `list_models`** caps at 100/call, no offset/paging, mixed "image" bucket → insufficient for full pull. Use the raw REST endpoint.

---

## 3. Content-safety design (VERIFIED — param-based)

**Safety params by family** (live-fetched openapi):
| Family | Param | Type | Default | Most-permissive |
|---|---|---|---|---|
| flux/schnell·dev, flux-lora, sana, hidream-i1-full, sd-v3.5-large, seedream v4/v4.5 | `enable_safety_checker` | bool | `true` | `false` |
| recraft-v3 | `enable_safety_checker` | bool | **false** already | `false` |
| flux-pro/v1.1(+ultra) | `safety_tolerance` | enum "1"–"6" | "2" | "6" |
| flux-pro/v1.1-ultra | `raw` | bool | false | `true` (stylistic realism, not a gate) |
| flux-2-pro(+edit) | `enable_safety_checker` **+** `safety_tolerance` (enum "1"–"5") | bool+enum | true / "2" | false / "5" — dual-gated |
| nano-banana-pro/-2(+edit) | `safety_tolerance` | enum "1"–"6" | "4" | "6" |
| wan/LTX video family | `enable_safety_checker` **+** `enable_output_safety_checker` | bool | true | false for both |

- `sync_mode` is a delivery flag (not safety) — exclude. `safety_checker_version` not found.
- **Caveat (bake into help):** `enable_safety_checker=false` disables fal's post-hoc classifier only. Google/OpenAI-backed endpoints (nano-banana, gemini) enforce moderation **upstream** regardless — not fully controllable.
- **`FLUX_DISABLE_SAFETY` works** (injects `enable_safety_checker=false`); it does nothing for `safety_tolerance`-only models. **`FLUX_GO_FAST` is dead code** (set, never read) — remove it.

**4-mode design** (param-override profile + model-list filter predicate):
- **Safe** — `enable_safety_checker=true`, `safety_tolerance="2"`, `raw=false`. Filter: all models.
- **Editorial** — `enable_safety_checker=false`, `safety_tolerance="4"`, `raw=true` where present. Filter: models exposing any safety param.
- **Fashion** — Editorial + sort fashion/virtual-try-on-tagged models to top. Filter: same as Editorial.
- **NSFW** — `enable_safety_checker=false`, `safety_tolerance=<model-max clamped>` (6, or 5 on flux-2-pro), `enable_output_safety_checker=false`. Filter: **only** models declaring `enable_safety_checker` or `safety_tolerance`.
- **Filter flag:** tag each catalog model `supports_relaxed_safety: bool` = params include `enable_safety_checker`||`safety_tolerance`. Mode picker filters the dropdown by it for Editorial/Fashion/NSFW.
- **`applyContentMode(params, model, mode)`** must clamp `safety_tolerance` to each model's own enum max (families differ: "5" vs "6").
- Help copy (Safe/Editorial/Fashion/NSFW) drafted in the research; include the upstream-moderation caveat in Editorial+NSFW text.

---

## 4. Per-service param wiring (highest-value, from research tables)

Each non-fal service currently uses `LEGACY_PARAMS`. Wire model-specific params (source per service noted). `# fill:` = verify with a live probe before wiring.

- **OpenAI Images:** add `output_compression`(0-100, webp/jpeg), `moderation`(low/auto). (size/quality/background/output_format already wired.)
- **Gemini:** send REAL fields via `generationConfig.imageConfig.aspectRatio` (1:1…21:9) + `imageSize`(1K/2K/4K) — today w/h only appends a text hint. `# fill:` candidateCount for image; Imagen `predict` path is a different call than the current `generateContent`.
- **NVIDIA NIM:** add `negative_prompt`, `aspect_ratio`. `# fill:` per-model steps caps + whether aspect_ratio/samples/output_format exist on native NIM (docs JS-gated — probe live).
- **Replicate:** fetch each model's live `Input` schema: `GET /v1/models/{owner}/{name}` → `latest_version.openapi_schema.components.schemas.Input`; render it (like fal). Add output_format/output_quality/go_fast/megapixels/multi-lora.
- **HuggingFace:** add `scheduler` + `extra_body` passthrough (unlocks per-model params).
- **OpenRouter:** add `image_config.{aspect_ratio,image_size}` on the chat path; `# fill:` exact passthrough shape.
- **Together.ai:** add `guidance_scale`, `disable_safety_checker`, `output_format`, `image_url`(img2img).
- **cliproxy:** mirror OpenAI (`quality`/`background`) — it's a passthrough. `# fill:` upstream remapping.
- **Ideogram v3:** add `magic_prompt`(AUTO/ON/OFF), `resolution` presets, `style_codes`, `color_palette`. `# fill:` character/style-preset fields.
- **Ideogram web:** `character_reference_parents`/`product_reference_parents` (unwired). `# fill:` sampling_speed enum, seed.
- **AGNES:** video `aspect_ratio` + `duration`; image `quality`/`style`. (video: num_frames must be 8n+1 ≤441; w/h normalize to 480p/720p/1080p.)

Mechanism: give each service a real per-model param source (a `services_params.json` or per-backend schema fn) consumed by `modelsFor()` instead of `LEGACY_PARAMS`.

---

## 5. Build jobs (→ /loop-compose)

- **Job 1 — Full FAL catalog puller** (foundational). Extend `scripts/build_fal_catalog.py` to page every category from `fal.ai/api/models` + fetch each model's openapi schema → regenerate `fal_models.json` with full `params[]` (incl. `description`), `price`, and `supports_relaxed_safety`. Re-runnable, schema-cached, resumable, per-category cap flag. Acceptance: ≥194 t2i + ≥125 t2v, each with non-empty described params + the safety flag.
- **Job 2 — Content-mode toggle** (needs Job 1's flags). 4-mode selector across ALL services; `applyContentMode()` with per-model tolerance clamp; `supports_relaxed_safety` model-list filter; per-request override (not static env); remove dead `FLUX_GO_FAST`; help copy + upstream caveat.
- **Job 3 — Per-service param richness** (independent of Job 1). Replace `LEGACY_PARAMS` with per-service/per-model schemas per §4; Replicate/HF dynamic schema fetch; verify every `# fill:` with a live probe before wiring (leave unverified out with a note).
- **Job 4 — Schema-driven help + widgets** (needs 1+3's richer params). `renderParams()` prefers `p.description`; add image/file + resolution-preset widget types (`paramControl`+`collectParams` branches); content-mode explainer popover.
- **Job 5 — Integration verify.** App `--smoke` + a real gen per category through fal + 2 non-fal services; no regressions.

**Scope note:** the full pull is 1,396 models (194 t2i + 125 t2v + 187 i2v + …). Puller must cache schemas + resume; a per-category cap flag lets the first run cover image+video categories, expanding later.
