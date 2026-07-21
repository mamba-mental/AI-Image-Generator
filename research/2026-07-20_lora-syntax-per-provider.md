# LoRA Request Syntax — Per Provider (AI Studio Void)

**Date:** 2026-07-20
**Purpose:** Exact, verified request syntax for applying one or more LoRAs to an image-generation call, per provider. Wrong syntax silently no-ops, so every param name/value-shape below is quoted from official docs and flagged where unconfirmed.
**Verification:** Each claim checked against the provider's own API docs / schema page (URLs in Sources). Anything not confirmed is marked **⚠ UNCONFIRMED**.

---

## TL;DR — the two syntax families

Providers split into **two shapes**:

1. **Array-of-objects `{path/model_name, scale/strength}`** — fal.ai, WaveSpeed, Together (`image_loras`), Novita (`loras`), Replicate multi-lora (`hf_loras[]`+`lora_scales[]`), Segmind newer models (partial).
2. **Flat single-LoRA string params** — Replicate `flux-dev-lora` (`lora_weights`+`extra_lora`), Segmind (`lora`+`lora_2_url`/`lora_3_url`, or `finetune_id`+`lora_strength`), HF diffusers (`load_lora_weights`+`set_adapters`).

The **`path` value** also splits: URL/HF-repo (fal, WaveSpeed, Together, Replicate) vs **provider-internal name only** (Novita, Segmind presets) — the latter will NOT accept an arbitrary URL.

---

## 1. fal.ai — `loras: [{ "path", "scale" }]`  ✅ CONFIRMED

**Param:** `loras` (`list<LoraWeight>`, optional, default `[]`).
> "The LoRAs to use for the image generation. You can use any number of LoRAs and they will be merged together to generate the final image."

**`LoraWeight` object:**
- `path` (`string`, **required**) — "URL or the path to the LoRA weights."
- `scale` (`float`, optional, **default `1`**) — "The scale of the LoRA weight. This is used to scale the LoRA weight before merging it with the base model."

**Multi-LoRA:** YES — "any number", merged together. (Confirmed to be the `loras` param shape you asked about.)

**What `path` can be:**
- Direct `.safetensors` URL (e.g. `https://.../watercolor-style-lora.safetensors`) — confirmed in official example.
- **HuggingFace repo id** (e.g. `XLabs-AI/flux-RealismLora`) — widely used in fal examples/guides. ⚠ The strict schema line only says "URL or path"; HF-repo-id resolution is documented in fal usage guides, not this one schema sentence — but it is the standard fal pattern.
- fal-hosted URL (uploaded via fal storage).
- **Civitai:** only a *direct download URL that resolves to a `.safetensors`* works (with token); the Civitai model *page* URL does NOT. Prefer an HF mirror.

**Endpoints that accept `loras`:** `fal-ai/flux-lora` (text-to-image), plus its `/image-to-image`, `/inpainting` variants; `fal-ai/flux-general`; and other flux-lora-family models. (`fal-ai/flux/dev` base model does NOT take `loras` — use `fal-ai/flux-lora`.)

**Minimal request (HTTP `https://fal.run/fal-ai/flux-lora`):**
```json
{
  "prompt": "a portrait, painted in watercolor style",
  "loras": [
    { "path": "https://huggingface.co/XLabs-AI/flux-RealismLora", "scale": 0.9 },
    { "path": "https://example.com/watercolor-lora.safetensors", "scale": 0.7 }
  ]
}
```

---

## 2. Replicate — DIFFERS PER MODEL  ✅ CONFIRMED

There is **no single Replicate LoRA syntax** — it depends on which model version you call.

### 2a. `black-forest-labs/flux-dev-lora` (and `flux-schnell-lora`) — flat, max 2 LoRAs
- `lora_weights` (`string`) — main LoRA.
- `lora_scale` (`number`, default `1`, range `-1`…`3`).
- `extra_lora` (`string`) — a **second** LoRA to combine.
- `extra_lora_scale` (`number`, default `1`, range `-1`…`3`).
- `hf_api_token` (`string`) — for gated HF LoRAs.
- `civitai_api_token` (`string`) — for gated Civitai LoRAs.

