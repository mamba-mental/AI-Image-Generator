# Spec C — Find & manage my work (presets · output/findability · tags)

**Cluster:** #4 + #6 + #8 · **Type:** feature + architecture
**Grilled:** 2026-07-21 (`/grill-with-docs`), informed by `research/2026-07-21_preset-tagging-output-modeling.md`.
**Depends on:** the **SQLite Library Index** (ADR 0001) — delivered by Spec A. Glossary: `CONTEXT.md`.
**Refined:** 2026-07-21 via refine-to-spec (judge gpt-5.2, pinned) — baseline 88, this version closes the flagged gaps.

## Problem (PRIME's words)
- #4 "The setting tab is very limited… we should have places where we can actually change/save/manage parts of this app that can be recalled multiple times for image generation."
- #6 "where are these images saved to be retrieved from the library? it's almost impossible to find them with over 5000+ images."
- #8 "I don't see any of the tags on any of these images for better filtering."

## Decisions locked (grilling + research + PRIME confirmation)
1. **Presets = TWO objects + defaults** (InvokeAI/Fooocus/A1111 precedent):
   - **Style/Profile** — reusable, prompt-optional (negative + optional `{prompt}`-template + param defaults + optional model).
   - **Recipe/Shot** — reproduce one exact image (prompt+negative+seed+model+provider+full params), provider-pinned.
   - Keep `config["parameters"]` as **app defaults** (third layer).
   - **Storage:** SQLite tables in `library.db` (same store as the index, one DB to back up): `styles(id,name,negative,prompt_template,params_json,model,is_default,updated)` and `recipes(id,name,provider,model,seed,prompt,negative,params_json,is_default,updated)`. Versioned by the DB's `schema_version`.
2. **Output** = dated folders (`<output_root>/generated/YYYY-MM/`) the app **guarantees are in the Library scan set**.
3. **Tags** = rows/columns in the **SQLite Library Index** (auto-tags from metadata + manual tags), with a durable metadata copy **embedded** in each output file for portability (formats + keys defined in AC-8.6).

## Acceptance criteria (RED → GREEN — each is a binary check)

