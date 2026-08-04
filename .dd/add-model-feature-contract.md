# *DD Contract: "Add a model by id/URL" affordance

Build type: Web-frontend feature + small backend method
Methods (>=3): ATDD (done-gate: user can add + run a new Replicate model) · SBE (worked examples: id/URL parse cases) · TDD (inner: parseModelRef pure fn + add_recent_model)
Stack + tools: Python (bridge.add_recent_model) -> pytest-style .dd harness; JS (parseModelRef + UI) -> node-eval + static harness (repo has no JS runtime, same as verify_naming/verify_libperf).

## Why
The Replicate backend runs ANY `owner/model` id, but the UI only offers models already in
`recent_models_<service>` — so a brand-new model has no entry point (PRIME testing NSFW models hit
this). Add a way to paste a model id OR a replicate.com URL, in TWO places (PRIME chose "Both"):
a dedicated "+ add model" input under the model dropdown, AND the "Which model?" search box.

## Acceptance (ATDD / SBE)
- AC-1: `parseModelRef` normalizes each case -> canonical id. -> `.dd/verify_add_model.py` (node-eval) [RED]
  - `https://replicate.com/aisha-ai-official/flux.1dev-uncensored-jibmix` -> `aisha-ai-official/flux.1dev-uncensored-jibmix`
  - `https://replicate.com/owner/model/versions/47f609a6...` -> `owner/model:47f609a6...`
  - `owner/model` -> `owner/model` ; `owner/model:abc123` -> `owner/model:abc123`
  - `  ` (blank) -> "" (no-op)
- AC-2: `bridge.add_recent_model(service, id)` prepends id to `recent_models_<service>`, de-dupes,
  persists via config.save, returns {ok, model_id, models}. -> `.dd/verify_add_model.py` [RED]
- AC-3: the "Which model?" box shows a "Use this model" action when the query parses as a model ref
  (looksLikeModelRef) even with zero catalog matches. -> static harness on renderModelSuggest [RED]
- AC-4: a dedicated "+ add model" input+button exists in index.html under the model select, wired to
  addUserModel. -> static harness [RED]
- AC-5 (no regression): existing model suggest/select still work; bridge imports clean; verify_library green.

## Examples (SBE)
- Paste `https://replicate.com/aisha-ai-official/nsfw-flux` -> added to recents, selected, schema fetched.
- Type `black-forest-labs/flux-dev` in the search box -> "Use this model" chip -> same.

## Non-goals
- Per-provider id VALIDATION (a bad id fails at generate with the backend's own error — not this feature's job).
- Auto-discovering a provider's full model catalog (that's the existing one-shot catalog fetch).

Status: CONTRACT MET (9/9 GREEN; live add+run of a new model gated on app restart + PRIME eyeball)
