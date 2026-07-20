# DD Contract — Job 1: Full FAL catalog puller

**Feature:** Regenerate `engine/fal_models.json` from the LIVE fal explore catalog (full per-category
pull, not the top-13 subset), each model carrying rich params + price + safety flag.

**Build target:** `scripts/build_fal_catalog.py` (extend) → `engine/fal_models.json` (regenerate).

## Acceptance criteria (RED until proven)

- [ ] **AC-1** `engine/fal_models.json` contains **≥194** `text-to-image` models.
- [ ] **AC-2** contains **≥125** `text-to-video` models.
- [ ] **AC-3** contains `image-to-image` and `image-to-video` (≥187) categories populated.
- [ ] **AC-4** ≥95% of models have a non-empty `params[]` (some endpoints legitimately expose no schema — logged, not failed).
- [ ] **AC-5** params carry a `description` string where the OpenAPI schema provides one.
- [ ] **AC-6** every model has a boolean `supports_relaxed_safety` field, computed from whether its schema exposes `enable_safety_checker`/`safety_tolerance`/`enable_output_safety_checker`.
- [ ] **AC-7** every model has `price` (from `pricingInfoOverride`||`billingMessage`) and `thumb` fields present.
- [ ] **AC-8** the previous `fal_models.json` was backed up (a `fal_models.json.bak-*` exists) before overwrite.
- [ ] **AC-9** the puller is re-runnable and schema-cached: a second run reuses `scripts/.fal_schema_cache/` (much faster) and honors `--categories` + `--max-per-category` flags.
- [ ] **AC-10** app `python main.py --smoke` still loads the catalog and returns `get_state()` (JSON parses, no crash).

## Verify
`python scripts/verify_fal_catalog.py` (to author) — counts per category, params/description/safety-field coverage, backup presence; PASS/FAIL per AC. Plus `python main.py --smoke`.
