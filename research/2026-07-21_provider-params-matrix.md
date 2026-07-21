# Provider Generation-Parameters Matrix — ground truth per provider (2026-07-21)

**Agent B / Batch tracker step B1-B3.** Docs-only research: the exact generation params every
provider in Omni-Image accepts, plus the unified aspect-preset model that maps PRIME's 16-item
ideogram-style preset list to provider-legal pixel/enum values. Companion machine-readable file:
`engine/service_params.draft.json` (same shape as `fal_models.json` `params[]`, plus a new
`aspect_presets{}` block per service).

**Rev 2 (post-judge, 84→target ≥90):** added the Request-payload cookbook (§14), turned the
aspect-preset mapping into a deterministic numbered algorithm with an explicit UI policy (§15),
retagged every default-bearing row against a stricter 4-tier provenance scale (below) so no
assumption ships wearing a badge it didn't earn, and added HF/Replicate/OpenRouter minimum-contract
one-liners.

## Provenance legend (read before trusting any "default" in this doc)

Every claim carries one of these tags. `CONFIRMED` from Rev 1 has been retired — it conflated
"I read a docs page" with "this was independently verified," which is exactly the gap the judge
caught. A default value is only as trustworthy as *where it was actually seen*:

- **DOC-RAW** — read from the provider's literal spec text (a raw OpenAPI/YAML/JSON file fetched
  and grepped directly, not summarized). Strongest tier. Only NVIDIA's schema was sourced this way
  this round (the NIM `.openapi.yaml` was fetched and read with Bash/grep, not paraphrased).
- **DOC-SUMMARY** — seen in a `WebFetch`/`WebSearch` pass over the provider's docs page. This is an
  LLM-generated paraphrase of the page, not a literal quote — reliable for field *names* and
  *stated* enum/range values, but a single pass, never independently cross-checked against a second
  source. Noted per-row where a default was explicitly labeled `Default:`/`(default)` in the
  fetched text vs. merely shown as an example payload value (those are NOT the same evidence and
  are now split apart below).
- **PROBE** — a live HTTP response from this app (either logged in an existing `.dd/*-contract.md`,
  or newly observed) that confirms a field/shape is *accepted* by the server. A probe proves the
  field name and type are legal; it does NOT by itself prove a specific numeric default, unless the
  response explicitly echoed one back.
- **CODE** — only ever seen in this app's own source (`engine/backends/*.py`,
  `engine/service_params.json`). No external confirmation at all. Most "defaults" in the *shipped*
  schema turn out to be this tier — that's the honest starting point for Phase 2, not a criticism.
- **UNVERIFIED** — none of the above; a best-guess or unstated value, flagged so it gets a live
  probe before Phase 2 trusts it.

PRIME's 16-preset model (the target every provider gets mapped onto):
Portrait `1:3 1:2 9:16 10:16 2:3 3:4 4:5` · Landscape `3:1 2:1 16:9 16:10 3:2 4:3 5:4` · `1:1` ·
`Custom` · `Auto`.

---

## 1. OpenAI (`gpt-image-1` / `gpt-image-1.5` / `gpt-image-2`)

**Endpoint:** `POST https://api.openai.com/v1/images/generations`, Bearer auth.
**Size model:** `enum_wh_string` — exactly 3 legal concrete sizes + `auto`. No free width/height.

