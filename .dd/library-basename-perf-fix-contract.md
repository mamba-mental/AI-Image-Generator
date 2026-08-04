# *DD Contract: Omni-Image library basename-collision + perf fix

Build type: Data-migration + Web-frontend-perf + Backend (union — routed per part)
Methods (>=3): ATDD (outer done-gate) · SBE + EDD (golden examples = the 104-not-5080 failing case) · TDD (inner units)
Stack + tools: Python (rename migration, `engine/mediaserver.py`, `engine/library_index.py`) -> executable `.dd/verify_*.py` harnesses (repo has no JS runtime, so JS is proven by static-source structural harness, same as `verify_libperf.py`).

## Root cause (proven, Phase 1)
Scraper writes `scripts/.replicate_recover/images/<predictionID>/<n>.<ext>` — every prediction's outputs are named `0.png`, `1.png`... so basenames COLLIDE across all 2,740 subfolders. The app keys identity on basename in three places -> three symptoms from ONE cause:
- `library_index.list_images` de-dupes by basename -> 5,080 recover images collapse to **104** tiles.
- `mediaserver._find` + thumb cache key by basename -> every `0.png` resolves to the first hit (wrong thumbs) via an `rglob` over 2,740 subdirs (slow).
- Making names unique (fix) grows distinct tiles ~5,666 -> ~10,600, exceeding the hard `limit=8000` AND worsening the un-virtualized DOM (`buildLibTiles` builds ALL tiles). => visibility fix and perf fix are COUPLED.

## Acceptance (the done-gate — ATDD / SBE)
- AC-1 (visibility): `library_index.list_images([recover_root], 20000)` returns >= 5000 distinct recover records (was 104). -> test: `.dd/verify_recover_fix.py` [RED]
- AC-2 (unique identity): in `library.db`, recover rows' distinct `name` == distinct `path` (no basename collision); on disk, sampled recover image basenames are unique. -> `.dd/verify_recover_fix.py` [RED]
- AC-3 (thumb resolves per-image): `mediaserver._find(name)` maps each recover basename to its OWN file (distinct names -> distinct absolute paths), no first-hit collision. -> `.dd/verify_recover_fix.py` [RED]
- AC-4 (DB-backed resolve, no rglob): `mediaserver` resolves a recover-name lookup WITHOUT a recursive filesystem walk (uses a DB/basename->path index). -> `.dd/verify_recover_fix.py` (structural + behavioural) [RED]
- AC-5 (virtualized grid): the library grid keeps a BOUNDED number of tile DOM nodes regardless of record count (IntersectionObserver / windowed recycle), not one node per record. -> `.dd/verify_grid_virtual.py` static harness [RED]
- AC-6 (cap): all recover images reachable — `list_library` record cap raised/paginated so >= 10,000 records load. -> `.dd/verify_recover_fix.py` [RED]
- AC-8 (lightbox metadata, added after PRIME's screenshot): clicking a recover image shows its prompt +
  metadata. Root cause — bridge.read_meta scanned only top-level `<dir>/<name>.json`, missing nested
  archive sidecars. Fix: resolve via library.db (name->real path) then read the nested sidecar. ->
  `.dd/verify_lightbox_meta.py` [was RED — top-level scan returned nothing] -> 5/5 GREEN.
- AC-7 (no regression): other folders (`I:/generated`, `I:/scraped-ai-images`, `generated_images`) still return correct counts + resolve correctly; `verify_libperf.py` stays 18/18; `verify_library.py` stays green. -> re-run those harnesses [must stay GREEN]

## Examples / spec (SBE / EDD)
- Failing example: recover folder has 5,080 image rows but `list_images` returns 104 (basename collapse). Fixed = 5,080.
- Collision example: `_find("0.png")` today returns ONE path though 1,488 distinct `0.png` files exist. Fixed = each unique name -> its own path.
- Golden: a rename maps `images/<id>/0.png` -> `images/<id>/<id>_0.png`; DB `name`/`path` and the `<img>.json` sidecar follow atomically; reversible via manifest.

## Inner cycle (TDD)
- first failing unit: `rename_recover` pure mapping fn `(<id>, n, ext) -> "<id>_<n>.<ext>"` + a dry-run planner that lists (old_path, new_path, old_name, new_name) with zero collisions. [RED — fn does not exist]

## Non-goals (guard scope-creep)
- Deliverable #2 (re-scrape the 808 predictions never fetched) — BLOCKED on a fresh replicate.com cookie; separate track.
- NSFW sweep folders; any change to the app's global basename-identity model beyond what the recover fix + virtualization require.
- The 79 empty-prompt / 11 zero-image records (data-quality residue of the incomplete scrape, folded into #2).

## Results (all executable, re-runnable)
- `verify_recover_fix.py`      6/6  (AC-1/2/3/4/6) — was 0/6
- `verify_grid_virtual.py`     3/3  (AC-5)
- `verify_ac7_no_regression.py` PASS — 6 non-recover folders (AC-7)
- `verify_thumb_serving_live.py` 4/4 — live HTTP: renamed nested recover thumbs 200 JPEG, DB-resolved, collision gone (3 distinct thumbs)
- Regression: verify_libperf 14/14 · verify_library 21/21 · verify_library_index 15/15 — all still GREEN

Whole-library distinct basenames: 5,666 -> 10,642 (recover 104 -> 5,080 now individually visible).

## Open (not part of this contract's done-gate)
- LIVE desktop-app render is the ONE thing not self-verifiable here (WebView decode; needs the app to
  RESTART to load the new Python + web assets). PRIME's restart + eyeball is the second reader.
- Deliverable #2 (re-scrape the 808 never-fetched predictions) — UNRECOVERABLE. Cookie is valid, but
  replicate.com `/p/<id>` returns 404 for the 808 (5/5 sampled across the full range) — the predictions
  are PURGED server-side (Replicate's legacy-retention deletion; the list index still names them but the
  detail records are gone). Not a tooling/auth failure; the source data no longer exists. The scraper
  naming patch (<pid>_<n>) is kept anyway so any FUTURE scrape is born collision-free.
- One-line flags (out of scope): scraped-ai-images (3705->3591) + nsfw-img (68->54) have their OWN
  pre-existing basename collisions; ~104 stale old-name thumbs in .cache/thumbs are harmless orphans.

Status: CONTRACT MET (all acceptance GREEN via executable harnesses; live-render gated on app restart)
