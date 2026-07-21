# Spec A — Library performance (regression fix)

**Cluster:** #3 · **Type:** bug/perf regression · **Introduced:** 2026-07-20 (Phase 2 library index change — mine)
**Route:** `/debug-router` → `/dd-router` (binary repro before fix)
**Refined:** 2026-07-21 via refine-to-spec (judge gpt-5.2, pinned) — baseline 86, this version closes the flagged gaps.

## Problem (PRIME's words)
> "when I click on the library tab, it not only takes forever to load, but it slows down the entire workstation. it also is even slower when I check 1 folder at a time. I thought that the quick load for these library images and prompts was optimized for a quick re-load after the initial load was done. This is not the case and its a terrible UX"

## Root cause (identified, not guessed — and its evidence is a required artifact)
1. **Per-image sidecar reads added to the crawl.** `Api._scan_library()` opens a `<media>.<ext>.json` sidecar for *every* media file (~5,000+ on the NAS) via a 16-thread pool. A name-only `rglob` (~7s) became thousands of extra SMB round-trips.
2. **Every folder toggle invalidates the whole cache.** `list_library()` caches under a key of the *enabled* `bases` set. Toggling one folder changes `bases` → cached index discarded → **full multi-thousand-file NAS re-crawl**. That is exactly why one-folder-at-a-time is *slower*.
3. **No incremental/partial state.** All-or-nothing index: no per-folder cache, no mtime delta, no early paint — the UI blocks until the whole crawl finishes.

- **AC-0 — Root-cause evidence artifact.** The repro records, on the real NAS, a `before` measurement to `.dd/perf/lib-before.json`: `{sidecar_open_count, smb_stat_count, wall_ms, folder_toggle_recrawl:true}`. This proves (1)+(2) empirically (sidecar opens ≈ file count; a toggle triggers a full re-crawl) rather than asserting them. The `after` run must show `sidecar_open_count == 0` on warm open and `folder_toggle_recrawl == false`.

## Goals
- Restore the original promise: **first load may be slow; every subsequent open is instant**, including after folder toggles.
- The Library tab must **never** make the workstation unresponsive (operationalized in AC-5).

