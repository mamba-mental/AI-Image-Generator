# Preset shape, image tagging, and output organisation — how mature AI image tools model it

**Date:** 2026-07-21
**For:** AI Studio Void (pywebview desktop, multi-provider: fal / Novita / Together / Runware / Replicate / OpenAI)
**Question:** How should a desktop AI image-gen app model **saved generation settings**, **image tagging**, and **output organisation**?
**Method:** Primary-source only where possible — reading the actual source files, data-model classes, official docs, and issue trackers of the tools that own each behaviour. Every claim carries an inline link. Anything I could not trace to a first-party source is labelled **UNVERIFIED**.

**Verification legend:** ✅ traced to source code or first-party spec · 📄 traced to first-party docs/issue tracker · ⚠️ UNVERIFIED against a primary source (secondary/inferred).

---

## §1 — PRESET SHAPE: one object or two?

The blocking question is whether tools persist **ONE** object (prompt + params + model together) or **TWO+ distinct** objects (a reusable *style/profile* WITHOUT the prompt, vs a re-runnable *shot/recipe* WITH prompt + seed). The finding: **mature tools split these, but under confusing names.** Almost universally there is (a) a lightweight, reusable *style* that is prompt-fragment-first and often carries NO seed/model, and (b) a separate, heavier reproduce-this-exact-image path (embedded generation metadata or a full "preset/template") that carries everything.

### Per-tool summary table

