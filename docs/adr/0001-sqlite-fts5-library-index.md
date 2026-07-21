# 1. SQLite + FTS5 as the Library Index

Date: 2026-07-21
Status: Accepted

## Context

The Library is 5,000+ images on a NAS (SMB), where every per-file round-trip is expensive. The current index is a flat JSON file (`.cache/library_index.json`). Three separate problems all trace to that store:

- **Perf regression (#3):** reading a metadata sidecar per image on every crawl, plus a full re-crawl whenever a folder is toggled (the cache key is the enabled-folder set).
- **Findability (#6):** generated images save outside the scan path and there is no fast way to locate one image among thousands.
- **Tags (#8):** there is no tag store and no fast text search over prompts/tags.

Primary-source research into how mature tools handle this (`research/2026-07-21_preset-tagging-output-modeling.md`) found that **digiKam and Adobe Lightroom both keep a local database as the fast, authoritative index**, with embedded/sidecar metadata as the durable, portable copy — never the only store. Embedded PNG text chunks are *ancillary* per the W3C PNG spec (any decoder may drop them) and are routinely stripped by resize/re-encode/upload, so they cannot be the source of truth for search.

## Decision

Replace the JSON `.cache/library_index.json` with a **local SQLite database using an FTS5 full-text index** as the Library Index. One record per image (path, folder, provider, model, seed, dimensions, date, prompt, auto-tags, manual tags), indexed once and updated incrementally by watching for changes — never a full NAS re-crawl on open. A durable copy of each generation's metadata is **also** embedded in the output file for portability, but the DB is authoritative for browsing and search.

`sqlite3` (with FTS5) ships in Python's standard library, so this adds no third-party dependency.

## Consequences

**Positive**
- Warm Library loads become a local DB query (target < 250 ms at 5k+), independent of the NAS.
- Per-folder incremental indexing and folder-toggle become cheap (no re-crawl).
- Fast prompt/tag search (FTS5) at scale.
- One store serves perf (#3), tags (#8), and output indexing (#6).

**Negative / risks**
- A schema + migration path is introduced; the old JSON index must be migrated or rebuilt once, and future schema changes need versioning.
- The DB and on-disk metadata can drift; a rescan/repair path is required to reconcile.
- FTS5 availability depends on the SQLite build bundled with the running Python — must be verified at startup with a graceful fallback if absent.

## Alternatives considered

- **Keep the JSON index, add a separate tags file.** Smaller change, but leaves two parallel stores and gives no fast full-text search at 5k+ — rejected.
- **Embedded-metadata-only (PNG chunks / XMP).** Rejected: ancillary chunks are dropped by re-encode/upload, imported images never have them, and there is no fast search. Kept only as the *portable copy*, not the index.
