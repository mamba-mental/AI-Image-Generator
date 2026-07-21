# Baseline critique (judge: zen-pal gpt-5.2) — Spec B
Score: 73/100  (#1 catalogs 78 · #2 NSFW 70 · #5 grading 68)

Top gaps to fix:
1 Per-provider integration sheet (endpoints/auth/pagination/schema/quotas/errors) — biggest #1 gap.
2 "No hardcoded lists" not enforceable — add CI/lint rule (forbid static model arrays except labelled offline_seeds.*) + review checklist.
3 Novita dual-catalog UX (sections/tabs, merge rules, partial-failure behavior).
4 "Generatable" too weak (spot-check 1) — per-provider sampling min-N + category stratification, explicit pass/fail.
5 Common ModelDescriptor schema (id/label/category/price + ctx/max-prompt/sizes/aspect/safety-modes/image-limits).
6 Caching semantics (TTL, invalidation, background refresh, persistence, last-known versioning).
7 Completeness check (page all results, compare counts, detect truncation).
8 "Most-permissive safety params" undefined — per-provider safety matrix.
9 Sample count/determinism (mean,sd implies multiple runs) — N renders/model, seed strategy, non-determinism policy.
10 Classifier generalization — 2nd independent NSFW signal + calibration + disagreement resolution.
11 black-frame/brightness brittle (dark art false-positive) — add blank/watermark/refusal-template detection + perceptual hash.
12 Grading rubric — define Safe/Editorial/Fashion/NSFW thresholds (classifier bands).
13 Evidence model complete — provider, model version, request params (size/steps/CFG/sampler), seed, raw safety response.
14 Store sent_prompt (post-truncation) + truncation flag.
15 Price sourcing reconcile (AC-1.4 price optional vs AC-2.4 needs it for spend).
16 Exclusion detection explicit mapping + verify excluded never enter queue.
17 "Reachable" defined (in catalog w/ current key at test time) + log inaccessible w/ error codes.
18 Provider-without-models-API fallback discovery strategy.
19 Content-mode UI states for inferred/excluded (badges, defaults).
20 Cap inference (only known-impossible/explicit-policy; else must test).
21 Verification invariants stronger (grades match classifier+thresholds; params most-permissive; required fields).
22 "viewable fal" operationalized (snapshot + delta).
23 Refusal/error taxonomy (capture refusals/safety-blocks/HTTP/moderation codes).
24 Concurrency/rate-limit/retries per provider.
