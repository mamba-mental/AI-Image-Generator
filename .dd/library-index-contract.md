# dd-contract — SQLite Library Index (Spec A)

**Spec:** `docs/specs/A-library-performance.md` (judge-verified 93/100) · **ADR:** `docs/adr/0001-sqlite-fts5-library-index.md`
**Route:** `/debug-router` → `/dd-router` — RED harness before the fix.

## Failing example (the regression, PRIME's real condition)
Opening the Library tab, and toggling one folder, both trigger a full ~5k-file NAS re-crawl with a per-image sidecar read → slow + workstation-wide stall. Root cause proven in `AC-0` (sidecar_open_count ≈ file count; folder toggle → full re-crawl).

## Acceptance (binary — from Spec A, executed by `.dd/verify_library_index.py`)
- **AC-1** Per-folder cache: toggling a folder off/on performs **zero** new filesystem reads for already-indexed folders (instrumented stat/open count unchanged across a toggle cycle).
- **AC-2** Warm reload < **250 ms** for a 5,000-row index with **zero** NAS-prefix filesystem access.
- **AC-3** Incremental refresh: after add/rename/delete of one file in folder B, only B is re-read; A untouched; new state reflected. Signature check never runs on plain `list` (only on explicit refresh).
- **AC-4** Sidecar bounded: warm `list` performs **zero** `<media>.json` opens (metadata persisted as columns at index time).
- **AC-5** FTS5 present → fast prompt/tag search; absent → LIKE fallback, no crash.
- **AC-6** Migration: a legacy `library_index.json` imports once; a corrupt DB rebuilds from scan (no data loss — NAS is source of truth).

## Build increments (each safe on its own)
1. `engine/library_index.py` — the module + `.dd/verify_library_index.py` harness → prove green in isolation (this increment; does NOT touch the live app path).
2. Rewire `bridge.py` `list_library`/`refresh_library`/`_scan_library`/`set_library_dir_enabled` to the module; keep the JS contract identical (`list_library` still returns the same record shape).
3. `web/app.js` — non-blocking paint (AC-5 responsiveness) + explicit Rescan button (AC-3 timing rule).

## Verify
`python .dd/verify_library_index.py` → exit 0 all-green / 1 any-fail, per-AC PASS/FAIL, on a synthetic tree + seeded DB (no NAS needed). Real-NAS timed benchmark `.dd/perf/bench_nas.py` after rewire.