### C6 — Output & findability
- **AC-6.1 — Filename pattern (defined + collision-proof).** New generations save to `<output_root>/generated/YYYY-MM/` as **`YYYYMMDD-HHMMSS-<seq>-<seedslug>.<ext>`** where `seq` = 4-digit zero-padded **per-(folder) sequence** (next value = `MAX(seq)+1` for that month-folder, taken **atomically under a DB/file lock** so concurrent generations never collide), and `seedslug` = the seed in base36 truncated to 6 chars (`000000` when no seed). Provider/model are **index columns/tags, not folder levels.** *Check:* generate 3 images concurrently into the same month → 3 distinct filenames, all sortable, all parseable.
- **AC-6.2 — Findable immediately (bounded).** Saving an image performs a **synchronous `images` insert at save time** (not a deferred background scan); the Library query returns that image **within 1 s** of the save completing, with no manual folder-add. *Check:* save → assert the DB row exists and `list_library()` includes it, timed < 1 s.
- **AC-6.3 — Paths configurable + validated.** Output/library paths are set in Settings (folder pickers; reuse `add_library_dir`). The app **rejects a drive root (`X:\`), a filesystem root (`/`), and a UNC share root (`\\host\share`)**, and rejects a non-writable dir, with a clear inline error (this is the guard for the `I:\`-root misconfiguration). *Check:* `verify_output.py` feeds each root form + a read-only dir and asserts rejection with a message.
- **AC-6.4 — Reveal in Library.** "Reveal in Library" from a Session tile / History row jumps to that image in the Library (index lookup by path/filename). *Check:* smoke asserts the control exists and scrolls/filters to the target.

### C8 — Tags & fast search
Two tag layers: **metadata tags** (free, instant, from the sidecar) and **vision tags** (semantic, from a model that sees the image, routed through cliproxy at $0 marginal).
- **AC-8.1 — Metadata auto-tags at save/scan.** Every indexed image carries metadata auto-tags (`provider`, `model`, `seed`, `dimensions`, `date`, `has-negative-prompt`) derived from its sidecar/metadata — the user never types these, and no model call is needed.
- **AC-8.7 — Vision auto-tags via cliproxy (PRIME-directed).** *Rationale (not an AC): cliproxy bills against PRIME's 20x ChatGPT Pro sub, so this is $0-marginal vs a metered vision API — that's why cliproxy is the default endpoint.* The **engineering invariant**: vision tagging is **optional and off-by-default unless a vision endpoint is configured**, carries a **hard per-image timeout + rate budget**, and the app **remains fully functional without it** (metadata tags always apply; the library never blocks waiting on it). A **vision-capable OpenAI model served through the configured endpoint** produces semantic content tags per image (subject, setting, style, palette, composition, and a coarse content-level e.g. sfw/suggestive/explicit). Rules:
  - **Endpoint from config, never hardcoded.** Base URL + client key resolve from config/env (`OPENAI_BASE_URL`/cliproxy client key) — the app must never hardcode `api.openai.com`; a config toggle selects cliproxy (default) vs a direct paid key (opt-in). The exact model id is **pinned + verified at build time** against the live cliproxy `/v1/models` (a vision-capable OpenAI model), not assumed from memory.
  - **Background batch, cached once.** Vision tagging runs as a **non-blocking background batch** (reusing the app's existing archive-captioning batch machinery); each image is tagged once and the result cached in `images.tags` (+ a `vision_tagged_at` marker) so it never re-calls. This **unblocks the 5,000-image backfill** (previously non-goal on cost; now free via the sub).
  - **Degrades safely.** If cliproxy is unreachable, metadata tags (AC-8.1) still apply and vision tagging retries later — never blocks save or library open.
  - *Check:* `verify_tags.py` mocks the cliproxy vision call and asserts (i) the call targets the configured base URL (not api.openai.com), (ii) returned tags land in `images.tags` + FTS, (iii) an already-`vision_tagged` image is skipped on re-run.
- **AC-8.2 — Manual tags from the lightbox.** Add/remove manual tags on an image from the lightbox; tags persist in `images.tags` **and** a durable copy is embedded in the file (AC-8.6).
- **AC-8.3 — Tag chips + filter.** The Library filter bar gains **tag chips** derived from the **distinct tags in the current filtered result set** ("in view" = current query results, not the whole DB), capped at 40 chips sorted by frequency, plus a tag filter combined with the existing folder/source/type/prompt filters. Multi-tag = **AND** within tags (results narrow).
- **AC-8.4 — FTS5-fast at scale.** Tag + prompt search returns in **< 250 ms** at 5,000+ rows via `images_fts`, never a per-file NAS read at query time. *Check:* seeded 5k DB, timed.
- **AC-8.5 — Tags survive re-index.** Manual tags are durable in the DB **and** the embedded copy lets an image be re-imported with its tags if the DB is rebuilt.
- **AC-8.6 — Embedded-metadata format (byte-defined, deterministic).** The durable copy is written under a single key **`ai_studio_meta`** holding a JSON blob `{provider,model,seed,prompt,negative,params,tags[]}`: **PNG** via an `iTXt` chunk keyed `ai_studio_meta` (UTF-8, uncompressed); **JPEG/WEBP** via EXIF `UserComment` written as the exact 8-byte charset prefix **`ASCII\0\0\0`** + UTF-8 JSON bytes, **plus** an XMP `dc:subject` mirror of the `tags[]` (XMP is the tolerant fallback that survives EXIF-stripping tools). If a metadata write fails, the image still saves and the row is DB-only (logged) — embedding never blocks a save. *Check:* `verify_tags.py` writes then re-reads each format (asserting the exact `ASCII\0\0\0` prefix on JPEG/WEBP) and asserts the JSON + tags round-trip (recovered on re-import).

### C4 — Settings / presets management
- **AC-4.1 — Save Style + Recipe.** Save the current composer state as a **Style** (name it) and as a **Recipe** (name it) — one action each from the composer, persisted to the `styles`/`recipes` tables.
- **AC-4.2 — Recall + default.** Recall a saved Style or Recipe into the composer; set either as the **default** applied on launch (`is_default`, one per type).
- **AC-4.3 — Apply is explicit + idempotent + non-destructive (defined merge contract).** Applying a Style/Recipe **only touches the fields the preset defines** (a blank/undefined template field is a no-op — it **never** blanks a hand-edited field). It shows a **preview/diff** = the list of fields that will change with **before → after** values and a **confirm/cancel** gate; applying twice yields the same result. `{prompt}` substitution is defined for **0** (append prompt), **1** (replace the token), and **N** (replace all occurrences).
- **AC-4.4 — Cross-provider Recipe reuse (defined mapping).** A canonical `PARAM_MAP` (a documented table: `width/height/steps/guidance/negative/seed/…` per provider) maps known params; **unknown keys are dropped with a logged warning, never an error**. A **provider-pinned** Recipe applied while a different provider is active **warns and offers to switch — never auto-switches silently**; "reproduce exact image" is only *guaranteed* on the pinned provider (stated in the warning).
- **AC-4.5 — Settings is real config management.** API keys (done) + output/library paths + default image size + default content mode + a **Styles/Recipes manager** (list, rename, delete, set-default).

## Non-goals
- Cloud sync of presets/tags. Re-tagging the 5,000 existing archive images **by hand** (they get metadata auto-tags on index + vision auto-tags via the cliproxy backfill per AC-8.7; manual tags stay opt-in per image). A metered paid vision API for tagging is explicitly **out** — cliproxy ($0 via the Pro sub) is the tagging path.

## Verification (deterministic harness contracts)
Each harness: `python .dd/verify_<x>.py` → exit `0` all-green / `1` any-fail, prints per-AC PASS/FAIL, runs on `mktemp` fixtures + a seeded `library.db` (no NAS needed).
- **`.dd/verify_output.py`** — a generation lands in `generated/YYYY-MM/` with a parseable AC-6.1 filename; that dir is auto-registered in the scan set; the image is returned by the index < 1 s (AC-6.2); each root form (`X:\`, `/`, `\\host\share`) + a read-only dir is rejected with a message (AC-6.3); concurrent-save collision test passes.
- **`.dd/verify_tags.py`** — auto-tags derived correctly; manual add/remove round-trips through DB **and** each embedded format (PNG iTXt / JPEG-WEBP EXIF+XMP), recovered on re-import; FTS query returns the tagged image timed < 250 ms at synthetic 5k; "in view" chip set = current result set.
- **`.dd/verify_presets.py`** — Style vs Recipe persisted distinctly in their tables; apply is idempotent + non-blanking + preview-gated (asserts a hand-edited field survives applying a Style that omits it); `{prompt}` substitution correct for 0/1/N; cross-provider maps known params + drops unknown w/o error + warns on provider mismatch.
- `python main.py --smoke` DOM probe: Settings shows the presets manager + path config; Library shows tag chips.
