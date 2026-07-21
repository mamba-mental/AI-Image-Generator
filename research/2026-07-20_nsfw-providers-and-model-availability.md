# NSFW-Permitting Image-Gen Providers & Model Availability

**For:** AI Studio Void (private image-gen tool, PRIME's own paid API accounts)
**Date:** 2026-07-20
**Scope:** API/provider research only. No images generated. Adult NSFW image generation is legal; this is a sourcing document for uncensored hosting.
**Confidence tags:** ✅ verified against provider docs · 🟡 strong secondary evidence · ⚠️ uncertain / verify before wiring.

---

## TL;DR — read this first

The problem is **not** "safety checker" flags. It's **which layer moderates and whether you can reach the raw weights.** Two distinct things:

1. **BFL *proprietary* models** — FLUX 1.1 [pro], FLUX.2 [pro]/[max]/[flex], FLUX.1 Kontext [pro]/[max]. Every reseller (fal, Together, Replicate, DeepInfra, Novita, WaveSpeed) is a **thin proxy to Black Forest Labs' own hosted API**, and BFL runs moderation server-side. These are **moderated everywhere — no host can uncensor them.** Do not fight this; pick a different model for NSFW.
2. **Open-weight models** — FLUX.1 [schnell/dev], FLUX.2 [klein/dev], all SDXL/SD1.5/Pony/community fine-tunes. The provider runs these **on its own GPUs from open weights**, so moderation is the *provider's choice*, not a license mandate. **fal chose to wrap FLUX output in a non-optional NSFW classifier (the blackout you see) even when `enable_safety_checker=false`.** The fix is simply to run the same open weights on a provider that lets you turn the classifier off: **Together, Replicate, Runware, Novita.**

**The move:** for NSFW, use open-weight models (SDXL/Pony/SD1.5/community-FLUX-fine-tunes, or raw FLUX.1 dev/schnell) on **Together (already wired), Runware, or Novita.** Leave fal for the BFL-proprietary polished renders where it isn't blacking out.

**Ranked providers to wire:** ① Together.ai (proven) → ② Runware → ③ Novita.ai → ④ Replicate → ⑤ DeepInfra. Turnkey NSFW fallbacks: ModelsLab, Hypereal, Prodia.

---

## Part A — Top NSFW-permitting models + the providers that host them uncensored

Price = per 1024² image unless noted; sourced from provider pages / pricepertoken.com (2026-07). "Moderates output?" = does that host blackout/block NSFW *by default* on that model.

| # | Model | Best uncensored host | Moderates output? | Disable flag (exact) | API shape | Auth header | ~$/image |
|---|-------|----------------------|-------------------|----------------------|-----------|-------------|----------|
| 1 | **FLUX.1 [schnell]** (Apache-2.0) | Together / Runware / Novita / DeepInfra | No (open weights; providers don't force a classifier) | Together: `disable_safety_checker:true` ✅ · Runware: `checkNSFW:false` (default) ✅ | OpenAI-compat REST + SDK | `Authorization: Bearer` | $0.0005–0.008 |
| 2 | **FLUX.1 [dev]** | Replicate / Together / Runware / Novita | No, if flag set (fal DOES blackout) | Replicate `disable_safety_checker:true` ✅ · Together same ✅ | async-queue (Replicate) / OpenAI-compat (Together) | `Bearer` / `Token` | $0.009–0.025 |
| 3 | **SDXL base 1.0 (fast-sdxl)** (OpenRAIL++) | Runware / Replicate / DeepInfra / Novita | No | Replicate `disable_safety_checker:true` ✅ · Runware `checkNSFW:false` ✅ | REST | `Bearer`/`Token` | $0.0002–0.0043 |
| 4 | **Pony Diffusion V6 XL** (SDXL, NSFW-native) | Runware (`civitai:` AIR) / Replicate community / Prodia | No | Runware `checkNSFW:false` (default off) ✅ | REST | `Bearer` | ~$0.0013–0.006 |
| 5 | **SD 1.5** + NSFW fine-tunes (largest ecosystem) | Novita / Runware / Prodia | No (Novita `enable_nsfw_detection` is opt-**in**) ✅ | Novita: just omit `enable_nsfw_detection` | async REST | `Bearer` | $0.001–0.0015 |
| 6 | **Realistic Vision v5/v6** (SD1.5/SDXL, photoreal) | Novita / Runware / ModelsLab | No | Runware `checkNSFW:false` | REST | `Bearer` | $0.001–0.006 |
| 7 | **DreamShaper / DreamShaper XL** | Novita / Runware / Prodia | No | (default off) | REST | `Bearer` | $0.001–0.006 |
| 8 | **Juggernaut XL / Juggernaut-Flux** (RunDiffusion) | Together / DeepInfra / Runware | No (open fine-tune) | Together `disable_safety_checker:true` | OpenAI-compat REST | `Bearer` | $0.0017–0.009 |
| 9 | **CyberRealistic (SDXL NSFW fine-tune)** | Runware (`civitai:`) / dedicated NSFW hosts | No | `checkNSFW:false` | REST | `Bearer` | ~$0.0013–0.006 |
| 10 | **SDXL Lightning (4-step)** (ByteDance) | DeepInfra / Runware / Replicate | No | `disable_safety_checker`/`checkNSFW:false` | REST | `Bearer`/`Token` | $0.0002–0.002 |
| 11 | **Playground v2.5 1024 aesthetic** (open) | Replicate / Runware | No | `disable_safety_checker:true` | async-queue | `Token` | ~$0.003–0.01 |
| 12 | **Sana / Sana Sprint** (NVIDIA, open, fast) | Runware / self-host | No (on Runware) | `checkNSFW:false` | REST | `Bearer` | ~$0.001–0.006 |
| 13 | **Lumina Image 2.0** (Alpha-VLLM, open) | Replicate / self-host | No | `disable_safety_checker:true` | async-queue | `Token` | ~$0.006–0.01 |
| 14 | **Illustrious XL / WAI-NSFW-Illustrious** (anime NSFW) | Runware (`civitai:`) / dedicated hosts | No | `checkNSFW:false` | REST | `Bearer` | ~$0.0013–0.006 |
| 15 | **FLUX.2 [klein] 4B / 9B** (open half of FLUX.2) | Runware / DeepInfra / Replicate / Hypereal | No on open-weight hosts; **fal wraps it** | Runware `checkNSFW:false` · Hypereal permissive policy | REST / OpenAI-compat | `Bearer` | $0.012–0.015 |
| 16 | **FLUX.1 SRPO [dev]** (Tencent SRPO fine-tune, open) | self-host / Runware / Replicate community | No | model-dependent (`disable_safety_checker`/`checkNSFW`) | REST | `Bearer`/`Token` | ~$0.009–0.02 |
| 17 | **Hunyuan Image 3.0** (Tencent, open weights) | DeepInfra / Novita / self-host | ⚠️ mostly no on open hosts; verify | provider-dependent | REST | `Bearer` | ~$0.02–0.04 |
| 18 | **"Uncensored FLUX LoRA"** (ModelsLab turnkey) | ModelsLab | No (API doesn't gate; account-policy only) 🟡 | none needed | REST | `key` in body | subscription |
| 19 | **FLUX.1 [dev] + ControlNet/LoRA (flux-general)** | Runware / Replicate / Together (`image_loras`) | No, flag set | Runware `checkNSFW:false` · Replicate `disable_safety_checker:true` | REST | `Bearer`/`Token` | $0.012–0.042 |
| 20 | **FLUX.2 [dev] + LoRA / comic-art LoRA** | Runware / Together (`image_loras`) / DeepInfra | No on open-weight hosts | Together `disable_safety_checker:true` · Runware `checkNSFW:false` | OpenAI-compat / REST | `Bearer` | $0.0084–0.03 |

**Dedicated NSFW-first API hosts** (turnkey, no jailbreak, but less model control / higher floor):
- **ModelsLab** — `model_id="uncensored-flux-lora"` etc.; API does not enforce the web-playground NSFW gate ✅ (verify account policy). REST, key in body.
- **Hypereal** (hypereal.cloud) — FLUX 2 family (klein/pro/max/Kontext/Krea) via one **OpenAI-compatible** image API; published *creator-calibrated* policy (allows fine-art nudity / mature editorial; hard limits stay hard). Klein **$0.015/img**, no daily cap. 🟡
- **Prodia** — SD1.5/SDXL/FLUX, one-request REST (no polling), historically NSFW-permissive, **from $0.001/img**. 🟡
- **each::labs** (eachlabs.ai) — `enable_safety_checker:false` documented for image/video. 🟡
- **NSFW Coders / ZenCreator / nocensor.ai / DreamGenArt** — B2B or browser platforms; NSFW Coders is enterprise ($5k+/mo) with 2257/PhotoDNA compliance baked in. Overkill for a personal tool but exist if a fully-managed adult stack is ever wanted.

---

## Part B — Availability & pricing matrix for the 25 fal-moderated models

Columns: **Uncensored host(s)** = where you can run it without a forced blackout · **Uncensored?** = can moderation be turned off there · **~$/img** · **Self-hostable (open weights)?**

| Model (fal id) | Uncensored host(s) | Uncensored there? | ~$/img | Self-hostable? |
|----------------|--------------------|--------------------|--------|----------------|
| **FLUX.1 [schnell]** | Together, Runware, Novita, DeepInfra, Replicate | ✅ Yes (`disable_safety_checker`/`checkNSFW:false`). Note: Together's flag does **not** apply to *FLUX Schnell **Free*** tier | $0.0005–0.008 | ✅ Yes — Apache-2.0 |
| **FLUX.1 [dev]** | Replicate, Together, Runware, Novita, DeepInfra | ✅ Yes (flag). fal blacks it out; others don't | $0.009–0.025 | ✅ Yes — FLUX.1-dev Non-Commercial license |
| **FLUX.1 SRPO [dev]** | Runware, Replicate (community), self-host | ✅ Yes | ~$0.009–0.02 | ✅ Yes — open (Tencent SRPO fine-tune of FLUX.1 dev) |
| **FLUX.2 [klein] 4B** | Runware, DeepInfra, Replicate, Hypereal | ✅ Yes on open-weight hosts | $0.012 | ✅ Yes — FLUX.2 Non-Commercial/Pro-Commercial |
| **FLUX.2 [klein] 9B** | Runware, DeepInfra, Replicate, Hypereal | ✅ Yes | $0.015 | ✅ Yes |
| **FLUX.2 Turbo** | ⚠️ fal-branded accelerated endpoint | ⚠️ underlying ~FLUX.2 klein distillation — self-host klein for equivalent; the Turbo tuning itself is fal-proprietary | ~$0.005–0.008 | ⚠️ Partial — base weights yes, fal's distillation no |
| **FLUX.2 Flash** | ⚠️ fal-branded accelerated endpoint | ⚠️ same as Turbo | ~$0.005–0.008 | ⚠️ Partial |
| **FLUX 2 Lora** (FLUX.2 dev + LoRA) | Runware, Together (`image_loras`), DeepInfra | ✅ Yes | $0.0084–0.03 | ✅ Yes — open base + community LoRA |
| **Stable Diffusion XL (fast-sdxl)** | Runware, Replicate, DeepInfra, Novita | ✅ Yes | $0.0002–0.0043 | ✅ Yes — OpenRAIL++ |
| **SDXL Lightning** | DeepInfra, Runware, Replicate | ✅ Yes | $0.0002–0.002 | ✅ Yes — ByteDance, open (SDXL fine-tune) |
| **FLUX.1 Kontext [pro]** | ❌ none — BFL proprietary API-only | ❌ Moderated everywhere (BFL-side) | $0.040–0.042 | ❌ No — closed |
| **FLUX.1 Kontext [max]** | ❌ none — BFL proprietary API-only | ❌ Moderated everywhere | $0.080–0.084 | ❌ No — closed |
| **FLUX.1 [dev] + ControlNets+LoRAs (flux-general)** | Runware, Replicate, Together | ✅ Yes (`disable_safety_checker`/`checkNSFW:false`) | $0.012–0.042 | ✅ Yes — open base |
| **Hunyuan Image (v3)** | DeepInfra, Novita, self-host | 🟡 Mostly yes on open hosts — verify | ~$0.02–0.04 | ✅ Yes — Tencent open weights |
| **Playground v2.5** | Replicate, Runware | ✅ Yes | ~$0.003–0.01 | ✅ Yes — Playground v2.5 1024 aesthetic, open |
| **Stable Diffusion v1.5** | Novita, Runware, Prodia | ✅ Yes (biggest NSFW ecosystem) | $0.001–0.0015 | ✅ Yes — open (CreativeML OpenRAIL-M) |
| **Realistic Vision** | Novita, Runware, ModelsLab | ✅ Yes | $0.001–0.006 | ✅ Yes — community SD1.5/SDXL fine-tune (CivitAI) |
| **Sana Sprint** | Runware, self-host | ✅ Yes | ~$0.001–0.006 | ✅ Yes — NVIDIA Sana, open (MIT/NVIDIA) |
| **Lumina Image 2** | Replicate, self-host | ✅ Yes | ~$0.006–0.01 | ✅ Yes — Alpha-VLLM, open |
| **Dreamshaper** | Novita, Runware, Prodia | ✅ Yes | $0.001–0.006 | ✅ Yes — community SD/SDXL fine-tune (CivitAI) |
| **Rundiffusion Photo Flux** | Together/DeepInfra (Juggernaut-Flux line), Runware | 🟡 Yes on open FLUX-dev fine-tune hosts — verify exact checkpoint | ~$0.009–0.017 | 🟡 Partial — some RunDiffusion FLUX fine-tunes open on HF, some hosted-only |
| **Flux 2 Lora Gallery — digital-comic-art** | Runware, Together (`image_loras`) | ✅ Yes | $0.0084–0.03 | ✅ Yes — FLUX.2 open base + community comic LoRA |

**Reading the matrix:** everything ✅ is an open-weight model you can run uncensored on Together / Runware / Novita / Replicate today. The only two hard ❌ are **Kontext [pro]/[max]** — BFL closed API, moderated at BFL regardless of host (as you already suspected). The ⚠️ rows (FLUX.2 Turbo/Flash) are fal's own accelerated brandings; substitute self-hostable **FLUX.2 [klein]** for equivalent open, uncensorable output.

---

## Recommended providers to wire (ranked)

1. **Together.ai** ✅ — *already proven by you.* OpenAI-compatible (`base_url=https://api.together.xyz/v1`), `Authorization: Bearer $TOGETHER_API_KEY`, `disable_safety_checker:true`. Cheapest FLUX schnell/dev + SDXL + FLUX.2 dev/flex + LoRA (`image_loras`). **Make this the NSFW default path.** Only gaps: FLUX Schnell *Free* tier and FLUX [pro] (BFL) ignore the flag → route those to a paid non-free model.
2. **Runware** ✅ — cheapest per-image ($0.0006–), single REST endpoint (`https://api.runware.ai/v1`, `Bearer`), **thousands of CivitAI community models** addressable by `civitai:<id>@<ver>` AIR (Pony, CyberRealistic, Illustrious, Realistic Vision, etc.), full LoRA/ControlNet/IP-Adapter. `checkNSFW` defaults **off** → no blackout; it only *labels* (`NSFWContent:true`) when you opt in. **Best for community NSFW checkpoints + LoRA stacking.**
3. **Novita.ai** ✅ — NSFW detection is **opt-in** (`extra.enable_nsfw_detection`; omit it = no moderation). Async REST (`/v3/async/txt2img`, `Bearer`), SD1.5/SDXL/FLUX + LoRA/ControlNet/embeddings, very cheap ($0.001–0.02). Strong second REST backend.
4. **Replicate** ✅ — `disable_safety_checker:true` (**API-only**, boolean, default false) on flux-dev, SDXL, RealVisXL, and *all derivative fine-tunes*. Async-queue (`Authorization: Token`). Huge community-model catalog incl. NSFW fine-tunes; downside = higher price + cold-starts. Good for niche checkpoints not on Runware.
5. **DeepInfra** 🟡 — flat, cheapest per-image on open SDXL/FLUX-schnell/dev; no forced output classifier on open models; OpenAI-ish REST. BFL proprietary models still moderated. Good cheap batch fallback.

**Turnkey NSFW fallbacks (no model plumbing):** ModelsLab (`uncensored-flux-lora`), Hypereal (FLUX 2 family, OpenAI-compat, permissive policy), Prodia (from $0.001/img).

**Avoid for NSFW:**
- **fal.ai** — current problem; forced FLUX output classifier blacks out NSFW even with `enable_safety_checker:false`. Keep only for BFL-proprietary polished renders.
- **WaveSpeed AI** — mirrors fal's schema *and* its behavior; Reddit reports the "Enable Safety Checker" toggle is **locked** on every model in its sandbox → same blackout on FLUX. ⚠️ Not a fix.
- **Fireworks AI** — content policy + no documented disable flag on image output; moderated.
- **NVIDIA NIM (build.nvidia.com)** — NeMo Guardrails, safety-first, and **records your inputs/outputs** on the hosted trial API. Do not send NSFW.
- **HuggingFace Inference** — now a *router to partner providers* (fal/replicate/together/nebius…) → inherits whichever partner's moderation. Use HF only to **download open weights for self-hosting**, not as an inference endpoint.

---

## Exact disable-safety cheat-sheet (per provider)

| Provider | Param | Type / default | Behavior | Exceptions |
|----------|-------|----------------|----------|------------|
| **Together.ai** | `disable_safety_checker` | bool, `false` | Disables built-in NSFW checker; without it, triggering content → **HTTP 422** | ✅ Confirmed: runs on **every model except FLUX Schnell *Free* and FLUX [pro]** |
| **Replicate** | `disable_safety_checker` | bool, `false` | Disables checker; **API-only** (web UI always filters). "Outputs will not be deterministic when disabled." | On/for SDXL, flux-dev + all derivative fine-tunes. BFL proprietary (flux-1.1-pro, kontext) still BFL-moderated |
| **Runware** | `checkNSFW` | bool, **default off** | When *off* (default) = no check, raw image. When *on* = returns `NSFWContent:true` flag (and historically a blacked frame on flagged content) → **just leave it off** | Community/open models only; BFL proprietary via `providerSettings` inherits BFL policy |
| **Novita.ai** | `extra.enable_nsfw_detection` (+ `nsfw_detection_level`) | bool, **opt-in** | Detection only runs if you set it `true`; default = **no moderation**, returns raw | — |
| **DeepInfra** | *(none needed)* | — | No forced output classifier on open models | BFL proprietary still moderated |
| **each::labs** | `enable_safety_checker` | bool | Set `false` | — |
| **fal.ai** | `enable_safety_checker` | bool | ❌ Does **not** stop the forced FLUX output blackout — this is the failure you hit | — |
| **WaveSpeed AI** | `enable_safety_checker` | bool | ⚠️ Reportedly locked in-sandbox; mirrors fal | — |

---

## Sources

- Together.ai image parameters (disable_safety_checker, model exceptions, 422) — https://docs.together.ai/docs/inference/images/parameters ✅ · overview https://docs.together.ai/docs/inference/images/overview
- Replicate safety-checking docs — https://replicate.com/docs/topics/predictions/safety-checking ✅ · flux-dev API schema (`disable_safety_checker boolean False`) https://replicate.com/black-forest-labs/flux-dev/.../api · realvisxl-v3.0-turbo ("only available through the API")
- Runware JS/TS SDK (`checkNSFW?: boolean`, `NSFWContent?`) — https://github.com/Runware/sdk-js ✅ · pricing ($0.0006–0.24/img) https://runware.ai/pricing · model-search `civitai:` AIR https://runware.ai/docs/platform/model-search
- Novita.ai txt2img API (`enable_nsfw_detection` opt-in) — https://novita.ai/docs/api-reference/model-apis-txt2img ✅ · pricing https://novita.ai/pricing · https://novita.ai/model-api/product/img2img · "turn off SD filter" blog https://blogs.novita.ai/turn-off-stable-diffusion-filter/
- DeepInfra Stable Diffusion / FLUX.2 — https://docs.deepinfra.com/tutorials/stable-diffusion · https://deepinfra.com/blog/bfl-flux2-release
- Cross-provider per-image pricing — https://pricepertoken.com/image (FLUX/SDXL/FLUX.2 prices, DeepInfra flat, Together, Replicate, fal)
- Segmind pricing/blog (flux-schnell ~$0.008, GPU-sec billing) — https://www.segmind.com/pricing · https://blog.segmind.com/flux-generation-cost-across-5-models-for-ai-images/
- Prodia (from $0.001/img, one-request REST) — https://prodia.com/ · https://prodia.readme.io/reference/generate · https://www.tooljunction.io/ai-tools/prodia
- WaveSpeed AI (`enable_safety_checker`, locked-toggle report) — https://wavespeed.ai/docs/docs-api/wavespeed-ai/flux-dev · https://www.reddit.com/r/StableDiffusion/comments/1r7k4gv/wavespeedai_safety_checker/
- NVIDIA NIM safety/guardrails + I/O recording — https://build.nvidia.com/explore/safety-moderation · https://blogs.nvidia.com/blog/nemo-guardrails-nim-microservices/
- Fireworks FLUX/SDXL — https://docs.fireworks.ai/faq-new/models-inference/flux-image-generation
- Open-weight license/filter status (which models ship filters) — https://localaimaster.com/blog/uncensored-local-image-generation · Hypereal FLUX 2 Klein permissive policy https://hypereal.cloud/a/flux-2-klein-no-restrictions
- ModelsLab uncensored-flux-lora (API ≠ web NSFW gate) — https://modelslab.com/models/modelslab/uncensored-flux-lora/api
- each::labs `enable_safety_checker:false` — https://docs.eachlabs.ai/api/nsfw-content
- Dedicated NSFW hosts (context) — nocensor.ai, zencreator.pro, dreamgenart.com, nsfwcoders.com

**Verification notes / uncertainty flags:**
- ✅ Together, Replicate, Runware, Novita disable-mechanisms verified against their own docs/SDK.
- 🟡 Segmind, Prodia, ModelsLab, Hypereal NSFW *output* stance is strong-secondary, not a quoted "we don't blackout" clause — confirm with one test image before relying on them for volume.
- ⚠️ FLUX.2 Turbo/Flash internals (which open base) not documented by fal — treat as fal-proprietary; use FLUX.2 [klein] for self-hostable equivalent.
- ⚠️ WaveSpeed flag behavior is from a user report, not the docs — verify if you ever consider it (recommend you don't; it mirrors fal).
- ❌ Kontext [pro]/[max] and FLUX.2 [pro]/[max]: moderated at BFL, uncensorable on any reseller — confirmed by the proprietary-API architecture, not a workaround anyone has.