**`lora_weights` / `extra_lora` value shapes (all supported):**
- Replicate model: `owner/model` or `owner/model/version` (e.g. `fofr/flux-pixar-cars`)
- HuggingFace URL: `huggingface.co/owner/model[/lora-file.safetensors]`
- CivitAI URL: `civitai.com/models/{id}[/{versionId}]`
- Any arbitrary `.safetensors` URL (incl. signed URLs)

**Multi-LoRA:** max **2** (main + `extra_lora`). Put trigger words for BOTH in the prompt.

```json
{
  "prompt": "ZIKI the man, illustrated MSMRB style",
  "lora_weights": "zeke/ziki-flux",
  "lora_scale": 1,
  "extra_lora": "jakedahn/flux-midsummer-blues",
  "extra_lora_scale": 1.22
}
```

### 2b. `lucataco/flux-dev-multi-lora` — arrays, up to 20 LoRAs
- `hf_loras` (`array<string>`) — "Huggingface path, or URL to the LoRA weights. Ex: `alvdansen/frosting_lane_flux`".
- `lora_scales` (`array<number>`, default `0.8` each).

**Value shapes:** HF path, Replicate LoRA URL, or CivitAI URL. For login-gated Civitai LoRAs, append `&token=<YOUR_API_TOKEN>` to the URL. **Max concurrent LoRAs: 20.**

```json
{
  "prompt": "a photo of TOK, sftsrv style",
  "hf_loras": ["alvdansen/frosting_lane_flux", "https://civitai.com/api/download/models/123456?token=XXX"],
  "lora_scales": [0.9, 0.8]
}
```

> **Implementation note:** detect the model and branch — `flux-dev-lora` → `lora_weights`/`extra_lora`; `flux-dev-multi-lora` → `hf_loras`/`lora_scales`. Sending `hf_loras` to `flux-dev-lora` (or vice-versa) is silently ignored.

---

## 3. HuggingFace — local diffusers vs Inference API (very different)  ✅ CONFIRMED

**There is no LoRA body param in HF's serverless text-to-image task schema** (task params are only `guidance_scale`, `negative_prompt`, `num_inference_steps`, `width`, `height`, `scheduler`, `seed`). LoRA on HF is handled two ways:

### 3a. Local `diffusers` (the reliable path) — `load_lora_weights` + `set_adapters`
```python
pipe.load_lora_weights("ostris/ikea-instructions-lora-sdxl",
                       weight_name="ikea_instructions_xl_v1_5.safetensors",
                       adapter_name="ikea")
pipe.load_lora_weights("lordjia/by-feng-zikai",
                       weight_name="fengzikai_v1.0_XL.safetensors",
                       adapter_name="feng")
pipe.set_adapters(["ikea", "feng"], adapter_weights=[0.7, 0.8])   # scale = adapter_weights
```
- The **scale** is `adapter_weights` (list<float>) in `set_adapters()`; default `1.0` if omitted.
- Single-LoRA scale: `pipe.set_adapters("ikea", adapter_weights=0.7)`.
- Multi-LoRA: YES (concatenated weighted matrices). `weight_name` picks the specific `.safetensors` inside the repo.

