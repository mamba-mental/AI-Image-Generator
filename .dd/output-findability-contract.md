# dd-contract — Output dir & findability (Spec C #6)

**Spec:** `docs/specs/C-find-and-manage.md` (93/100), C6 section.
**Live bug (smoke-confirmed):** `config.output_directory = "I:\\"` — the NAS ROOT. Generations save into the root of a 5k+ share and are **not** inside any `library_directories` scan path → unfindable (PRIME's #6).

## Acceptance (binary — `.dd/verify_output.py`)
- **AC-6.1** New generations save to `<output_root>/generated/YYYY-MM/` with a sortable, collision-proof filename (`YYYYMMDD-HHMMSS-<ms>-<seq>-<seedslug>.<ext>`). Provider/model stay metadata, not folder levels.
- **AC-6.2** The active `generated/` root is guaranteed a member of the Library scan set (auto-registered if missing) — a fresh generation is findable in the Library immediately, no manual folder-add.
- **AC-6.3** Setting `output_directory` REJECTS a drive root (`X:\`), a filesystem root (`/`), a UNC share root (`\\host\share`), and a non-writable dir, with a clear error (guards the `I:\`-root misconfig). Valid dirs accepted.

## Build
1. `engine/save.py` — `make_output_paths` writes into `<base>/generated/YYYY-MM/`; add `validate_output_root(path) -> (ok, msg)` + `generated_root(base)`.
2. `bridge.py` — `_ensure_output_registered()` adds the generated root to `library_directories` (called on init + after a save); `set_config`/a `set_output_dir` validates via `validate_output_root`.
3. `web/app.js` (Settings) — output/library path pickers surface the validation error. (UI wire = C4 phase; the guard + API land here.)

## Verify
`python .dd/verify_output.py` → exit 0/1, per-AC PASS/FAIL, on temp dirs (no NAS). + `main.py --smoke`.
