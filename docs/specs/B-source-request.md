# Spec B — source request (what "good" is measured against)

This is the deliverables definition the Spec B artifact (`B-truth-about-models.md`) must satisfy. It captures PRIME's raw asks (#1, #2, #5) plus the decisions he confirmed.

## PRIME's words
- **#1:** "Are the models that you are putting in the dropdowns for the provider pulled dynamically or are you guessing? For instance, I only see 21 image LLMs in on the model search for novita and you have many that are not on the page… This will need to be checked for all of the models and all of the providers."
- **#2:** "have all of the models either been researched or tested for a genuine NSFW generation? Except for the ones that we know for sure won't allow NSFW / Art Nude generation, we need to test all of these. We should do another test using a prompt that I would actually use." (He supplied a long, explicit fine-art-nude prompt as the example.)
- **#5:** "for all of the providers in the image… have all of the LLMs listed on the api been checked that they align with the filters settings for the content mode? if not, its important that this is updated as well."

## Confirmed decisions (do not re-litigate)
- **Scope of the NSFW re-test = WIDEST:** all ~46 viewable fal models **re-tested on PRIME's real prompt**, PLUS every reachable model on the newly-wired providers (Novita, Together, Runware, AGNES). Models known-impossible (BFL-proprietary Kontext; Google/OpenAI-backed) excluded by rule, not by spend.
- **Benchmark prompt = PRIME's actual prompt** (the explicit fine-art-nude prompt), not the mild one used before. It exceeds 1024 runes on some providers → the harness must record the clamped length so a truncated prompt is never mistaken for a capability signal.
- Every provider's model dropdown must be **pulled live from that provider's API**, never a hardcoded list (seeds allowed only as a labelled offline fallback).
- Novita specifically must expose **both** its catalogs — legacy checkpoints AND the modern Model-APIs (Seedream/Qwen-Image/Flux-Kontext/ZZ-Turbo) — because today only the legacy checkpoint catalog is surfaced.
- Content-mode grading (`content_capability`) must be **per-model and evidence-backed for every provider**, not a per-service assumption.

## What a passing spec must do
- Turn each of #1/#2/#5 into concrete, testable RED→GREEN acceptance criteria.
- Name the exact provider endpoints / mechanisms to fetch each catalog live.
- Define the empirical NSFW harness: inputs (PRIME's prompt), classification method, per-model evidence fields, coverage list, spend-gate, and skip-logging.
- Define how per-model content grades flow into the Content Mode filter for all providers.
- Be executable-verifiable (named verify harnesses) and honest about what is tested vs inferred vs excluded.

## Verified facts (from this session — the spec must stay consistent with these)
- Only **fal** is genuinely dynamic today (1,322 models). Novita = legacy-checkpoint catalog only. Together/Runware/cliproxy/AGNES/Ideogram/OpenAI/NVIDIA/Gemini = hardcoded seed lists.
- NSFW testing to date = fal only (95 t2i), mild prompt. Zero testing on the new providers.
- `content_capability` exists only for fal.