### 3b. Inference Providers / `InferenceClient.text_to_image()` — `adapter_id` / `extra_body`
- `InferenceClient.text_to_image(..., adapter_id="<lora repo id>")` — `adapter_id` is documented as "Lora adapter id".
- Provider-specific LoRA params go through `extra_body={...}` (e.g. routing to `fal-ai`/`replicate`/`together`/`wavespeed` as the backend provider, which then use THAT provider's own LoRA shape).
- Legacy Serverless Inference API accepted an HTTP header `lora: <owner/repo>` (per HF "dynamic LoRA loading" blog) — **⚠ legacy (2023); prefer `adapter_id`/`extra_body`**. Whether the LoRA actually applies is provider-dependent.

> **Bottom line for the tool:** treat HF as **local-diffusers only** for reliable LoRA. For hosted HF inference, LoRA support is limited and best done by routing `extra_body` to a real provider (fal/replicate/together/wavespeed) — in which case use that provider's syntax from this doc.

---

## 4. Together.ai — `image_loras: [{ "path", "scale" }]`  ✅ CONFIRMED (it DOES support LoRA)

**Together's image API DOES support LoRA** via the `image_loras` param (not "no").

- `image_loras` (`array<object>`) — each `{ "path": <url>, "scale": <float> }`.
- `path` = a URL to a valid Flux LoRA `.safetensors` (HF URL, Replicate URL, or any `.safetensors` URL). "You can point to any URL that has a `.safetensors` file with a valid Flux LoRA fine-tune."
- `scale` = strength; typical `0.3`–`1.2`.
- **Multi-LoRA: up to 2** per image.
- **Supported models:** `black-forest-labs/FLUX.1-dev-lora` and `black-forest-labs/FLUX.2-dev`. (Other FLUX models — Schnell, 1.1-Pro, Kontext — do NOT take `image_loras`.)
- Endpoint: `POST https://api.together.ai/v1/images/generations` (also `api.together.xyz`).

```json
{
  "model": "black-forest-labs/FLUX.1-dev-lora",
  "prompt": "a BLKLGHT image of a man walking in the rain",
  "width": 1024, "height": 768, "steps": 28, "n": 1, "response_format": "url",
  "image_loras": [
    { "path": "https://huggingface.co/XLabs-AI/flux-RealismLora", "scale": 0.8 },
    { "path": "https://replicate.com/fofr/flux-black-light", "scale": 0.8 }
  ]
}
```
Remember to include each LoRA's **trigger word** in the prompt.

---

## 5. Segmind — PER-MODEL, no universal `loras` array  ✅ CONFIRMED (fragmented)

Segmind has **no single unified multi-LoRA array param**. The shape depends on the endpoint (`POST https://api.segmind.com/v1/<model>`):

- **Preset + extra-URL models** (e.g. `qwen-image-edit-plus-multi-lora`):
  - `lora` (`string`) — a **pre-configured** LoRA name (enum, e.g. `"multiple_angle"`, `"add_people"`; default `"none"`).
  - `lora_2_url` (`string`) — "Additional LoRA model URL. Public direct url or huggingface url pointing to the lora file."
  - `lora_3_url` (`string`) — same. → up to ~3 LoRAs (1 preset + 2 URLs).
- **Finetune model** (`flux-dev-finetuned`): `finetune_id` (`string`) + `lora_strength` (`number`, default `1`, range `-10`…`10`).
- **Replicate-LoRA model** (`face-to-many`): `custom_lora_url` (`string`, must be a Replicate `trained_model.tar` URL) + `lora_scale` (`number`, default `1`, range `0`…`1`).

**Multi-LoRA:** only on the preset+URL models (preset + `lora_2_url` + `lora_3_url`). **No `{path,scale}` array like fal.**

```json
// qwen-image-edit-plus-multi-lora
{
  "prompt": "Turn the camera to a top-down view.",
  "image_1": "https://.../input.webp",
  "lora": "multiple_angle",
  "lora_2_url": "https://huggingface.co/owner/repo/resolve/main/my-lora.safetensors"
}
```
> **⚠** Segmind's classic SD1.5/SDXL "Multi-LoRA" surface changed over time — verify the exact param on the specific model's `/api` page before wiring; do not assume a `loras[]` array.

---

## 6. Novita.ai — `request.loras: [{ "model_name", "strength" }]`  ✅ CONFIRMED

- `loras` (nested under `request`) — `array<object>` of `{ "model_name": <string>, "strength": <float> }`.
- `model_name` = **Novita's internal LoRA name** (the `sd_name_in_api` value). Get it from `GET` Model API with `filter.types=lora`. **NOT a URL** — you must use a Novita-hosted LoRA or upload your own (Model Upload, max 5/user).
- `strength` (`float`) — "The larger the value, the more biased the effect is towards lora. Range `[0, 1]`."
- **Multi-LoRA:** YES (array).
- Endpoint: `POST https://api.novita.ai/v3/async/txt2img` (v3 keeps `loras` inside `request`; a legacy flat form put `loras` at top level).

```json
{
  "request": {
    "model_name": "majicmixRealistic_v7.safetensors",
    "prompt": "a photo of a handsome man, close up",
    "width": 512, "height": 768, "steps": 30, "image_num": 1,
    "loras": [
      { "model_name": "add_detail_44319", "strength": 0.7 },
      { "model_name": "more_details_59655", "strength": 0.7 }
    ]
  }
}
```
> **KEY GOTCHA:** Novita will silently ignore a URL in `model_name`. It only resolves Novita-catalog LoRA names — upload first, then reference by name.

---

## 7. WaveSpeed AI — `loras: [{ "path", "scale" }]`  ✅ CONFIRMED

Same shape as fal.

- `loras` (`array`, optional, **max 3 items**). ⚠ One model description says "max 4" in prose but every schema table says **max 3** — treat 3 as the limit.
- `loras[].path` (`string`, required) — HF repo id `owner/model` (e.g. `strangerzonehf/Flux-Super-Realism-LoRA`) **or** a public `.safetensors` URL.
- `loras[].scale` (`float`, required) — range `0.0`…`4.0`.
- **Multi-LoRA:** YES (LoRA stacking, up to 3).
- Endpoints: `wavespeed-ai/flux-dev-lora`, `wavespeed-ai/flux-dev-lora-ultra-fast`, `wavespeed-ai/flux-2-dev/text-to-image-lora`, `wavespeed-ai/flux-2-klein-4b/text-to-image-lora`.
- Endpoint: `POST https://api.wavespeed.ai/api/v3/wavespeed-ai/<model>`.

```json
{
  "prompt": "a cinematic city at sunset, golden light",
  "loras": [ { "path": "strangerzonehf/Flux-Super-Realism-LoRA", "scale": 1.0 } ],
  "size": "1024*1024",
  "num_inference_steps": 28, "guidance_scale": 3.5, "num_images": 1, "seed": -1
}
```

---

## 8. Civitai as a LoRA SOURCE  ✅ CONFIRMED

Civitai is a *source*, not a generation provider you call for the tool's LoRA jobs. Two ways to reference a Civitai LoRA:

### 8a. Download URL (the portable form — feed to fal/Replicate/Together/WaveSpeed)
```
https://civitai.com/api/download/models/{modelVersionId}
```
- Uses the **model VERSION id**, not the model id. (Find it via `GET /api/v1/model-versions/{id}` → `downloadUrl`, or `mcp__civitai__get_download_url`.)
- **Auth for gated/login-required LoRAs:**
  - `?token=YOUR_API_TOKEN` query param (append `&token=…` if the URL already has params), OR
  - `Authorization: Bearer YOUR_API_TOKEN` header.
- The endpoint **302-redirects to a presigned S3 URL** — your HTTP client must follow redirects. Filename is in `Content-Disposition`.

### 8b. AIR identifier (Civitai-native generation only)
```
urn:air:{baseModel}:{type}:civitai:{modelId}@{versionId}[+{fileId}]
```
- Example (LoRA): `urn:air:flux1:lora:civitai:{modelId}@{versionId}`
- Real doc example (checkpoint): `urn:air:sdxl:checkpoint:civitai:827184@2514310`
- `{baseModel}` from the version's `baseModel` (`SDXL 1.0`→`sdxl`, `SD 1.5`→`sd15`, `Flux`→`flux1`); `{type}` = `lora` for LoRAs.
- **Easiest:** don't hand-build it — `GET /api/v1/model-versions/{id}` returns a ready `air` field; forward it verbatim.
- **⚠ AIR is consumed by Civitai's own Orchestration/generation API only.** fal, Replicate, Together, WaveSpeed, Novita do **not** accept `urn:air:` strings.

### 8c. Which providers accept a Civitai reference directly

| Provider | Civitai model-page URL (`civitai.com/models/…`) | Civitai download URL (`/api/download/models/{v}`) | AIR (`urn:air:`) | Needs HF mirror? |
|---|---|---|---|---|
| **Replicate** `flux-dev-lora` / `multi-lora` | ✅ yes (native, `civitai.com/models/{id}[/{ver}]`; token via `civitai_api_token` or `&token=`) | ✅ works | ❌ | No |
| **fal.ai** | ❌ | ⚠ only if URL resolves to raw `.safetensors` (+token) | ❌ | Usually yes |
| **Together** | ❌ | ⚠ only a direct `.safetensors` URL; no documented token param → | ❌ | Prefer HF |
| **WaveSpeed** | ❌ | ⚠ public direct `.safetensors` URL may work; no token param → | ❌ | Prefer HF |
| **Segmind** (`lora_2_url`/`lora_3_url`) | ❌ | ⚠ "public direct url" — a public Civitai download URL may work | ❌ | Prefer HF |
| **Novita** | ❌ (upload to Novita, use `model_name`) | ❌ | ❌ | Upload instead |
| **Civitai Orchestration** | — | — | ✅ native | — |

**Rule of thumb:** Replicate is the only listed provider that natively resolves Civitai *model-page* URLs. For everyone else, either (a) use a **direct `.safetensors` download URL** (public LoRAs, or with `?token=`), or (b) **mirror the LoRA to a public HuggingFace repo** and pass the HF URL/repo-id. AIR strings are Civitai-only.

`mcp__civitai__*` tools (`search_models`, `get_model_version`, `get_download_url`, `get_models_by_type` with type=LORA) are available for discovery — use `get_model_version` to read the `air` + `downloadUrl` + `files[]` for any versionId.

---

## Summary table

| Provider | LoRA param | Value shape of the reference | Multi? | Scale/strength param |
|---|---|---|---|---|
| **fal.ai** | `loras: [{path, scale}]` | `path` = `.safetensors` URL / HF repo-id / fal URL | ✅ any # (merged) | `scale` (float, default 1) |
| **Replicate** `flux-dev-lora` | `lora_weights` + `extra_lora` (strings) | Replicate `owner/model[/ver]`, HF URL, Civitai URL, `.safetensors` URL | ⚠ max 2 | `lora_scale`, `extra_lora_scale` (default 1, −1…3) |
| **Replicate** `flux-dev-multi-lora` | `hf_loras: [str]` + `lora_scales: [num]` | HF path / Replicate URL / Civitai URL (`&token=`) | ✅ up to 20 | `lora_scales[]` (default 0.8) |
| **HuggingFace** (diffusers, local) | `load_lora_weights(repo, weight_name, adapter_name)` + `set_adapters([...], adapter_weights)` | HF repo id + `weight_name` file | ✅ yes | `adapter_weights` (list<float>, default 1.0) |
| **HuggingFace** (Inference API) | `adapter_id` / `extra_body` (no task-schema body param) | HF repo id (`adapter_id`); else route to a provider | ⚠ limited/provider-dep | via provider |
| **Together.ai** | `image_loras: [{path, scale}]` | `path` = `.safetensors` URL (HF/Replicate/any) | ✅ up to 2 | `scale` (float, ~0.3–1.2) |
| **Segmind** (per-model) | `lora` (preset) + `lora_2_url` + `lora_3_url`; OR `finetune_id`+`lora_strength`; OR `custom_lora_url`+`lora_scale` | preset enum, or public/HF `.safetensors` URL, or Replicate `.tar` URL | ⚠ preset+2 URLs (model-dep) | `lora_strength` / `lora_scale` |
| **Novita.ai** | `request.loras: [{model_name, strength}]` | `model_name` = **Novita internal name** (NOT a URL) | ✅ yes | `strength` (float, 0…1) |
| **WaveSpeed AI** | `loras: [{path, scale}]` | `path` = HF repo-id `owner/model` or `.safetensors` URL | ✅ max 3 | `scale` (float, 0.0…4.0) |
| **Civitai** (source) | Download URL `…/api/download/models/{versionId}` OR AIR `urn:air:…:lora:civitai:{id}@{ver}` | versionId → download URL (redirects to S3); AIR = Civitai-native only | — | n/a (scale set by consuming provider) |

---

## Implementation flags / cautions

1. **fal / WaveSpeed / Together share the `{path, scale}` object shape** — but the KEY name differs: fal & WaveSpeed use `loras`, Together uses `image_loras`. Do not send `loras` to Together (silently ignored).
2. **Replicate has NO single shape** — branch on model. `flux-dev-lora` = flat `lora_weights`+`extra_lora` (max 2); `flux-dev-multi-lora` = `hf_loras[]`+`lora_scales[]` (max 20).
3. **Novita `model_name` ≠ URL** — it's a Novita-catalog name; arbitrary URLs are ignored. Upload custom LoRAs first.
4. **Segmind is fragmented** — no universal `loras[]` array; read each model's `/api` page. Preset `lora` values are fixed enums.
5. **HuggingFace hosted-inference LoRA is weak** — treat local `diffusers` (`load_lora_weights`+`set_adapters`) as the real path; for hosted, route `extra_body` to a real provider and use that provider's syntax.
6. **Together LoRA only on `FLUX.1-dev-lora` + `FLUX.2-dev`** — not Schnell/Pro/Kontext.
7. **Civitai:** only Replicate natively takes model-page URLs; everyone else needs a direct `.safetensors` download URL (public or `?token=`) or an HF mirror. `urn:air:` is Civitai-generation-only.
8. **⚠ WaveSpeed max-LoRA count** — schema tables say max **3**; one prose line says "max 4". Use 3.
9. **⚠ fal HF-repo-id** — confirmed as fal's standard usage pattern in examples/guides, but the one-line schema only literally says "URL or path"; direct `.safetensors` URL is the 100%-safe form.

---

## Sources (all fetched/verified 2026-07-20)

- fal.ai flux-lora schema: https://fal.ai/models/fal-ai/flux-lora/api ; docs: https://fal.ai/docs/model-api-reference/image-generation-api/flux-lora
- Replicate flux-dev-lora schema: https://replicate.com/black-forest-labs/flux-dev-lora/api/schema ; llms.txt: https://replicate.com/black-forest-labs/flux-dev-lora/llms.txt
- Replicate "Working with LoRAs" guide: https://replicate.com/docs/guides/extend/working-with-loras
- Replicate multi-lora: https://replicate.com/lucataco/flux-dev-multi-lora/api (+ /readme)
- HuggingFace diffusers Load adapters / LoRA / PEFT for inference: https://huggingface.co/docs/diffusers/en/tutorials/using_peft_for_inference ; https://huggingface.co/docs/diffusers/main/en/using-diffusers/loading_adapters ; https://huggingface.co/docs/diffusers/en/api/loaders/lora
- HuggingFace Inference Providers text-to-image task + InferenceClient (`adapter_id`, `extra_body`): https://huggingface.co/docs/inference-providers/main/tasks/text-to-image ; https://huggingface.co/docs/huggingface_hub/en/package_reference/inference_client
- HF dynamic LoRA (legacy `lora:` header): https://huggingface.co/blog/lora-adapters-dynamic-loading
- Together.ai FLUX LoRA quickstart + params: https://docs.together.ai/docs/quickstart-flux-lora ; https://docs.together.ai/docs/inference/images/parameters ; https://docs.together.ai/docs/inference/images/overview
- Segmind model API pages: https://www.segmind.com/models/qwen-image-edit-plus-multi-lora/api ; /flux-dev-finetuned/api ; /face-to-many/api
- Novita txt2img API + LoRA + custom-model upload + v2→v3 migration: https://novita.ai/docs/api-reference/model-apis-txt2img ; https://novita.ai/docs/guides/model-apis-custom-model ; https://novita.ai/docs/guides/model-apis-v2-to-v3-migration
- WaveSpeed flux-dev-lora / ultra-fast / flux-2 lora: https://wavespeed.ai/docs/docs-api/wavespeed-ai/flux-dev-lora (+ -ultra-fast, /flux-2-dev-text-to-image-lora, /flux-2-klein-4b-text-to-image-lora)
- Civitai AIR guide + model-versions ref + download guide: https://developer.civitai.com/site/guide/air ; https://developer.civitai.com/site/reference/model-versions ; https://education.civitai.com/civitais-guide-to-downloading-via-api/
