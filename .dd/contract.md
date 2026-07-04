# Contract — AI Studio Void rebuild (pywebview + fal.ai + PyInstaller)

**Build:** Rebuild the CustomTkinter app as a web-view desktop app: HTML/CSS/JS UI (from STITCH-UI-REFERENCE.html + DESIGN.md Void-Black tokens) in pywebview, Python engine behind js_api bridge, fal.ai as 4th backend (curated flagships), PyInstaller onedir exe + desktop shortcut. Plan: `C:\Users\tiran\.claude\plans\jiggly-enchanting-reef.md` (PRIME-approved 2026-07-03).

**Driven-dev methods:** spec-first (approved plan = spec) · phase-gated checklist (binary gates below) · TDD where portable (migrated test_hf_params + new test_bridge run at every gate) · producer≠verifier (each gate is a runnable check, not a claim).

## Acceptance criteria (binary)

1. All 4 services (replicate, hf, gemini, fal) generate successfully from the new UI.
2. fal backend covers 6 categories from `engine/fal_models.json` (t2i, i2i, t2v/i2v, upscale, bg-removal, music).
3. Mid-generation cancel works (job stops, UI re-enables, fal queue request cancelled).
4. UI renders fully offline — zero CDN/network requests to paint the window.
5. Frozen exe launches and generates from a non-repo cwd; config materializes in %APPDATA%\AI Studio Void\.
6. No secrets in tracked files (pattern-grep r8_/AIza/hf_/FAL across tracked = 0) and none in the PyInstaller bundle.
7. Old app.py archived to _archive/ (not deleted) only after the exe gate passes; runnable fallback until then.
8. `pytest tests/` green at every phase gate.

## Phase gates (each ends with a runnable binary check)

- P0 hygiene: tracked-file secret grep = 0; app.py still launches.
- P1 engine: `python -c "from engine.backends import replicate_api, hf_api, gemini_api"` + pytest green + CLI --help.
- P2 bridge: `python main.py --smoke` prints get_state() JSON, exit 0.
- P3 fal: one flux/schnell gen lands in generated_images with progress events; fal skill gap-filled, help block intact.
- P4 comps: 3 rendered comps presented; PRIME's pick recorded.
- P5 UI: screenshot + in-app fal AND gemini gen + cancel proof.
- P6 exe: non-repo-cwd launch + schnell gen + %APPDATA% config.
- P7 shortcut: .lnk double-click launches; tests green.
