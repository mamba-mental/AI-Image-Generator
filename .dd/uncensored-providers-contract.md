# dd-router contract — Wire uncensored providers (Phase 3)

**Slug:** uncensored-providers
**Repo:** mamba-mental/AI-Image-Generator
**Verify:** `.dd/verify_providers.py` (python, structural + key-gated live) + `scripts/verify_content_mode.js` (node, per-provider polarity)

## Problem
fal blacks out NSFW output server-side on open-weight models. Research (`research/2026-07-20_nsfw-providers-and-model-availability.md`) found the uncensored route is **host + model class**, not a magic param: run open-weight models on providers that let their own GPUs return the image. Wire the ranked providers — **Together** (already a backend, `disable_safety_checker`), **Runware** (`checkNSFW:false`, CivitAI + LoRA), **Novita** (`enable_nsfw_detection` opt-in) — with each provider's EXACT disable-safety param and correct polarity.

## Acceptance criteria (RED → GREEN)

- **AC-1 — Backends registered.** `engine.backends.BACKENDS` contains `together`, `runware`, `novita`, each a callable with signature `generate(model_id, params, progress, cancel_event)`.
- **AC-2 — Keys resolvable.** `engine.config.KEY_FIELDS` maps `runware`→`RUNWARE_API_KEY`, `novita`→`NOVITA_API_KEY` (together already present).
- **AC-3 — Services surfaced.** `Api.get_state()["services"]` includes `together`, `runware`, `novita`; `service_params.json` has a `default` schema for `runware` + `novita` declaring their safety flag; `recent_models` seeds each.
- **AC-4 — Correct disable-safety param in the request body (structural, per provider):**
  - Together → `body["disable_safety_checker"] == True` when passed (backend already forwards it).
  - Runware → `_build_task(...)["checkNSFW"] == False` when `checkNSFW=False` is passed.
  - Novita → `_build_body(...)["request"]["enable_nsfw_detection"] == False` when passed (nested under `request`, not top-level).
- **AC-5 — Content-mode polarity (JS).** `applyContentMode({}, model, "nsfw", svc)` yields the ALLOW value and `"safe"` yields the MODERATE value for each: together `disable_safety_checker` true/false; runware `checkNSFW` false/true; novita `enable_nsfw_detection` false/true. `isRelaxable(model, svc)` is true for all three (shown in NSFW mode).
- **AC-6 — Response parsing (structural).** Runware `_parse({"data":[{"imageURL":u}]})==[u]`; Novita `_imgs({"images":[{"image_url":u}]})==[u]`; both return an `"<svc> Error: …"` string list on an empty/error response.
- **AC-7 — Live uncensored render (key-gated).** If `TOGETHER_API_KEY` is set, generating an open model (FLUX.1-schnell/dev) on the benchmark nude prompt with `disable_safety_checker=True` returns a **viewable (non-black)** image (brightness classifier mean>12 or sd>8). Skipped (not failed) when the key is absent; same optional probe for Runware/Novita when their keys exist.

## Verify plan
`scripts/verify_content_mode.js` extended with AC-5 (node, pure). `.dd/verify_providers.py` asserts AC-1,2,3,4,6 by importing the backends + `_build_task`/`_build_body`/`_parse`/`_imgs` and reflecting registration/config/state; AC-7 runs only when a key is present (downloads the result + brightness-classifies). Prints `[PASS]/[FAIL]`; exit non-zero on any structural fail (a skipped live probe is not a fail).
