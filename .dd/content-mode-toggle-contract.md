# DD Contract — Job 2: Content-mode toggle (Safe / Editorial / Fashion / NSFW)

Extend the binary `state.nsfw` scaffold into a 4-mode selector that filters the model list and
drives per-model safety params per request. Plan doc §3.

## Acceptance criteria (RED until proven)

- [ ] **AC-1** A 4-mode selector (Safe/Editorial/Fashion/NSFW) replaces the binary checkbox, visible for ALL services (no `state.service==="fal"` gate).
- [ ] **AC-2** `applyContentMode(params, model, mode)` returns params with the mode's safety profile applied — `enable_safety_checker`, `enable_output_safety_checker`, `raw`, and `safety_tolerance` **clamped to the model's own enum max** (6 for most, 5 on flux-2-pro) — only for params the model actually declares.
- [ ] **AC-3** Editorial/Fashion/NSFW **filter the fal model list** to `supports_relaxed_safety` models; Safe shows all. Fashion sorts fashion/try-on models first.
- [ ] **AC-4** The override is applied to the **per-request params dict** (gen handler), not a static env var. The static `FLUX_DISABLE_SAFETY` + dead `FLUX_GO_FAST` env sets are removed from `config.py`; the inert `fal_api.py` env hook is removed.
- [ ] **AC-5** Per-mode help text (incl. the upstream-moderation caveat that Google/OpenAI-backed models still moderate) shows in the note + policy panel.
- [ ] **AC-6** A non-fal service honors the mode: `replicate`/`together` get `disable_safety_checker=true` in permissive modes, `false` in Safe.
- [ ] **AC-7** Proven: NSFW on a fal model (e.g. flux-pro/v1.1) sets `safety_tolerance` to its max + `enable_safety_checker=false`; Safe restores `true`/"2". Proven on 1 fal + 1 non-fal.
- [ ] **AC-8** `main.py --smoke` still passes.

## Verify
A node/JS assertion of `applyContentMode` across a fal safety model + a replicate model + a hard-filter model (openai) for all 4 modes; plus `main.py --smoke`.
