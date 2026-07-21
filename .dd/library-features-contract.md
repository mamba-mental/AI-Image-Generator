# dd-router contract — Library filters, folder toggles, add-folder, prompts (Phase 2)

**Slug:** library-features
**Repo:** mamba-mental/AI-Image-Generator
**Verify harness:** `.dd/verify_library.py` (python, self-contained, re-runnable, exit 0 = all green)

## Problem
The Library view is a flat masonry of basenames with no filter, no folder control, and prompts only in the lightbox. Root cause: `.cache/library_index.json` stores only basenames (`{dirs, files:[str], count}`) — no per-image `dir`/`type`/`service`/`prompt`, so nothing can be filtered. `_library_dirs()` is all-or-nothing; there is no folder on/off, no add-folder, and `jobs.py` throws away `category` before it's persisted.

## Acceptance criteria (RED → GREEN)

- **AC-1 — Index carries per-image records.** `Api._scan_library(bases)` returns a list of dict records `{file, dir, type, ...}` (not bare strings). `type` ∈ {image, video} from extension. When a `<media>.<ext>.json` sidecar exists, the record also carries any of `service`, `model`, `prompt`, `category` present in it.
- **AC-2 — Index is versioned + backward-compatible.** `list_library()` writes `{version: 2, dirs, files:[record], count}`; a v1 (string-list) or mismatched-`dirs` cache triggers a rescan, never a crash. `list_library()` returns the record list.
- **AC-3 — Category is persisted going forward.** `jobs.py` no longer strips `category` from the saved `meta`; a generated image's sidecar/history record carries `category` when the request had one. `clean_params` still excludes `category` (no dup).
- **AC-4 — Folder enable/disable.** `Api._library_dirs()` excludes any path in `config["library_directories_disabled"]`. `Api.set_library_dir_enabled(path, False)` adds it to that list (and removes the media-server root); `True` removes it (and re-adds the root). `Api.list_library_dirs()` returns `[{path, name, enabled, exists}]` for every configured dir.
- **AC-5 — Add folder.** `Api.add_library_dir(path)` with a valid dir appends it to `config["library_directories"]`, registers it as a media root, persists, and returns the updated `list_library_dirs()`. An invalid/again-existing path is a no-op (no crash, no dup).
- **AC-6 — Media-server root removal exists.** `engine.mediaserver.remove_root(path)` removes a previously-added extra root so a disabled folder stops serving without an app restart.
- **AC-7 — Cross-folder record integrity.** Every record's `dir` is one of the scanned `bases`; de-dup by basename is preserved (first dir wins) so the index has no duplicate `file`.
- **AC-8 — Frontend filter (smoke).** The Library view exposes a filter bar (source folder, service, type, prompt text search) and folder toggles + an add-folder control; `python main.py --smoke` starts clean and a DOM check finds the filter bar + `#library` populated. (Verified via `--smoke` + diag, not the python harness.)

## Verify harness plan (`.dd/verify_library.py`)
Pure-python, no app run: constructs a temp tree with two "library" dirs, media files + sidecars (one with `service/prompt/category`, one video, one basename-collision), monkeypatches `Api` config, then asserts AC-1,2,4,5,7 on `_scan_library`/`list_library`/`_library_dirs`/`set_library_dir_enabled`/`add_library_dir`, AC-3 by inspecting the `jobs.py` meta-build (import + reflect the code path), AC-6 by `mediaserver.add_root`+`remove_root` round-trip. Prints `[PASS]/[FAIL]` per AC; exit non-zero on any fail.
