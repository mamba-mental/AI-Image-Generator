# DD Contract — NSFW capability: graded classification + empirical verification

Make the content filter mean "actually allows NSFW", not "has a disable-able safety param".
Replaces the `supports_relaxed_safety` proxy with a graded `content_capability` + an empirical oracle.

## Acceptance criteria (RED until proven)

- [ ] **AC-1** Every model in `fal_models.json` carries `content_capability` ∈ {`upstream_moderated`, `permissive`, `verified`, `filtered`}.
- [ ] **AC-2** **Zero** Google/OpenAI-backed models (`nano-banana`, `gemini`, `imagen`, `gpt-image`, `dall-e`, `nucleus`) are graded `permissive`/`verified` — they're all `upstream_moderated` (the ≥9 false positives are gone from the shown list).
- [ ] **AC-3** `content_mode.js` `isRelaxable()` keys off `content_capability` (shows `permissive`+`verified`, hides `upstream_moderated`+`filtered`); a "verified only" refinement exists.
- [ ] **AC-4** The mode note + `NSFW_POLICY` panel copy no longer claim a confirmed NSFW list — they say "adjustable filter, permissive not guaranteed; some providers moderate upstream".
- [ ] **AC-5** A curated known-uncensored seed list grades those ids `verified` before any empirical run.
- [ ] **AC-6** `scripts/verify_nsfw_capability.py` exists: gens a benchmark NSFW prompt per candidate → `fal-ai/x-ailab/nsfw` classifier → writes `engine/nsfw_capability.json` (id → {grade, score, evidence}); re-runnable + cached; `--sample N` + `--categories` flags; the build merges it back so grades become **empirically-backed, not heuristic**.
- [ ] **AC-7** After an empirical run, every model shown in NSFW mode is `verified` (produced NSFW, with a score) or explicitly `permissive` (untested) — never a bare boolean.
- [ ] **AC-8** `main.py --smoke` still passes; the NSFW-mode t2i count drops below 155 and excludes nano-banana/gemini.

## Verify
`python scripts/verify_content_capability.py` (free: grading + exclusions + label copy) + `main.py --smoke`; and (paid, gated) `scripts/verify_nsfw_capability.py --sample 15` → flux/sdxl come back verified, nano-banana/recraft-vector refused, evidence written.