| Param | Type | Values | Default | Source |
|---|---|---|---|---|
| `size` | enum | `auto, 1024x1024, 1536x1024, 1024x1536` | `auto` | DOC-SUMMARY — `auto (default)` explicitly marked in [developers.openai.com/api/docs/guides/image-generation](https://developers.openai.com/api/docs/guides/image-generation) |
| `quality` | enum | `auto, low, medium, high` | `auto` | DOC-SUMMARY — `(default)` marked, same source |
| `background` | enum | `auto, opaque, transparent` | `auto` | DOC-SUMMARY — `(default)` marked; `transparent` **not supported on gpt-image-2** per the same doc note |
| `output_format` | enum | `png, jpeg, webp` | `png` | values = DOC-SUMMARY (enum stated); default `png` = **CODE** — not marked as a default in the fetched text, only present in `engine/service_params.json` |
| `output_compression` | int | 0–100 | — | DOC-SUMMARY, jpeg/webp only |
| `moderation` | enum | `auto, low` | `auto` | DOC-SUMMARY — `(default)` marked |
| `n` | int | 1–10 | 1 | max = UNVERIFIED (not stated anywhere fetched; 10 carried forward as the historical dall-e-2 ceiling — CODE); default 1 = CODE (`service_params.json`, standard REST convention, never doc-stated) |

**App behavior confirmed correct:** `engine/backends/openai_api.py::_size()` already snaps any
non-legal WxH to the nearest of the 3 concrete sizes before sending — this is the ONE backend
that already does size validation client-side.

## 2. cliproxy (self-hosted OpenAI-compat proxy → gpt-image family)

Same wire shape as OpenAI §1 (no independent spec; it's a pass-through — every tag above applies
identically, one hop further removed since the proxy's own default-if-omitted behavior was never
independently tested, only assumed identical to upstream OpenAI). **Bug:**
`engine/backends/cliproxy_api.py` builds `size` from raw `width x height` with **no snap** to the
3 legal enum values the OpenAI backend applies — see the Bug List, item 1.

## 3. Gemini (`gemini-2.5-flash-image`, `gemini-3-pro-image`, `gemini-3.1-flash-image`, …)

**Endpoint:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=`.
**Size model:** `aspect_ratio_enum_plus_tier` — closed 10-value ratio enum + a separate resolution
tier. No width/height override exists at all.

| Param | Type | Values | Default | Source |
|---|---|---|---|---|
| `generationConfig.imageConfig.aspectRatio` | enum | `1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9` | `1:1` | values = DOC-SUMMARY — [ai.google.dev/gemini-api/docs/image-generation](https://ai.google.dev/gemini-api/docs/image-generation); default `1:1` = **CODE** (`service_params.json`) — the fetched text never states a default ratio |
| `generationConfig.imageConfig.imageSize` | enum | `1K, 2K, 4K` (upper-case `K` mandatory) | `1K` | DOC-SUMMARY, default explicitly stated ("1K … all models support this default resolution"); 2K/4K gated to `gemini-3.1-flash-image`/`gemini-3-pro-image`; a 512px/`0.5K` tier exists only on `gemini-3.1-flash-lite-image` (not currently in our enum) |

`.dd/per-service-params-contract.md` already logged this field-pair NAME as PROBE-confirmed (429
quota response, not 400 → body shape accepted) — that proves `imageConfig.aspectRatio`/`imageSize`
are legal keys, it does not independently confirm the specific default values above.

## 4. NVIDIA NIM (`ai.api.nvidia.com/v1/genai/{model}` — FLUX.1-dev / FLUX.1-schnell / SD3.5-large)

**Size model:** `fixed_wh_enum_independent` — **this is the single biggest correction in this
research, and the strongest-sourced (DOC-RAW throughout).** The current `service_params.json`
declares width/height as a continuous `min:320 max:1536 step:64` range. The real NIM `ImageRequest`
schema constrains width AND height **independently** to the exact same 10-value enum:

`768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344`

Both axes cap at 1344 — so extreme ratios (3:1, 1:3, 2:1, 1:2) are **physically unachievable**;
the nearest legal pair is the best available (see §15).

| Param | Type | Range/Values | Default | Source |
|---|---|---|---|---|
| `width` | enum | the 10-value list above | 1024 | DOC-RAW — raw `.yaml` text read directly, [FLUX.1-dev](https://docs.nvidia.com/nim/visual-genai/latest/api/flux.1-dev.html) + [SD3.5-large](https://docs.nvidia.com/nim/visual-genai/latest/api/stable-diffusion-3.5-large.html) OpenAPI specs, both byte-identical on this schema |
| `height` | enum | same 10-value list | 1024 | DOC-RAW, same source |
| `steps` | int | **5–100** | 50 | DOC-RAW (`minimum: 5.0, maximum: 100.0, default: 50` in the schema) — current shipped schema wrongly says 1–50, default 25 |
| `cfg_scale` | float | **(1.0, 9.0]** (exclusive min) | 3.5 | DOC-RAW (`exclusiveMinimum: 1.0, maximum: 9.0, default: 3.5`) — current shipped schema wrongly says 0–20, default 4.5 |
| `seed` | int | 0 – 4294967295 | 0 (random) | DOC-RAW |
| `samples` | int | **1 only** (hard max=min=1) | 1 | DOC-RAW — batching >1 is rejected outright by the schema itself |
| `disable_safety_checker` | bool | — | false | DOC-RAW (`default: false` literal in the schema), but the field's *effect* is gated server-side behind `NIM_ALLOW_UNCHECKED_GENERATION=true` — may be a no-op on the hosted endpoint (that gate flag's state on `ai.api.nvidia.com` is UNVERIFIED) |
| `negative_prompt` | — | **NOT A FIELD** | — | DOC-RAW absence. `text_prompts` (deprecated) allows exactly 1 entry with `weight` locked to `const 1.0` — there is no negative-weight mechanism at all |

**Caveat on source parity:** this schema is the self-hosted NIM container's OpenAPI spec
(`docs.nvidia.com/nim/visual-genai`), fetched and read as raw text. Our backend calls the
NVIDIA-*hosted* endpoint (`ai.api.nvidia.com/v1/genai/{model}`), which is assumed — not
independently re-confirmed — to mirror this schema 1:1 (same publisher, same container per model
family; that parity is the entire point of NIM). Treat as **DOC-RAW-adjacent**, not
DOC-RAW-hosted: the schema text itself is as strong as evidence gets, the *endpoint match* is the
one remaining unverified link in the chain.

**Bug:** `engine/backends/nvidia_api.py` sends `negative_prompt` unconditionally whenever the UI
field is filled. Per the schema above, this field doesn't exist on the request model — see the Bug
List, item 2.

## 5. Together.ai (`black-forest-labs/FLUX.1-schnell[-Free]`, `FLUX.1.1-pro`, `FLUX.2-*`)

**Endpoint:** `POST https://api.together.xyz/v1/images/generations`, OpenAI-compatible.
**Size model:** `free_wh` — free integer width/height, **no documented multiple-of-N or hard
bound** at all (docs give none).

| Param | Type | Range | Default | Source |
|---|---|---|---|---|
| `width`, `height` | int | undocumented (256/1792/step-64 in the shipped schema is the app's own pre-existing convention) | 1024 | range = DOC-SUMMARY-absent (no constraint stated); default `1024` = **DOC-SUMMARY, but weak** — only seen as an example payload value (`"height": 1024, "width": 1152`), never a literal `Default:` field — [docs.together.ai/reference/post-images-generations](https://docs.together.ai/reference/post-images-generations) |
| `steps` | int | undocumented | 20 | default = DOC-SUMMARY (a literal `Default` column value of `20` in the fetched parameter table) |
| `guidance_scale` | float | "1–10 suggested" (not enforced) | 3.5 | default = DOC-SUMMARY (literal `Default` column `3.5`); the 1–10 range is advisory prose, not a hard enum |
| `seed` | int | — | — | DOC-SUMMARY, field exists, no default claimed |
| `negative_prompt` | string | — | — | DOC-SUMMARY, field exists, no default claimed |
| `n` | int | undocumented max | 1 | default = DOC-SUMMARY (literal `Default` column `1`); max = UNVERIFIED, app assumes 4 |
| `output_format` | enum | `jpeg, png` | `jpeg` | DOC-SUMMARY, literal `Default` column `jpeg` |
| `disable_safety_checker` | bool | — | false | field = DOC-SUMMARY (exists); default `false` = **CODE** — the fetched table's Default column literally shows `—` (no default given), our schema's `false` is our own assumption |
| `image_loras` | array `[{path,scale}]` | max 2, FLUX.1-dev-lora/FLUX.2-dev only | — | DOC-SUMMARY (already correctly gated in `together_api.py::_supports_lora`) |

## 6. Novita AI (async txt2img)

**Endpoint:** `POST https://api.novita.ai/v3/async/txt2img` → poll `GET /v3/async/task-result`.
**Confirms:** the "Model APIs" nav category in Novita's docs **is** this same async endpoint —
no separate synchronous alternative was found; same body shape either way.
**Size model:** `free_wh`, range DOC-SUMMARY-confirmed.

| Param | Type | Range | Default | Source |
|---|---|---|---|---|
| `width`, `height` | int | **128–2048** | — | DOC-SUMMARY range; no default claimed either way — [novita.ai/docs/api-reference/model-apis-text-to-image](https://novita.ai/docs/api-reference/model-apis-text-to-image) |
| `steps` | int | **1–100** | — | DOC-SUMMARY range, no default stated |
| `guidance_scale` | float | **1–30** | 7 | range = DOC-SUMMARY (current shipped schema wrongly floors at 0); default `7` = **CODE** (`novita_api.py`'s own `params.get("guidance_scale", 7.0)`) — the fetched table gave the range with no Default column at all |
| `sampler_name` | enum | 19 values (Euler a, Euler, LMS, Heun, DPM2, DPM2 a, DPM++ 2S a, DPM++ 2M, DPM++ SDE, DPM fast, DPM adaptive, LMS Karras, DPM2 Karras, DPM2 a Karras, DPM++ 2S a Karras, DPM++ 2M Karras, DPM++ SDE Karras, DDIM, PLMS, UniPC) | "Euler a" | values = DOC-SUMMARY (current shipped schema lists only 5, a safe subset); default `"Euler a"` = **CODE** (`novita_api.py`'s own fallback) — no default was stated in the fetched text |
| `seed` | int | ≥ -1 | -1 | DOC-SUMMARY — literal `Default: -1` stated |
| `negative_prompt`, `prompt` | string | **1–1024 runes** | — | DOC-SUMMARY, doubly confirmed by matching the existing clamp in `_build_body()` (independent code cross-check, unusually strong for this doc) |
| `image_num` | int | **1–8** | — | DOC-SUMMARY range, no default stated by docs (app itself defaults to 1 — CODE) |
| `enable_nsfw_detection` | bool | opt-in | false | field/billing note = DOC-SUMMARY ("adds $0.0015 cost per image when enabled" implies opt-in); the literal value `false` as a stated default was never seen — **UNVERIFIED-observed**, inferred from the billing note's opt-in language, not a `Default:` field |

## 7. Runware (single `POST /v1` array-of-tasks, `imageInference` task)

**Size model:** `free_wh`, model-dependent per docs (no universal hard bound stated).
Sourced via `WebSearch` (Google's AI-overview of the page), one remove further than a direct
`WebFetch` — flagged per-row.

| Param | Type | Range | Default | Source |
|---|---|---|---|---|
| `width`, `height` | int | model-dependent (undocumented universal bound) | — | UNVERIFIED — [runware.ai/docs/image-inference/api-reference](https://runware.ai/docs/image-inference/api-reference) states dimensions vary per model; the `1024`/`1152` numbers seen were an example payload, not a stated default (CODE-only in the shipped schema) |
| `steps` | int | 1–100 | 20 | DOC-SUMMARY via WebSearch overview, literal `default: 20` — not independently re-fetched, lower confidence than a direct page read |
| `CFGScale` | float | **0–50** | 7 | DOC-SUMMARY via WebSearch overview, literal `default: 7` — current shipped schema wrongly caps max at 30 |
| `numberResults` | int | **1–20** | 1 | DOC-SUMMARY via WebSearch overview, literal `default: 1` — current shipped schema wrongly caps max at 4 |
| `seed` | int | — | — | DOC-SUMMARY, field exists |
| `negativePrompt` | string | — | — | DOC-SUMMARY, field exists |
| `checkNSFW` | bool | opt-in | false | field = DOC-SUMMARY; default `false` = **CODE** (matches `runware_api.py`'s own assumption, not independently doc-confirmed) |
| `scheduler` | string | — | — | DOC-SUMMARY, field exists |
| `outputType` / `outputFormat` | enum | — | `URL` / — | DOC-SUMMARY, field exists; `URL` default = CODE |

## 8. Hugging Face Inference (`InferenceClient.text_to_image`)

**Size model:** `free_wh_model_dependent`. There is **no universal API contract** — the SDK
forwards kwargs to whichever Inference Provider backs the chosen model, so legal ranges are
genuinely per-model and unknowable in advance. Every numeric bound and every default in the
current schema and in `service_params.draft.json`'s illustrative table is **CODE-only** —
seen exclusively in `engine/backends/hf_api.py` / `engine/service_params.json`, never
independently doc-confirmed or probed, because there is no single spec to confirm against.

**Minimum implementable contract:** pass-through only. Enable the aspect-preset controls in the
UI **only when the selected model's own (per-model, unknowable-in-advance) schema happens to
declare `width`/`height`** — don't enforce any numeric range client-side, since a range that's
correct for one HF-hosted model will be wrong for the next. No retry/fallback logic beyond what
`hf_api.py` already does (distinguishing "model is loading" from a hard error).

## 9. Ideogram v3 (`POST https://api.ideogram.ai/v1/ideogram-v3/generate`, multipart form, `Api-Key` header)

**Size model:** `aspect_ratio_or_resolution_enum`, mutually exclusive.

**Key finding: PRIME's 15 ratio presets already map 1:1 onto Ideogram's own native `aspect_ratio`
enum** — only the separator differs (`:` vs `x`). This preset list looks like it was modeled
directly off Ideogram's list.

| Param | Type | Values | Default | Source |
|---|---|---|---|---|
| `aspect_ratio` | enum | `1x3, 3x1, 1x2, 2x1, 9x16, 16x9, 10x16, 16x10, 2x3, 3x2, 3x4, 4x3, 4x5, 5x4, 1x1` | `1x1` | DOC-SUMMARY — literal `Default: 1x1` — [developer.ideogram.ai/api-reference/api-reference/generate-v3](https://developer.ideogram.ai/api-reference/api-reference/generate-v3) |
| `resolution` | string | ~76 exact WxH options (512×1536 … 1536×512); overrides `aspect_ratio` | — | DOC-SUMMARY count/range, full enumeration not reproduced here |
| `rendering_speed` | enum | `FLASH, TURBO, DEFAULT, QUALITY` | `DEFAULT` | DOC-SUMMARY — literal `Default: DEFAULT` — current shipped schema is missing `FLASH` |
| `magic_prompt` | enum | `AUTO, ON, OFF` | `AUTO` | values = DOC-SUMMARY; default `AUTO` = **CODE** — the fetched text listed only `Options: AUTO, ON, OFF` with no default marked |
| `style_type` | enum | `AUTO, GENERAL, REALISTIC, DESIGN, FICTION` | `GENERAL` | DOC-SUMMARY — literal `Default: GENERAL` — current shipped schema is missing `FICTION` and states the wrong default (`AUTO`) |
| `num_images` | int | 1–? | 1 | default = DOC-SUMMARY (literal `(default: 1)`); exact max = UNVERIFIED, app assumes 8 |
| `negative_prompt` | string | — | — | DOC-SUMMARY, field exists |
| `seed` | int | — | — | DOC-SUMMARY, field exists |
| `style_preset` | enum | 56 values (`WATERCOLOR`, `OIL_PAINTING`, `POP_ART`, …) | — | DOC-SUMMARY, confirmed to exist, **not currently wired** in the app at all — expansion opportunity, not a bug |

## 10. AGNES-AI (`apihub.agnes-ai.com/v1`, OpenAI-compatible image + async video)

**Size model (image):** `free_wh_string` (`size: "WxH"`). Sparse public docs — most confidence
comes from the app's own PROBE evidence logged in `.dd/pD-providers-contract.md`, not a formal
spec.

| Param | Type | Notes | Default | Source |
|---|---|---|---|---|
| `size` | string | `"WxH"` shape | — | shape = DOC-SUMMARY — [agnes-ai.com/en/docs/agnes-image-20-flash](https://agnes-ai.com/en/docs/agnes-image-20-flash) shows `"size": "1024x768"` as an example, not a stated default. Any `"1024x1024"` default in the shipped/draft schema is **CODE-only** |
| `n` | int | undocumented cap | — | UNVERIFIED — no example, no field list found anywhere for `n` specifically |
| `response_format` | enum | `url` / `b64_json` — **must be nested under `extra_body`, not top-level**, or the API 400s | — | DOC-SUMMARY (explicit warning in the docs) — the app doesn't currently send this field at all (harmless; format is auto-detected from whatever key comes back) |

**Video (`/v1/videos`):** `aspect_ratio` and `duration` field *names* are **PROBE**-confirmed
2026-07-20 (HTTP 200, `status:queued`) per the existing contract — that proves they're accepted,
not that `"16:9"` is specifically the server's own default-if-omitted (the shipped default is
**CODE**, from `service_params.json`, never doc-stated). `width`, `height`, `num_frames`,
`frame_rate` bounds are pure **CODE** — the app's own assumption, no doc and no probe of the
numeric bounds themselves (only that the endpoint accepts a request shaped like one).

## 11. OpenRouter — the biggest structural inconsistency found this session

**Two completely different code paths exist, and the app uses the wrong one for size control:**

1. **Legacy chat/completions image-modality** (what `engine/backends/openrouter_api.py` calls
   today): `POST /api/v1/chat/completions` with `modalities: ["image", "text"]`. Per OpenRouter's
   current docs this path has **no documented size/aspect_ratio/resolution body field at all** —
   output dimensions are entirely prompt-text-driven or model-default. DOC-SUMMARY via
   [openrouter.ai/docs/features/multimodal/image-generation](https://openrouter.ai/docs/features/multimodal/image-generation)
   and the [Unified Image API announcement](https://openrouter.ai/blog/announcements/image-api/),
   which explicitly says legacy chat-completions models "continue to be supported here" without
   describing any size parameter for that path.

2. **New dedicated Image API** (`POST /api/v1/images`): DOES accept real size control —

   | Param | Type | Values | Default | Source |
   |---|---|---|---|---|
   | `resolution` | enum | `512, 1K, 2K, 4K` (model-dependent) | — | DOC-SUMMARY — announcement blog |
   | `aspect_ratio` | string | e.g. `16:9`, `9:16` — provider clamps to its own supported subset | — | DOC-SUMMARY |
   | `size` | string | explicit `"WxH"` — **authoritative when paired with `resolution`/`aspect_ratio`; a mismatched pair 400s** | — | DOC-SUMMARY |
   | `n` | int | up to 10, model-dependent | — | DOC-SUMMARY range statement, per-model cap UNVERIFIED |
   | `seed` | int | model-dependent support | — | UNVERIFIED which models honor it |

**Minimum implementable contract:** on the legacy path, don't send any size field at all (it's a
guaranteed no-op — sending nothing is more honest than sending something ignored). Real
aspect-ratio control requires migrating to `/api/v1/images` — until then, treat this provider's
aspect-preset dropdown as decorative in the UI (grey it out or badge it "prompt-only"), not silent.

**Net effect: the aspect-preset control in the unified UI is a silent no-op for OpenRouter as
currently wired.** See the Bug List, item 5 — this is the single change most likely to fix
PRIME's "no consistency" complaint for this provider specifically, since today it has *zero*
consistency (no control surface exists on the path the app actually calls).

## 12. Replicate (fully dynamic, live per-model schema — already the right architecture)

**Size model:** `dynamic_per_model`. `bridge.py::_replicate_input_params()` already does this
correctly: `GET /v1/models/{owner}/{name}` → `latest_version.openapi_schema.components.schemas.Input`
→ `_openapi_props_to_params()` walks the OpenAPI properties (resolving `allOf`/`$ref` enum refs)
into the same `params[]` shape used everywhere else. Mechanism = DOC-SUMMARY-confirmed —
[replicate.com/docs/reference/http](https://replicate.com/docs/reference/http); the actual per-call
schema is live-fetched at runtime, so its correctness is self-verifying (PROBE, every call) rather
than something this doc needs to pin down statically.

**Always-injected fields regardless of the fetched schema** (`replicate_api.py::_build_input`, all
**CODE** — read directly from source, no external doc involved since these are *this app's*
choices, not Replicate's):
`num_inference_steps` (28), `guidance_scale`/`guidance` (7.5), `negative_prompt` (""),
`num_outputs` (1), `apply_watermark` (False, FLUX-specific), `disable_safety_checker` (True),
`safety_tolerance` (≤6, default 6). These are sent to **every** model whether or not its own
schema declares them. Cog-based Replicate models are generally tolerant of unknown extra input
keys (ecosystem convention — not hard-documented anywhere), so this is treated as LOW-risk /
UNVERIFIED rather than a confirmed bug — flagged for a live check, not a fix.

**Minimum implementable contract:** trust the live-fetched schema as authoritative for size/steps/
guidance/seed *when it declares them*; the 7 always-injected fields above are a separate,
app-level overlay that isn't schema-driven and shouldn't be — don't try to make them "discovered,"
they're deliberate defaults this app applies on top of whatever the model exposes.

## 13. fal.ai — already solved correctly; do not touch

1,322 curated models in `engine/fal_models.json`, sourced live from fal's own per-model schema
metadata (not something this research needs to re-derive — that data IS the primary source,
fetched by the app itself, effectively DOC-RAW by construction). Two size families observed
directly in the data:

- **`image_size` family** (e.g. `fal-ai/flux/schnell`, `fal-ai/flux/dev`, `fal-ai/flux-2-pro`,
  `openai/gpt-image-2`): an enum preset (`square_hd, square, portrait_4_3, portrait_16_9,
  landscape_4_3, landscape_16_9`) that fal's own API accepts as **either** the preset string
  **or** an explicit `{width, height}` object **or** `"auto"`. `bridge.py::_build_args` already
  overrides it with `{width, height}` whenever the UI supplies both — this already works.
- **`aspect_ratio` family** (e.g. `fal-ai/nano-banana-2`, `fal-ai/nano-banana-pro`): a literal
  ratio-string enum that already nearly matches PRIME's preset naming. `nano-banana-2` adds
  `auto` + 4 extreme ratios (`4:1, 1:4, 8:1, 1:8`) our preset list doesn't have; `nano-banana-pro`'s
  narrower 10-value set omits `16:10, 10:16, 1:3, 3:1, 1:2, 2:1` — for those, fall back to (a)'s
  width/height override if the same model also exposes width/height, else nearest-enum-match,
  else 1:1.

---

## 14. Request-payload cookbook — the exact SEND contract, per provider

The gap the matrix alone doesn't close: an integrator copying field names between providers will
get casing, nesting, and omission rules wrong. One block per provider — exact casing, exact type,
what must be **absent** (not `null`, not `""`) vs. what's safe to omit, and the fallback on a
predictable failure.

**OpenAI / cliproxy**
```
POST /v1/images/generations
{ "model": "gpt-image-2", "prompt": "...", "n": 1,
  "size": "1024x1024",                        // one of the 4 legal strings ONLY
  "quality": "auto", "background": "auto",
  "output_format": "png", "output_compression": 80,  // omit unless format is jpeg/webp
  "moderation": "auto" }
```
snake_case throughout, matches the field names 1:1. `background:"transparent"` must never be sent
to gpt-image-2 (400s). Failure/fallback (fixes Bug #1): **snap `size` to the nearest legal enum
before send** — mirror `openai_api.py::_size()` on the cliproxy path too, it's currently missing
there.

**Gemini**
```
POST /v1beta/models/{model}:generateContent?key=...
{ "contents": [...], "generationConfig": {
    "responseModalities": ["TEXT","IMAGE"],
    "imageConfig": { "aspectRatio": "16:9", "imageSize": "1K" } } }
```
`imageConfig` fields are **camelCase** (`aspectRatio`, `imageSize`) — the one provider where a
snake_case field name from any other provider is silently ignored, not rejected. Omit `imageConfig`
entirely (not `{}`) when neither sub-field is set. A 429 (quota) is not a signal the shape is
wrong — retry/backoff, don't change the request.

**NVIDIA**
```
POST https://ai.api.nvidia.com/v1/genai/{model}
{ "prompt": "...", "mode": "base", "width": 1024, "height": 1024,
  "steps": 50, "cfg_scale": 3.5, "seed": 0 }
```
snake_case. **Never send `negative_prompt`** — not `null`, not `""`, absent entirely (undeclared
field on a schema this strict elsewhere is a 422 risk). Never send `samples` > 1. A 422 naming
`width`/`height` means the value isn't one of the 10 legal enum entries — snap to nearest and
resend, don't retry the same value.

**Together**
```
POST /v1/images/generations
{ "model": "black-forest-labs/FLUX.1.1-pro", "prompt": "...",
  "n": 1, "width": 1024, "height": 1024, "steps": 20,
  "guidance_scale": 3.5, "output_format": "jpeg" }
```
snake_case. `image_loras` must be **omitted** (not `[]`) on any model except
`FLUX.1-dev-lora`/`FLUX.2-dev`. On a 400 naming an unsupported param for the chosen model (docs
note per-model variance), drop that one field and retry once — don't blind-retry the whole body.

**Novita**
```
POST /v3/async/txt2img
{ "extra": {"response_image_type":"jpeg"},
  "request": { "model_name": "...", "prompt": "..." (<=1024 chars),
    "width":1024, "height":1024, "image_num":1, "steps":25,
    "guidance_scale":7.0, "sampler_name":"Euler a", "seed":-1 } }
```
snake_case, but nested one level under `request`+`extra` — the ONE provider whose body isn't flat.
`enable_nsfw_detection`: **omit for permissive mode** — its absence matches the app's Content Mode
convention (explicit `false` also works, omission is the documented-lighter path). Async — poll
`task-result?task_id=`; a `TASK_STATUS_FAILED.reason` should surface verbatim, never be silently
retried.

**Runware**
```
POST /v1
[ { "taskType":"imageInference", "taskUUID":"<uuid>",
    "model":"...", "positivePrompt":"...", "width":1024, "height":1024,
    "numberResults":1, "outputType":"URL", "CFGScale":7, "steps":20,
    "checkNSFW": false } ]
```
**Mixed casing** — `taskType`/`taskUUID`/`positivePrompt`/`numberResults`/`outputType`/`CFGScale`
are camelCase (`CFGScale` even capitalizes the acronym), and the body is an **array** of task
objects, not a single object — the easiest provider to break by copy-pasting a snake_case single-
object body from anywhere else. `checkNSFW`: always send explicitly (true/false) — the server's
own default when omitted is undocumented, don't rely on it. On error, `errors[0].message` is the
one place to surface — no retry logic needed (single synchronous call).

**HuggingFace**
```python
client.text_to_image(model=model_id, prompt=..., negative_prompt=...,
                      width=1024, height=1024, guidance_scale=7.5,
                      num_inference_steps=28, seed=...)
```
snake_case Python kwargs, forwarded by the SDK to whichever Inference Provider backs the model —
the *wire-level* casing on the real backing API is outside this app's control. `None` values are
already stripped before the call (`{k:v for k,v in ... if v is not None}`) — correct pattern,
keep it. "Model is currently loading" is a distinct, non-fatal state already classified separately
in `hf_api.py` — no numeric-range retry loop, since ranges are genuinely per-model.

**Ideogram**
```
POST /v1/ideogram-v3/generate   (multipart/form-data, Api-Key header)
prompt=..., aspect_ratio=9x16, rendering_speed=DEFAULT,
style_type=GENERAL, magic_prompt=AUTO, num_images=1
```
snake_case field *names*, but `aspect_ratio` *values* use `x` not `:` (`9x16`, never `9:16`) — the
one translation every other provider skips. Send **either** `aspect_ratio` **or** `resolution`,
never both. Every scalar must be a form-encoded `(None, value)` tuple (already correct in
`ideogram_api.py`). 401 = bad key (already surfaced distinctly); any other 4xx should show
`r.text` verbatim (already correct).

**AGNES**
```
POST /v1/images/generations
{ "model":"agnes-image-2.1-flash", "prompt":"...", "n":1, "size":"1024x1024" }
```
snake_case, OpenAI-compatible. `response_format`, if ever sent, must go under
`extra_body.response_format` — top-level 400s per the docs' own warning. Video (`/v1/videos`):
send `aspect_ratio`+`duration` at the top level directly (both PROBE-confirmed accepted); poll
`GET /agnesapi?video_id=` until `status` hits a done/fail set — no fixed-sleep retry, the existing
bounded poll loop is correct.

**OpenRouter**
Legacy path (currently wired): `{ "model":..., "messages":[{"role":"user","content":prompt}],
"modalities":["image","text"] }` — **no size field exists to send**; sending one is silently
ignored, not an error. Recommended path (not yet wired): `POST /api/v1/images` with
`{ "model":..., "prompt":..., "resolution":"1K", "aspect_ratio":"16:9" }` — omit `size` unless
it's meant to be the sole authority; a mismatched `size`+`resolution`/`aspect_ratio` trio 400s.
Fallback on that specific 400: retry once with `aspect_ratio` only (drop `resolution` and `size`)
before surfacing the error.

**Replicate**
No fixed body — always send `prompt`; send **either** `width`/`height` **or** the model's declared
`aspect_ratio` field, never both (prefer `aspect_ratio` when the schema offers it — no clamping
math needed). The 7 always-injected fields (§12) are sent unconditionally today with no per-model
fallback if one is rejected — that's the flagged LOW-risk item, not fixed here.

**fal**
No fixed body — per-model, but already correctly solved: `image_size` sent as `{width,height}`
whenever the UI has both; `aspect_ratio`-family models get the ratio string directly if it's in
that model's own enum, else nearest-match, else omitted (let the model default). No cookbook gap
here.

---

## 15. Deterministic aspect-preset algorithm

Given a **preset name** (one of PRIME's 15 ratio strings, or `Custom`, or `Auto`) and a **target
provider**, resolve the value to send in this exact order:

1. **Resolve the provider's `size_mode`** — one of `free_wh`, `fixed_wh_enum_independent`,
   `aspect_ratio_enum_plus_tier` / `aspect_ratio_or_resolution_enum` / other enum-native shapes,
   `enum_wh_string`, or `dynamic_per_model`.
2. **`Custom` short-circuits everything below** — pass the user's raw width/height (or raw ratio
   string, for enum-only providers) straight through, clamped only to the provider's own legal
   bounds. It is never computed from the preset table.
3. **`Auto` short-circuits to a lookup, not a computation** — if the provider has a literal
   `"auto"` sentinel (OpenAI/cliproxy `size=auto`, some fal `aspect_ratio` models), send it.
   Otherwise **omit the size parameter entirely** and let the provider's own default apply — never
   silently substitute `1:1`, since that changes provider behavior the user didn't ask for.
4. **Otherwise, branch on `size_mode`:**
   - **`free_wh`** (Together / Novita / Runware / HF / AGNES-image / fal's `image_size` family /
     Replicate's generic fallback): `target_area = 1024×1024 = 1,048,576px` → per-axis
     `h = sqrt(area / ratio)`, `w = h * ratio` → **snap both axes to the 16px grid**
     (`round(v/16)*16`) → **clamp each axis independently** to the provider's own min/max → **if
     clamping moved a value off the 16px grid, re-snap once more and re-clamp** (this converges in
     at most 2 passes — clamping only ever pushes toward a bound, never past it a second time).
     16px, not 64px, was chosen specifically because a 64px grid collapsed distinct ratios like
     `10:16` and `2:3` onto the same pixel pair in the first draft of this table.
   - **`fixed_wh_enum_independent`** (NVIDIA): exhaustively score all `10×10=100` `(w,h)` pairs
     from the fixed enum by `|w/h − ratio|`; pick the minimum. **Tie-break 1:** prefer the pair
     with larger total area (more detail retained). **Tie-break 2:** if still tied, prefer the
     pair closer to the enum's own median (1024) for stability across adjacent presets.
   - **Enum-native ratio families** (Gemini's 10-value enum, Ideogram's 15-value enum, OpenRouter's
     new endpoint, fal's `aspect_ratio` family): if the preset string is literally present in the
     provider's enum, send it verbatim (near-total match for Ideogram; exact for most of fal's
     `aspect_ratio` models). Else pick the enum value minimizing `|enum_ratio − preset_ratio|`,
     **tie-break by same orientation** — a portrait preset never snaps to a landscape enum value
     and vice versa; `1:1` only ever matches `1:1`.
   - **`enum_wh_string`** (OpenAI / cliproxy): 3-bucket classifier — `ratio > 1.05` → `1536x1024`,
     `ratio < 0.95` → `1024x1536`, else → `1024x1024`. The `0.95`/`1.05` deadband exists so a
     near-square custom ratio doesn't flip-flop between buckets on floating-point noise.
   - **`dynamic_per_model`** (Replicate): inspect the live-fetched schema first — declares
     `aspect_ratio`? use the enum-native rule above. Declares `width`+`height`? use the `free_wh`
     rule, clamped to *that model's own* schema bounds, not a global default. Declares neither?
     omit size control, same as `Auto`.

**UI policy for unachievable presets — NEAREST-with-badge, one policy, applied uniformly.**
Disable-with-tooltip was rejected: it would make the *same preset button* behave differently per
provider (present-and-live on 9 providers, greyed-out on NVIDIA) — reintroducing exactly the kind
of per-provider inconsistency this whole exercise exists to remove. Nearest-with-badge keeps one
uniform 15-button row everywhere; a small badge (e.g. "≈") plus a tooltip stating the achieved
ratio communicates the compromise without hiding the control. Applies identically to all three
cases found in this research:
- **NVIDIA's 4 unachievable presets** (3:1, 1:3, 2:1, 1:2) — badge shows the achieved ratio from
  `service_params.draft.json`'s `nvidia.aspect_presets` table.
- **Gemini's 5 non-enum presets** (1:3, 1:2, 10:16, 3:1, 16:10) — badge shows which of the 10
  enum ratios was substituted.
- **`nano-banana-pro`'s 6 missing presets** (16:10, 10:16, 1:3, 3:1, 1:2, 2:1) — the `free_wh`
  width/height fallback from §13 is tried first (that model also exposes width/height); only if a
  future fal model lacks both does the badge fall back to nearest-enum-match.

---

## The 3 biggest inconsistencies (answers PRIME's actual complaint)

1. **Four incompatible size models coexist with no shared vocabulary:** enum-WxH-string
   (OpenAI/cliproxy), enum-aspect-ratio-string (Gemini, Ideogram, some fal models, OpenRouter's
   new endpoint), fixed-independent-enum-per-axis (NVIDIA — unique and easy to miss), and free
   continuous width/height (Together/Novita/Runware/HF/AGNES/most of fal/Replicate). A single
   "Aspect Ratio" dropdown that just forwards a colon-string will silently break on 4 of these 5
   shapes.
2. **NVIDIA's declared range was simply wrong** — the shipped schema (`min:320 max:1536 step:64`,
   `cfg_scale 0-20`, `steps 1-50`) doesn't match the real NIM contract (`768-1344` fixed 10-value
   enum on both axes, `cfg_scale (1.0,9.0]`, `steps 5-100`) at all — and this is the one provider
   where the correction is DOC-RAW-strength, not a paraphrase. Any request near the
   documented-but-fake bounds (e.g. width 512, or cfg_scale 15) would 422.
3. **OpenRouter has *zero* size control on the endpoint the app actually calls** — not "different
   params," but *no params at all* for size on that path. Every other provider at least has *some*
   knob; OpenRouter's aspect-preset dropdown is currently pure theater unless the backend migrates
   to `POST /api/v1/images`.

## Bug list — params the app currently sends that the live API does not accept

1. **cliproxy** (`cliproxy_api.py`) builds `size` from raw `width x height` with no legality
   check — unlike `openai_api.py`'s `_size()`, which snaps to the 3 legal enums first. Any custom
   width/height combo sent to cliproxy today likely 400s.
2. **NVIDIA** (`nvidia_api.py`) sends `negative_prompt` whenever the UI field is filled. The real
   `ImageRequest` schema (FLUX.1-dev, SD3.5-large) has no such field — `text_prompts` is
   deprecated and its one allowed entry has `weight` locked to `const 1.0`, so there is no
   negative-prompt mechanism at all on this endpoint family. Needs a live 422/ignore check.
3. **NVIDIA** `steps`/`cfg_scale` sliders in the UI are bounded by the wrong numbers (see finding
   #2 above) — a value near either shipped bound (e.g. steps=10 near the fake min of 1, or
   cfg_scale=15 within the fake 0-20 range) will 422 against the real 5-100 / (1.0,9.0] contract.
4. **Runware** and **Novita** `guidance_scale`/`CFGScale` and `numberResults` UI ceilings are
   *narrower* than the real API allows (Runware caps the app's slider at 30 vs. real 50, and at 4
   images vs. real 20; Novita floors guidance at 0 vs. real minimum 1) — not a hard failure, just
   under-exposed range that should be widened in Phase 2.
5. **OpenRouter** aspect-preset control is a no-op on the currently-called endpoint — not strictly
   a "rejected param" bug since nothing is sent that errors, but functionally the same problem
   PRIME is complaining about: the control exists in the UI and does nothing.

## Citations

- OpenAI: https://developers.openai.com/api/docs/guides/image-generation
- Together: https://docs.together.ai/reference/post-images-generations
- Gemini: https://ai.google.dev/gemini-api/docs/image-generation
- NVIDIA NIM FLUX.1-dev OpenAPI: https://docs.nvidia.com/nim/visual-genai/latest/api/flux.1-dev.html (raw spec: `_static/_static/yaml/flux.openapi.yaml`)
- NVIDIA NIM SD3.5-large OpenAPI: https://docs.nvidia.com/nim/visual-genai/latest/api/stable-diffusion-3.5-large.html (raw spec: `_static/_static/yaml/sd-3.5.openapi.yaml`)
- Novita: https://novita.ai/docs/api-reference/model-apis-text-to-image
- Runware: https://runware.ai/docs/image-inference/api-reference (via WebSearch overview, not independently re-fetched)
- Ideogram v3: https://developer.ideogram.ai/api-reference/api-reference/generate-v3
- AGNES-AI: https://agnes-ai.com/en/docs/agnes-image-20-flash , https://github.com/AgnesAI-Labs/AgnesAI-Models
- OpenRouter multimodal image generation: https://openrouter.ai/docs/features/multimodal/image-generation
- OpenRouter Unified Image API announcement: https://openrouter.ai/blog/announcements/image-api/
- Replicate HTTP API / model schema fetch: https://replicate.com/docs/reference/http
- fal.ai: sourced from the app's own live-fetched `engine/fal_models.json` (no external fetch needed — this is fal's own model metadata already vendored)
- cliproxy: no independent spec; mirrors OpenAI (§1) per its own docstring
