# Batch D — Providers (items #13, #1, #12, #11, #3) — dd-router contract

Status: RED (author before build; verify_pD.py RED→GREEN per item)

## #13 — Multi-key pool + auto-swap
- AC-13.1: `engine/keypool.py` builds a per-service key pool from env (primary + `<ENV>_2..9` + comma `<ENV>S`/`_POOL`) and config; `current/rotate/size`; keys never hardcoded.
- AC-13.2: `config.resolve_keys` populates the pools; status reflects pool size>0.
- AC-13.3: `jobs._run` retries with the next key on a rate-limit/auth error (401/403/429/quota) up to pool size.
- Runtime: simulated key1-429 → rotate → key2 success (fake backend, real JobRegistry).

## #1 — Max-coverage NSFW posture
- AC-1.1: in-app reference map provider→policy→config (`NSFW_POLICY` in app.js) rendered in a reachable panel.
- AC-1.2: a global "allow mature content" toggle injects permissive safety params for fal (enable_safety_checker=false, safety_tolerance=max) into the request.
- AC-1.3: the dead `FLUX_DISABLE_SAFETY` env flag is wired — fal backend honors it as the default for enable_safety_checker when the model supports it and it's unset.
- Runtime: toggle ON → collectParams includes enable_safety_checker=false; fal _build_args passes it through; DOM shows the policy reference.

## #12 — Per-provider prompting refs + negative-prompt gating
- AC-12.1: `PROMPT_GUIDE` map (per model family) with sourced guidance in app.js.
- AC-12.2: params UI shows the active model's prompting guidance; negative-prompt field visibility gated by family (FLUX/gpt-image hide; SDXL/Seedream/Imagen show).
- Runtime: switching model changes the guidance text + negative-field visibility.

## #11 — OpenRouter backend
- AC-11.1: `engine/backends/openrouter_api.py` — image via `/v1/images` + chat-image via `/chat/completions`; registered in BACKENDS; "openrouter" in the service list.
- AC-11.2: key from env `OPENROUTER_API_KEY` (never hardcoded); a curated model or the models endpoint.
- Runtime: one real OpenRouter image generation returns a saved file (or a clear, logged provider error if the key/model is unavailable — negative path).

## #3 — Img→prompt integration
- AC-3.1: method chosen via /oracle; reuse fal image-to-text/caption; not a rebuild.
- AC-3.2: from the lightbox (or a control), "analyze image → prompt" produces an editable prompt that can seed a generation.
- Runtime: select an image → get a regenerated prompt → it lands in the prompt box.

## Evidence rule
Each AC: file:line + code + runtime receipt. Ledger GREEN only on observed evidence. Keys from env/credential store only.