## Mechanism (decided — ADR 0001): SQLite + FTS5 Library Index
Replace the JSON `.cache/library_index.json` with a **local SQLite database + FTS5** as the Library Index — indexed once, updated incrementally, never a full NAS re-crawl on open. Shared foundation for Spec C tags(#8)+output(#6). `sqlite3`/FTS5 ship with Python — no new dependency.

### Minimal schema (`.cache/library.db`, `schema_version` pragma-tracked)
```sql
CREATE TABLE folders(          -- one row per configured library dir
  path TEXT PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 1,
  sig TEXT,                    -- change-detection signature (see AC-3)
  indexed_at REAL);
CREATE TABLE images(
  path TEXT PRIMARY KEY,       -- absolute path (unique); basename derived
  folder TEXT NOT NULL REFERENCES folders(path),
  name TEXT NOT NULL, type TEXT NOT NULL,       -- image|video
  provider TEXT, model TEXT, seed TEXT, prompt TEXT,
  width INTEGER, height INTEGER, created REAL,
  tags TEXT DEFAULT '');       -- Spec C manual tags (CSV); auto-tags derived
CREATE INDEX idx_images_folder ON images(folder);
CREATE VIRTUAL TABLE images_fts USING fts5(   -- Spec C fast prompt/tag search
  name, prompt, provider, model, tags, content='images', content_rowid='rowid');
-- triggers keep images_fts in sync with images (insert/update/delete)
```
- **FTS5 availability check at startup** (`sqlite_compileoption_used('ENABLE_FTS5')` or a probe `CREATE VIRTUAL TABLE`); if absent, fall back to a plain index table with `LIKE` search + log a warning (never crash).
- **Migration:** on first run, if `.cache/library_index.json` exists, import its records into `images` (one-time), then ignore the JSON. If the DB is missing/corrupt (integrity_check fails), delete + rebuild from a scan (rollback story = "rebuild from filesystem," never data loss since the NAS is source of truth).

## Acceptance criteria (RED → GREEN — every one has a measurable check)
- **AC-1 — Per-folder cache.** Index keyed **per folder** (`folders`/`images.folder`), not per enabled-set. Toggling a folder off/on performs **zero** new filesystem reads for already-indexed folders. *Check:* instrument `os.stat`/`open`/`Path.rglob`; assert the count is **unchanged** across an off→on toggle cycle on a synthetic tree.
- **AC-2 — Warm reload is instant + provably no NAS access.** With a warm DB, `list_library()` returns in **< 250 ms** for a 5,000-row index. *Measured*, and enforced: instrument filesystem access and **assert zero path accesses under any NAS-prefix** (the configured library dirs) during the warm call — a warm open is a pure local-DB query. Baseline recorded: DP1 (Windows) + the real NAS share; the timing includes query + row hydration but **not** thumbnail generation (that's lazy per tile).
- **AC-3 — Incremental refresh with a defined signature — and it NEVER runs on open.** A rescan re-reads only folders whose **signature changed**. Signature = `sha1(sorted(child_name + '|' + str(child_mtime_ns) for each direct+recursive entry))` (chosen over bare `dir_mtime` because it also catches **renames and deletes**). **Critical timing rule (guards against re-introducing the #3 regression):** signature computation / rescan runs **only on an explicit user "Rescan" action or a scheduled idle refresh — NEVER automatically on Library tab-open** (tab-open is a pure warm DB read, AC-2). To keep even an explicit rescan from hammering the NAS, per-folder scanning is capped at **≤ 4 concurrent SMB operations** (not the old 16-thread pool) and yields between folders. *Check:* on a synthetic tree, add/rename/delete one file in folder B → assert only B is re-read, A untouched, new state reflected; assert tab-open triggers **zero** signature reads.
- **AC-4 — Sidecar reads bounded — strategy LOCKED to (a).** Metadata is read **once at index time and persisted as `images` columns** (`provider/model/seed/prompt/width/height`), and **never re-read on open**. (Lazy per-tile is *not* used for indexed images; it remains only a fallback for an image encountered before its folder is indexed.) *Check:* warm open performs zero `<media>.json` sidecar opens (AC-0 `after` artifact).
- **AC-5 — Non-blocking UI, with a responsiveness budget.** The crawl runs on a **background thread** (never the webview UI thread). The Library view paints its shell + first tiles **before** any crawl completes; progress is shown. *Measurable budget:* during an active full crawl the UI thread is never blocked **> 50 ms** in a single tick, the window stays responsive to move/close within **200 ms**, and the indexing thread stays **I/O-bound — CPU < 70 % of one core averaged over 5 s** (psutil sample on the baseline box). *Check:* a smoke run starts a crawl and asserts the JS event loop keeps ticking (a heartbeat timer fires within budget) while indexing, and samples crawl-thread CPU against the 70 % ceiling.
- **AC-6 — No feature regression.** Phase-2 filters (folder/source/type/prompt-search), folder toggles, add-folder, prompt-on-tile all still pass `.dd/verify_library.py`.

## Non-goals
- Library visual redesign (Spec C). Tagging UI (Spec C — this spec only lays the `tags` column + FTS substrate).

## Verification (named harness + real-NAS benchmark, fully specified)
- **`.dd/verify_library.py`** (extended) — deterministic, runs on a **synthetic tree + seeded DB** (no NAS needed for CI):
  - fixtures: `mktemp` tree of N folders × M files with fake sidecars; a `seed_db(5000)` helper populates `images` for the perf assert.
  - CLI: `python .dd/verify_library.py` → exit `0` all-green / `1` any-fail; prints per-AC PASS/FAIL.
  - asserts AC-1 (zero re-reads across toggle), AC-3 (delta-only rescan incl rename/delete), AC-2 (warm query < 250 ms on the seeded DB + zero NAS-prefix access), AC-4 (zero sidecar opens warm), AC-6 (filters/toggles/add-folder).
- **`.dd/perf/bench_nas.py`** — the **real 5k NAS benchmark** (PRIME's actual condition):
  - `cold` = delete `library.db` + fresh process → measure full index build.
  - `warm` = existing `library.db` + fresh process → measure `list_library()`.
  - thresholds: **warm < 250 ms**; **cold ≤ current JSON-crawl time** (no regression on the one slow path); warm run asserts **0** NAS-prefix filesystem calls.
  - artifacts: writes `lib-before.json` (AC-0) and `lib-after.json`; the delta (before.wall_ms vs after warm) is reported and must show the instant-reload win.
- `python main.py --smoke` DOM probe still green (Library filter bar renders).
