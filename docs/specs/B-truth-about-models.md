# Spec B — Truth about models (dynamic catalogs · real NSFW testing · per-model content grading)

**Cluster:** #1 + #2 + #5 · **Type:** architecture + empirical research
**Core problem:** *the app does not know what each provider actually offers, or what it actually allows.*
**Refined:** 2026-07-21 via refine-to-spec (external judge gpt-5.2, pinned). Baseline **73 → 86 → 92/100** — cleared the 90 target (axes: #1 catalogs 93, #2 NSFW 91, #5 grading 92). Build-time detail to pin in the §0 sheet (judge nice-to-haves, non-blocking): per-provider id-acceptance endpoint/params + error-code→ACCEPTED/FAIL/INCONCLUSIVE map; fal classifier request/response schema + a pinned NSFW-vote threshold so `classifier_scores[]` are comparable over time; a model-identity/alias rule for catalog drift (renamed `id`, same underlying model → alias, not a new row).

## Current state (verified 2026-07-20)
| Provider | Model list source | Honest status |
|---|---|---|
| fal | fal explore API → `engine/fal_models.json` (1,322) | ✅ genuinely dynamic |
| novita | `GET /v3/model?type=checkpoint` (100) | ⚠️ dynamic but **legacy SD1.5/SDXL checkpoints only** — the 21 modern "Model APIs" (Seedream 5.0/4.5/4.0, Qwen-Image, Flux Kontext dev/pro/max, ZZ Image Turbo, upscaler/eraser/inpaint) are absent (not in `/v3/model`, not in `/openai/v1/models`) |
| together, runware, cliproxy, agnes, ideogram, openai, nvidia, gemini | **hardcoded seed lists in `bridge.py`** | ❌ guesses |

- **NSFW testing:** only the 95 fal t2i models were empirically probed, with a mild prompt. Novita/Together/Runware/AGNES/Ideogram: zero testing.
- **Content grading:** `content_capability` exists only for fal. Non-fal services are treated as uniformly "permissive" if they expose a disable flag — never per model.

## Benchmark prompt (PRIME's real prompt — the capability signal)
> A photorealistic fine-art nude photograph of a young East Asian woman with long straight black hair… kneeling in profile on a leaf-strewn stone-paved walkway… nude with smooth oiled skin, full breasts and erect nipples visible… glossy black stiletto high heels… classical stone facade… stone statue of Jesus Christ… vintage street lamp… cinematic editorial photography, 50mm, 3:2, 8k. *(full text stored in `engine/nsfw_benchmark_prompt.txt`; >1024 runes)*

## §0 — Provider integration sheet (the missing execution detail — gap #1)
A per-provider table maintained in `research/2026-07-21_provider-catalog-endpoints.md`, filled from **primary docs** before any code, with columns:
`provider · catalog_endpoint(s) · auth (header + key env) · pagination (param + cursor field) · response schema (model-name field, price field) · rate limit · known error codes · has-live-catalog? (Y/N) · fallback if N · evidence`.

- **"has-live-catalog? = Y" requires POSITIVE evidence** — a real request that returned a non-empty model list, with the captured response pasted in the `evidence` column. "I didn't find one" is **not** proof of absence.
- **"has-live-catalog? = N" requires a cited absence** — a link to the provider's API-reference index showing no list/models/catalog endpoint exists (adversarially confirmed against that index, not merely "not found by me"). This directly serves PRIME's "must be checked for ALL providers": absence is *demonstrated*, never assumed.
- Confirmed facts the sheet must encode:
  - **Novita — checkpoints:** live catalog `GET /v3/model?type=checkpoint` (verified, 100 rows). **has-live-catalog = Y.**
  - **Novita — modern "Model APIs"** (Seedream/Qwen-Image/Flux-Kontext/ZZ-Turbo/upscaler/eraser): verified **absent** from both `/v3/model` and `/openai/v1/models` (2026-07-20). Novita documents these as a **fixed, per-model endpoint set** with no list API → **has-live-catalog = N**, fallback = curated-from-docs offline seed (AC-1.7), each `model_name` cited to its Novita doc page. This is the honest, execution-ready resolution — *not* "endpoint TBD."
  - **Together / Runware / AGNES:** catalog endpoints currently **unverified**; §0 must return either positive evidence (Y) or a cited absence (N) per the two rules above before any of them is wired.

## §1 — Live catalogs (fixes #1)

- **AC-1.1 — No hardcoded primary lists, enforced.** Each wired provider has a `<svc>_models()` fetch against its real endpoint (per §0). The only permitted static arrays are in files named `engine/offline_seeds/<svc>.json`, each labelled `"_note": "offline fallback only"`. A CI/lint check (`scripts/lint_no_hardcoded_models.py`, run in `verify_catalogs.py`) **fails if a model-name array literal appears in `bridge.py`/backends outside `offline_seeds/`.**
- **AC-1.2 — Novita exposes BOTH catalogs.** Legacy checkpoints AND the modern Model-APIs, each via its correct endpoint, surfaced as **two labelled groups** in the dropdown (e.g. "Novita · Checkpoints" / "Novita · Model APIs"). Duplicates de-duped by id. If one catalog fetch fails, the other still renders (partial-failure tolerated) with a visible note.
- **AC-1.3 — Completeness, not first-page.** The fetch **pages through all results** (per §0 pagination) and records `fetched_count` vs any provider-reported `total`; a mismatch logs a truncation warning. A shown model that was truncated-away is a failure of this AC.
- **AC-1.4 — Common `ModelDescriptor`.** Every catalog entry normalizes to: `{id, label, category, provider, price?, max_prompt_runes?, sizes?/aspect_ratios?, safety_modes?, image_limit?, family?}`. Required: `id, label, category, provider`. Missing optionals are `null`, never guessed. The dropdown shows price when present (parity with fal).
- **AC-1.5 — Caching + refresh.** Catalogs cache to `.cache/catalogs/<svc>.json` with a `fetched_at` + TTL (default 24h); a visible "↻ refresh" forces a re-fetch. A fetch failure **degrades to the last cached list** (never an empty dropdown) and shows a stale badge.
- **AC-1.6 — Generatable: ID-validity for ALL + render-sample for N.** Two tiers, because PRIME's #1 is "every dropdown entry is real, for ALL models":
  - **All models (cheap):** every catalog `id` is checked for *acceptance* by the provider — submitted to the generate/validate endpoint (dry-run or cheapest params) and asserted to be **accepted** (not a `model not allowed`/`unknown model`/404). A rejected id is a catalog-parse/rename bug and **fails** this AC. No image is rendered for this tier — it is an id-acceptance probe only.
  - **Render sample (paid):** min(N, all) where N=3, **stratified by category**, actually generate and assert a media URL returns. Pass/fail per sampled model recorded.
  - Together these catch both "the dropdown lists a dead/renamed id" (all-tier) and "the endpoint is wired wrong" (sample-tier).
- **AC-1.7 — No-models-API fallback.** If §0 finds a provider has **no** live catalog endpoint, that is recorded explicitly and its `offline_seeds/<svc>.json` becomes the sanctioned source (labelled in the UI as "static list — provider exposes no catalog API") — this is the *only* sanctioned hardcoded case.

## §2 — Real NSFW testing (fixes #2) — scope: **all viewable fal + every reachable model on the new providers**

- **AC-2.1 — Harness + evidence schema.** For each in-scope model, run PRIME's prompt with that provider's **most-permissive** safety config (from the §2 safety matrix), **N=3 renders** (fixed seeds where the provider supports seeds; else record `seed:null` + non-deterministic flag). Each render is classified (§2 classification) and one evidence row is written per model to `engine/nsfw_capability.json`:
  `{provider, model, model_version?, grade, nsfw_votes/3, mean, sd, classifier, classifier_scores[], request_params{size,steps,cfg,sampler}, seed, sent_prompt_sha256, clamped_len, truncated:bool, raw_safety_response?, refusal_class?, tested_at}`.
- **AC-2.2 — Most-permissive safety matrix.** A per-provider map (`engine/safety_matrix.json`) of the exact params/values that maximise permissiveness (together `disable_safety_checker:true`, runware `checkNSFW:false`, novita omit `enable_nsfw_detection`, fal per-model checker/tolerance…). "Most-permissive" = the documented maximum the API allows; providers that ignore a param are noted.
- **AC-2.3 — Robust classification (not brittle brightness), portable across providers.** Every render — **regardless of which provider generated it** — is graded by **two independent signals** on the downloaded image bytes:
  - **(a) NSFW score** via fal's standalone image classifier (`fal-ai/imageutils/nsfw`-class endpoint) invoked as its own scoring call on the bytes. It is provider-agnostic (it scores *any* image, not just fal-generated ones). The spec records its cost + rate limit in the §0 sheet. **If the classifier is unavailable/errors, the render is graded `unclear` — never silently downgraded to blank-detection-only** (blank-detection alone cannot prove *genuine NSFW generation*, only refusal).
  - **(b) refusal/blank detector** = {near-uniform frame via perceptual hash + variance, known watermark/placeholder template match, provider refusal text}. A near-uniform *dark* frame is "blocked" only if paired with a provider refusal/`has_nsfw` flag — guarding against dark-art false positives.
  - Signal disagreement → grade `unclear`, never a silent guess.
- **AC-2.4 — Grading rubric (bands).** `verified` = ≥2/3 renders classified NSFW by (a) AND not blocked; `refused/blocked` = ≥2/3 blank/refusal; `sfw` = renders viewable but classifier-negative; `unclear` = signals disagree or errors. Content-mode buckets (Safe/Editorial/Fashion/NSFW) map from these grades (rubric table in the spec).
- **AC-2.5 — Coverage + exclusions.** In-scope = the ~46 fal-viewable (from a **snapshot** `engine/fal_viewable_snapshot.json` with a delta report on drift) **re-tested on PRIME's prompt**, plus every **reachable** model on Novita/Together/Runware/AGNES. "Reachable" = present in the live catalog with the current key at test time; inaccessible models are logged with their error code, not silently dropped. Excluded-by-rule = an explicit `engine/nsfw_exclusions.json` where **each entry is `{id_pattern (regex), reason, policy_source_url}`** — a documented policy basis is mandatory (guards against over-exclusion / lazy "known-impossible" false-negatives). `verify_nsfw_v2` **asserts** (i) no excluded model enters the test queue AND (ii) every excluded id matches a listed `id_pattern` with a non-empty `policy_source_url` (no blanket/unjustified excludes). Seed patterns: BFL-proprietary Kontext ids, Google/OpenAI-backed family patterns.
- **AC-2.6 — Spend gate + resilience.** Prints `models × N × est-price` **before** firing (price from §0/ModelDescriptor; unknown price → require `--allow-unknown-price` or block). Re-runnable + cached: re-tests only models lacking evidence unless `--recheck`. Per-provider **rate-limit + max-concurrency + retry-with-backoff**; logs every skip/failure (no silent truncation).

## §3 — Per-model content grading for ALL providers (fixes #5)

- **AC-3.1 — Per-model, evidence-first.** `content_capability` is computed for **every** provider's models. A non-`safe` grade may be assigned **only** from empirical evidence (§2) OR the explicit exclusion rule (§2.5); **inference is capped** — a model with no evidence and no exclusion is graded `untested`, never assumed permissive.
- **AC-3.2 — Cross-provider filter.** Content Mode filters on the per-model grade for every service; the "Verified only" toggle narrows to `verified` across providers. UI states are defined: `verified` badge, `untested` badge (shown-with-caveat), `excluded` (hidden in NSFW mode); default hides `untested` under "Verified only".
- **AC-3.3 — Honest policy panel.** States, per provider, the **real basis** of each grade (tested N=3 / untested / excluded-by-rule), with counts — no overclaiming.
- **AC-3.4 — Discoverability console (surfacing, PRIME-requested).** The sweep's evidence must be *visible*, not buried in JSON:
  - **The sweep run itself refreshes `dashboards/nsfw-verified-gallery.html`** — the harness regenerates the gallery data (verified models + their sample renders + provider/model/grade/votes) as its final step, so the gallery is never stale relative to `engine/nsfw_capability.json`. Sample images are downloaded locally to `dashboards/assets/` (never hot-linked to expiring provider CDN URLs).
  - **The gallery is integrated into `dashboards/nsfw-providers-reference.html` as one "full discoverability console"** — the reference page (per-provider capability + policy basis from AC-3.3) and the verified-model gallery are unified so a viewer can go provider → model → verified sample render in one place, filterable by provider/grade. Both served over `dashboards_server` (`http://<host>:31960/...`), not `file://`.
  - Both pages carry the mandatory dashboard credit footer (skill/date/regen note) + a freshness badge reflecting `tested_at`.
  - Verify: a sweep run produces a gallery whose entries match `nsfw_capability.json` verified rows 1:1; the reference console links each provider row to its verified renders; a stale badge shows if `tested_at` is older than the JSON.

## §4 — In-app "which model?" suggestion box (PRIME-requested — the payoff of §1–§3)
An Ask-AI query box in the composer, **designed like the router pages' Ask-AI boxes** (`session-command-router.html` pattern: instant keyword routing as you type + a real model-answered reply). It turns the truthful catalog into an answer instead of a 1,322-row dropdown to scroll.
- **AC-4.1 — Box + instant local routing.** A single text input in the composer; as the user types, it **instantly filters the loaded catalog by keyword** (provider/model/category/capability) — no model call — exactly like the router pages' `classify()`/`picker-inline.js` pass. Enter / "Ask AI" fires the model-answered reply.
- **AC-4.2 — Grounded in ACCESS + capability truth (never hallucinated).** Suggestions are drawn **only from models the user can actually reach** (wired + keyed providers per key-status) and are filtered by the active **content mode** + per-model **content grade** (§3) — it must never suggest a model that isn't accessible or is wrong for the content mode. It cites `model id · provider · why · verified?`.
- **AC-4.3 — Answer source.** The Ask-AI reply is produced by the dashboards-server `/api/chat` (or an in-app equivalent) **primed with the app's live catalog + capability + key-status as context** — a registered `scope` so the answer is about *this user's* accessible image/video models, not generic advice. (Guards the known "unknown scope → generic code prompt" fallback.)
- **AC-4.4 — One-click apply.** A suggested model is selectable straight into the composer (sets provider + model), so "ask → generate" is two clicks.
- *Verify:* `.dd/verify_suggest.py` (+ JS test) — typing a keyword filters to the right catalog subset with no network call; an Ask-AI reply only names accessible models and respects the active content mode; selecting a suggestion sets provider+model.

## Non-goals
- New providers beyond those wired. Video-model NSFW testing (follow-up). A second ML classifier beyond fal's + the refusal detector (the two-signal design is the bar here). The **LLM/model fleet-access advisor dashboard is Spec E** (separate surface).

## Verification (stronger invariants)
- `.dd/verify_catalogs.py` — every provider returns a non-empty live catalog (or a labelled no-API fallback); the no-hardcoded-lists lint passes; completeness (paged count) checked; the generatable sample passes per provider.
- `.dd/verify_nsfw_v2.py` — every in-scope model has an evidence row whose `sent_prompt_sha256` matches PRIME's prompt; grades are **recomputed from the stored classifier_scores + rubric bands and must match the stored grade** (no hand-set grades); every row carries the required evidence fields + the most-permissive params from the safety matrix; no excluded model appears.
- content-mode JS test extended: per-model grading across providers; `untested`/`verified`/`excluded` UI states; verified-only narrows correctly.