| Tool | Object model | What is persisted | Prompt part of it? | Format / location | Source |
|---|---|---|---|---|---|
| **A1111 — styles** | Style (prompt-only fragment) | `name`, `prompt`, `negative_prompt` only. No seed/CFG/steps/sampler/model. | Yes — as a template fragment with a `{prompt}` hole | `styles.csv` (3 columns) | ✅ [styles.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/styles.py) |
| **A1111 — PNG-info** | Re-runnable shot (implicit) | Full param string: prompt, negative, steps, sampler, seed, CFG, size, model hash… | Yes | `parameters` tEXt chunk in each PNG; "Send to txt2img" re-hydrates | ✅ [images.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/images.py), [infotext_utils.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/infotext_utils.py) |
| **A1111 — config** | App/UI defaults | `config.json` = settings (`opts`, incl. model + all output paths); `ui-config.json` = per-widget default values | Negative prompt default can live in ui-config | Two JSON files | 📄 [issue #6411](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/6411), ✅ [shared_options.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/shared_options.py) |
| **ComfyUI** | Re-runnable shot = the whole graph | Full API `prompt` graph + UI `workflow` JSON | Yes (prompt node is in the graph) | Embedded as `prompt` + `workflow` tEXt keys in PNG; reuse by dragging PNG back in | ✅ [nodes.py `SaveImage`](https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/nodes.py) |
| **InvokeAI — style presets** | Style (prompt template, two-object) | `positive_prompt`, `negative_prompt` only; `type` = `user`/`default`. No params, no model. | Yes — template with `{prompt}` placeholder | DB record (`StylePresetRecordDTO`) | ✅ [style_preset_records_common.py](https://raw.githubusercontent.com/invoke-ai/InvokeAI/main/invokeai/app/services/style_preset_records/style_preset_records_common.py), 📄 [prompt-templates support article](https://support.invoke.ai/support/solutions/articles/151000197193-using-prompt-templates) |
| **InvokeAI — image metadata** | Re-runnable shot (implicit) | JSON blob: prompt, model, seed, sampler + full node graph | Yes | `invokeai_metadata` + `invokeai_graph` tEXt/iTXt chunks | 📄 [RFC #266](https://github.com/invoke-ai/InvokeAI/issues/266) |
| **Fooocus — `sdxl_styles`** | Style (prompt-only) | `name`, `prompt` (with `{prompt}`), `negative_prompt` | Yes — template fragment | JSON array files | ✅ [sdxl_styles_fooocus.json](https://raw.githubusercontent.com/lllyasviel/Fooocus/main/sdxl_styles/sdxl_styles_fooocus.json) |
| **Fooocus — `presets/*.json`** | Full recipe (everything) | `default_model`, `default_refiner`, `default_loras`, `default_cfg_scale`, `default_sampler`, `default_scheduler`, `default_styles`, `default_prompt`, `default_prompt_negative`, `default_aspect_ratio`, `default_performance`, asset download lists… | Yes (`default_prompt`) | JSON preset files | ✅ [presets/default.json](https://raw.githubusercontent.com/lllyasviel/Fooocus/main/presets/default.json) |
| **SD.Next — styles** | Hybrid style (prompt + params + wildcards) | Prompt (with `{prompt}` or append), generation **parameters**, and wildcards | Yes | One JSON file per style in `models/styles` | 📄 [SD.Next Styles docs](https://vladmandic.github.io/sdnext-docs/Styles/) |
| **Midjourney** | Three separate mechanisms (all distinct) | `--style raw`/style-tuner (look), `--p` personalization profile (model-tuned prefs), `/prefer option set` (named bundle of param/text snippets) | Only `/prefer option` can carry text | Server-side profiles / Discord option sets | 📄 [Personalization](https://docs.midjourney.com/hc/en-us/articles/32433330574221-Personalization), [Parameter List](https://docs.midjourney.com/hc/en-us/articles/32859204029709-Parameter-List) |
| **Leonardo.ai** | Built-in preset styles (enumerated) | Named presets (`ANIME`, `PHOTOGRAPHY`, `DYNAMIC`, `RENDER_3D`…) with pre-configured params | No (style only) | Enum values in API | 📄 [commonly-used API values](https://docs.leonardo.ai/docs/commonly-used-api-values) · custom user-saved recipe object ⚠️ UNVERIFIED |
| **NightCafe** | Templates = full recipe **with placeholders** | Prompt, model, settings, styles, keywords **+ fill-in-the-blank elements** | Yes (with template holes) | Server-side template | 📄 [NightCafe Templates](https://nightcafe.studio/blogs/blog/nightcafe-templates-ai-art-workflows) |

### Detailed findings

**AUTOMATIC1111** persists a **style** as a 3-column CSV row. The data class is a NamedTuple `PromptStyle(name, prompt, negative_prompt, path)`, and only `name, prompt, negative_prompt` are written to `styles.csv` (the `path` field is filtered out on write) ([styles.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/styles.py)). A style is **prompt-fragment-only** — it holds *no* seed, CFG, steps, sampler, size, or model. The style prompt is merged into the user prompt by `merge_prompts`: if the style text contains the literal token `{prompt}` it is substituted, otherwise the two strings are comma-joined ([styles.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/styles.py)). The **re-runnable "shot"** is a *separate* mechanism — the full generation string embedded in each PNG under the `parameters` tEXt key (`read_info_from_image` does `items.pop('parameters')`) ([images.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/images.py)), parsed back by `parse_generation_parameters` and re-applied through the "Send to txt2img" paste path ([infotext_utils.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/infotext_utils.py)). App-level defaults are a third layer: `config.json` stores settings/`opts` (checkpoint, output paths), while `ui-config.json` stores per-widget default values ([issue #6411](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/6411)). **So A1111 is effectively three objects: style (fragment) · PNG-info (shot) · config (defaults).**

**ComfyUI** has no per-parameter preset at all — the reusable unit is the **entire graph**. `SaveImage` embeds two tEXt keys: `metadata.add_text("prompt", json.dumps(prompt))` (the executed API graph) and `metadata.add_text(x, json.dumps(extra_pnginfo[x]))` for each extra key (the UI `workflow`). Embedding is skipped when `args.disable_metadata` is set ([nodes.py](https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/nodes.py)). Reuse = drag the PNG back onto the canvas; the shot IS the file.

**InvokeAI** is the cleanest **two-object** design. A *style preset* stores **only** `positive_prompt` + `negative_prompt` (Pydantic `PresetData`), with a top-level record of `name`, `preset_data`, `type` (`user`/`default`), `is_public` — **no params, no model** ([style_preset_records_common.py](https://raw.githubusercontent.com/invoke-ai/InvokeAI/main/invokeai/app/services/style_preset_records/style_preset_records_common.py)). The `{prompt}` placeholder is not in the data-model validation because it is applied at graph-build time; the docs confirm the template semantics — e.g. `highly detailed photo of {prompt}, award-winning` with a live preview of subject-vs-style ([prompt-templates support article](https://support.invoke.ai/support/solutions/articles/151000197193-using-prompt-templates)). The re-runnable shot is again a *separate* channel: generation metadata embedded in the output PNG as `invokeai_metadata` / `invokeai_graph` tEXt chunks, JSON-encoded, auto-written on save ([RFC #266](https://github.com/invoke-ai/InvokeAI/issues/266)).

**Fooocus** literally ships the two objects as two directories: `sdxl_styles/*.json` = prompt-only styles (`name`, `prompt` with `{prompt}`, `negative_prompt`) ([sdxl_styles_fooocus.json](https://raw.githubusercontent.com/lllyasviel/Fooocus/main/sdxl_styles/sdxl_styles_fooocus.json)); `presets/*.json` = a **full recipe** (model, refiner, loras, cfg, sampler, scheduler, styles, prompts, aspect ratio, performance, and even model-download lists) ([presets/default.json](https://raw.githubusercontent.com/lllyasviel/Fooocus/main/presets/default.json)). This is the sharpest real-world example of the split.

**SD.Next** deliberately *merges* prompt + parameters into one "style" object (each is a JSON file that can carry positive/negative prompt, generation parameters, and wildcards; `{prompt}` replaces-or-appends) ([SD.Next Styles docs](https://vladmandic.github.io/sdnext-docs/Styles/)) — a useful counter-example showing the hybrid model and its "Apply selected style to prompt" bake-in step.

**Hosted tools** confirm the pattern from the product side: **Midjourney** keeps *three* unrelated persistence tools (style-tuner look, `--p` personalization profile, `/prefer option` named bundles) rather than one preset; **Leonardo** exposes enumerated built-in preset styles (whether a user can save a *custom recipe object* is ⚠️ UNVERIFIED from primary docs); **NightCafe Templates** is the one hosted example of a single full-recipe object that explicitly includes **fill-in-the-blank placeholders** — the same `{prompt}`-hole idea, generalised ([NightCafe Templates](https://nightcafe.studio/blogs/blog/nightcafe-templates-ai-art-workflows)).

---

## §2 — KNOWN FAILURE MODES (with issue numbers)

The dominant, recurring failure is the **collision the two-object split exists to prevent**: users want styles that *also* save parameters, and simultaneously complain that presets *silently overwrite the parameters they hand-edited*. Both symptoms come from conflating style and recipe.

**Styles silently overriding / not reflecting manually-edited fields**
- A1111 [#12930](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/12930) — applying a style generates correctly but leaves **both prompt boxes empty**, so the user cannot see or edit what was applied (the classic silent-override).
- A1111 [#7273](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/7273) — "Apply selected styles to current prompt" does nothing visible.

**Presets resetting parameters the user changed by hand**
- Fooocus [#2609](https://github.com/lllyasviel/Fooocus/issues/2609) — switching presets **resets `default_image_number` to 1 every time**; adding it to a custom preset didn't help.
- Fooocus [#775](https://github.com/lllyasviel/Fooocus/issues/775) — user must **manually re-adjust settings every launch** (no "save full settings").
- Fooocus [#2373](https://github.com/lllyasviel/Fooocus/issues/2373) — a preset's steps/CFG are wrong for some models and must be re-overridden every session.
- Fooocus [#3405](https://github.com/lllyasviel/Fooocus/issues/3405) — custom preset fails to load.

**"Make styles carry params" — the demand for one-object, and why it's contentious**
- A1111 [#10725](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/10725) — feature request: saved styles end up **without Seed, CFG, Steps, Sampler, Width/Height, Override Settings**, so styles "generate differently." This is the exact pressure toward a full-recipe object — but granting it naively produces the Fooocus #2609/#2373 override complaints.

**Prompt-template placeholder pitfalls**
- A1111 [#14005](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/14005) — **two `{prompt}` tokens in one styles.csv line breaks the Paste button.** Placeholder substitution needs to be defined for 0, 1, and N occurrences.
- Style applied twice / prompt duplicated: A1111 [#1383](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/1383) and [#559](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/559) — applying a style **appends its text twice**. Apply must be idempotent.

**Params that don't survive a round-trip / don't map across pipelines**
- A1111 [#10896](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/10896) — image parameters **not stored when sent to extras/upscaling** (a stage drops the metadata).
- A1111 [#11409](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/11409) — PNG-info → txt2img send-parameters breakage.
- Cross-model/provider mapping: because a saved "shot" pins seed + model hash + sampler name, it is inherently provider-specific — sampler/scheduler vocabularies differ between backends, so a recipe captured on one provider will not reproduce on another. (This is intrinsic to the design rather than a single bug; the A1111 send-to-extras failures above illustrate that even *within one tool* a param set can silently fail to carry across stages.)

**Takeaway for the app:** apply must be **explicit and idempotent**, must **never blank or silently replace** a hand-edited field, and placeholder substitution must be defined for 0/1/N `{prompt}` occurrences.

---

## §3 — TAGGING AT SCALE (5,000+ images)

### What the generation tools actually write (embedded metadata)

- **A1111** writes one Latin-1/UTF-8 tEXt chunk keyed **`parameters`** containing the human-readable param string ([images.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/images.py)).
- **ComfyUI** writes JSON under **`prompt`** (API graph) and **`workflow`** (UI graph) tEXt keys ([nodes.py](https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/nodes.py)).
- **InvokeAI** writes JSON under **`invokeai_metadata`** / **`invokeai_graph`**, choosing tEXt vs iTXt based on whether the content is Latin-1 ([RFC #266](https://github.com/invoke-ai/InvokeAI/issues/266)).

All of these are **auto-tags derived from generation metadata** — the tool writes them, the user never types them.

### The PNG text-chunk formats (get these right)

The W3C PNG spec defines three textual chunk types, all **ancillary** (§11.3.3): **`tEXt`** (Latin-1/ISO-8859-1, uncompressed), **`zTXt`** (Latin-1 + deflate compression), and **`iTXt`** (UTF-8, "international textual data") ([W3C PNG spec](https://www.w3.org/TR/png/)). Because they are ancillary (lowercase second letter), the spec explicitly says a decoder "can safely ignore the chunk" — i.e. **any editor is permitted to drop them.** For JPEG/WebP the equivalent stores are EXIF and **XMP** (Adobe's RDF/XML metadata standard, embeddable in-file or as a `.xmp` sidecar) ([XMP — Wikipedia](https://en.wikipedia.org/wiki/Extensible_Metadata_Platform)). PNG text chunks are **separate from EXIF/XMP**, so a tool that only strips EXIF leaves PNG chunks intact — and vice-versa ([AI Metadata Cleaner](https://aimetadatacleaner.com/blog/removing-stable-diffusion-metadata-generation-parameters)).

### Durability: does embedded metadata survive?

**No, not reliably.** Embedded PNG text chunks are dropped by ordinary editing and transport:
- Re-saving a PNG in Photoshop, or resizing/re-encoding, can strip the generation chunks ([Civitai metadata-error guide](https://comingsoonwp.com/how-to-fix-civitai-couldnt-detect-valid-metadata-in-this-image-error/)).
- Downloading from Discord / Twitter / Telegram typically strips all embedded metadata ([AI Metadata Cleaner](https://aimetadatacleaner.com/blog/removing-stable-diffusion-metadata-generation-parameters)).
- Within a single tool, a processing stage can drop it (A1111 [#10896](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/10896)).
- **Imported** images never had it: InvokeAI [#2464](https://github.com/invoke-ai/InvokeAI/issues/2464) — uploaded images lose metadata, because the store is embed-only.

**Sidecars** trade different risks: an `.xmp` sidecar survives re-encode of the image (it's a separate file) and is the safe choice for RAW, but it **desyncs or is lost if the image is moved/copied by other software** ([digiKam XMP sidecar release notes](https://www.digikam.org/news/2011-05-12_new_features_in_digikam_2.0_xmp_sidecar/); [digiKam metadata settings](https://docs.digikam.org/en/setup_application/metadata_settings.html)).

### How mature DAMs solve this (prior art)

**digiKam** is explicit and instructive: metadata write target is configurable to **"write to image only," "write to XMP sidecar only," or "write to both"**, and it notes sidecars are *faster* to write and safer for RAW, but you must keep the sidecar with the image if you move files with other software ([digiKam metadata settings](https://docs.digikam.org/en/setup_application/metadata_settings.html)). Critically, digiKam does **not** browse the filesystem on every open — it maintains a **database index** (SQLite by default; MySQL optional) as the fast source of truth, with the in-file/sidecar metadata as the durable, portable copy. **Adobe Lightroom** uses the same architecture: a catalog (database) for fast search/browse, plus embedded XMP or XMP sidecars for RAW as the portable copy. **XnView MP** reads/writes IPTC/XMP/EXIF into files.

The common, converged pattern across all serious tools: **a local database is the authoritative, fast index; embedded/sidecar metadata is the durable, portable copy — never the only store.**

### What makes search fast at 5k+

A filesystem scan that opens every file to read its chunks is O(files) with a slow per-file cost — untenable on SMB/NAS where each round-trip is expensive (your own constraint, and matched by prior findings in this repo about network-drive galleries needing a **persisted local index + local thumbnail cache**). The answer every DAM uses: **index once into a local SQLite database and query the DB** (with **FTS5** full-text for prompt/tag search). digiKam/Lightroom both do exactly this.

---

## §4 — OUTPUT ORGANISATION

### On-disk layout each tool uses

- **A1111** — default `outputs/txt2img-images` (and `outputs/img2img-images`, `outputs/grids`), with **`save_to_dirs = True`** and **`directories_filename_pattern = "[date]"`**, producing **`outputs/txt2img-images/YYYY-MM-DD/`** dated subfolders. The `FilenameGenerator` resolves tokens including `[date]` → `strftime('%Y-%m-%d')`, `[seed]`, `[prompt_words]`, etc. ([shared_options.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/shared_options.py), [images.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/images.py)). This dated-folder convention is the de-facto standard.
- **ComfyUI** — flat **`output/`** directory (`self.output_dir = folder_paths.get_output_directory()`), filenames prefixed `ComfyUI` with a zero-padded counter (`ComfyUI_00001_.png`) ([nodes.py](https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/nodes.py)). Discovery is via the embedded-workflow load path (drag PNG in) and the queue history, not a dated tree.
- **InvokeAI** — images live under an images directory but the **gallery is DB-driven** (boards, records), so discovery is a database query, not a filesystem walk ([RFC #266](https://github.com/invoke-ai/InvokeAI/issues/266)).

### Discovery model: watch vs scan vs index

- A1111 / ComfyUI effectively rely on the tool being the only writer and reading its own known output dir.
- InvokeAI / DAMs (digiKam, Lightroom) use **index-then-query**: a one-time scan builds a database, then browsing/search hits the DB; a filesystem *watch* (or manual "rescan") incrementally updates the index. This is the model that scales to 5k+ on slow storage.

---

## Recommendations

### (a) Preset modelling — **TWO objects, not one**

Persist two distinct, named object types plus keep the existing app-defaults blob as a third layer:

1. **Style / Profile** (reusable across subjects, prompt-optional).
   - Fields: `name`, `negative_prompt`, an optional `positive_prompt` **template** that may contain a `{prompt}` placeholder, and a **params dict** of *defaults* (width, height, steps, guidance, prompt_strength) — optionally `model` + loras.
   - Prompt is **not required**; if a `{prompt}` token is present, substitute the user's prompt into it, otherwise append. Define behaviour for 0/1/N `{prompt}` tokens (A1111 [#14005](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/14005)) and make apply **idempotent** (A1111 [#1383](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/1383), [#559](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/559)).
   - Direct precedent: InvokeAI style presets, Fooocus `sdxl_styles`, A1111 styles.

2. **Recipe / Shot** (reproduce THIS exact image, provider-pinned).
   - Fields: exact `prompt`, `negative_prompt`, `seed`, `model` + `provider`, and the **full resolved params**. This is what "regenerate this" and "send back to the composer" use.
   - Precedent: A1111 PNG-info round-trip, ComfyUI embedded workflow, NightCafe Templates.
   - **Trade-off:** a Recipe is provider-specific (seed/model/sampler vocabularies differ across fal/Novita/Together/…), so store it with its provider tag and, on cross-provider reuse, map known params and **degrade unknown keys gracefully** rather than failing. This is the intrinsic limit shown by the round-trip failures (A1111 [#10896](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/10896), [#11409](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/11409)).

   **Hard rule (from the failure data):** applying a Style or Recipe must be **explicit** and must **never silently overwrite or blank a manually-edited field** — show a preview/diff first (InvokeAI's preview; SD.Next's explicit "apply to prompt"). Silent override is the single most-complained-about behaviour (A1111 [#12930](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/12930); Fooocus [#2609](https://github.com/lllyasviel/Fooocus/issues/2609), [#2373](https://github.com/lllyasviel/Fooocus/issues/2373)).

   > The current app persists exactly one unnamed `config["parameters"]` blob — that is the *third* layer (app defaults), not either object above. Keep it, but add the two named object types on top.

### (b) Where tags live — **DB-primary, embed-for-portability**

- **Authoritative store = a local SQLite database with FTS5**, holding the row per image: file path, provider, model, seed, dimensions, sampler, date, **auto-tags** (derived from generation metadata by the app) and **manual/user tags**. This is the digiKam/Lightroom architecture and the only thing that is fast at 5k+ on SMB (matches this repo's own prior finding that network-drive galleries need a persisted local index + thumbnail cache — never re-crawl).
- **Also embed a durable copy** of the generation metadata into each PNG (a JSON `parameters`-style tEXt/iTXt chunk, following the A1111/Invoke/Comfy convention) so images stay **self-describing and re-importable** if the DB is ever lost or the image leaves the app.
- **Do not make embedded metadata the only store:** PNG text chunks are ancillary and the spec permits any decoder to drop them ([W3C PNG spec](https://www.w3.org/TR/png/)); they're stripped by re-encode/resize/social upload ([AI Metadata Cleaner](https://aimetadatacleaner.com/blog/removing-stable-diffusion-metadata-generation-parameters)); and imported images never had them (InvokeAI [#2464](https://github.com/invoke-ai/InvokeAI/issues/2464)).
- **Auto vs manual tags:** the app writes auto-tags (provider, model, seed, dimensions, date, has-negative-prompt) at save time; the user only ever types *manual* tags. Both live as rows/relations in the DB.
- **XMP sidecars = optional interop layer**, not the primary store — they survive re-encode but desync on external moves ([digiKam](https://docs.digikam.org/en/setup_application/metadata_settings.html)). Offer "also write XMP sidecar" as a setting (digiKam's three-way choice), default off.

### (c) On-disk output layout — **dated folders, inside the scan path, indexed not scanned**

- **Layout:** `outputs/YYYY-MM-DD/` dated subfolders (the A1111 `[date]` convention — [shared_options.py](https://raw.githubusercontent.com/AUTOMATIC1111/stable-diffusion-webui/master/modules/shared_options.py)). Chronological browsing is the natural default; put **provider/model as DB columns/tags, not folder levels** (per-model deep trees fragment chronological browsing and duplicate the tag dimension).
- **Fix the current findability bug directly:** the output directory MUST be inside (or registered into) the library's scan-path list. Make the library scan path a configurable **list** that always includes the active output dir — this is the whole reason generated images are currently unfindable.
- **Filenames:** sortable + collision-proof — zero-padded sequence counter plus a short seed/slug (`00042-<seed>.png`), à la ComfyUI's counter and A1111's `[seq]-[seed]` tokens.
- **Discovery:** **index once into SQLite, then watch** for new files and incrementally update — never full-scan the NAS on each library open (your SMB round-trip constraint + prior local-index finding).

---

### Single most surprising finding

The mature open-source tools have **already converged on the two-object split** (style vs recipe) — but the single loudest, most recurring user complaint is *both sides of the same collision at once*: people beg for "styles that also save my parameters" (A1111 [#10725](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/10725)) **while simultaneously** raging that "presets keep resetting the parameters I hand-edited" (Fooocus [#2609](https://github.com/lllyasviel/Fooocus/issues/2609), [#775](https://github.com/lllyasviel/Fooocus/issues/775), [#2373](https://github.com/lllyasviel/Fooocus/issues/2373)). The same "make it one object that does everything" instinct produces *both* pains. The fix is not a smarter single object — it's a clean **two-object split with explicit, idempotent, never-silent apply.** A close second: **embedded PNG metadata is genuinely unreliable as a store** — it's an ancillary chunk the spec says any decoder may drop, and it's routinely stripped by resize/re-encode/upload — which is precisely why every serious library tool keeps a **database index** and treats the in-file embed as a convenience copy, not the source of truth.

---

*Sources are linked inline throughout. Primary source types used: tool source code (A1111, ComfyUI, InvokeAI, Fooocus on GitHub), first-party docs (SD.Next, Midjourney, Leonardo, NightCafe, digiKam, W3C PNG spec), and first-party issue trackers. Items marked ⚠️ UNVERIFIED (Leonardo custom-recipe save; digiKam default DB engine stated as documented-but-not-re-fetched here) were not confirmed against a primary source in this pass.*
