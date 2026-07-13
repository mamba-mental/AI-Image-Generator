# Batch B — Gallery (items #2, #7, #9) — dd-router contract

Status: RED (author before build; verify_pB.py must go RED→GREEN)

## #2 — Grid-size S/M/L (persisted)
- AC-2.1: `index.html` has a grid-size picker (`#gridpick`) with S / M / L buttons.
- AC-2.2: `app.js` `setGrid(name)` sets `data-grid` on the gallery + library containers AND persists via `set_config({ui_grid})`.
- AC-2.3: `boot()` restores `cfg.ui_grid`.
- AC-2.4: `app.css` sizes columns per `[data-grid="s|m|l"]` on `.gallery` and `.wmason`.
- Runtime: DOM shows the buttons; clicking L widens tiles vs S; reload keeps the choice.

## #7 — Click-to-enlarge lightbox + open-in-editor + open-folder
- AC-7.1: `index.html` has a `#lightbox` overlay container.
- AC-7.2: `app.js` `openLightbox(file, meta)` renders the enlarged media in `#lightbox` (in-app, no new window) and wires close.
- AC-7.3: lightbox has three working actions — Open in editor (`api().open_in_editor`), Open folder (`api().open_output_folder`), Save As (`api().save_as`).
- AC-7.4: `bridge.py` has `open_in_editor(path)` using `os.startfile(path, "edit")` with fallback to `os.startfile(path)`.
- AC-7.5: tile/image click opens the lightbox (session gallery + library).
- Runtime: DOM — click a tile → `#lightbox` visible with the img; buttons present; open_in_editor callable.

## #9 — Metadata overlay from per-image sidecar
- AC-9.1: `save.py` has `write_sidecar(media_path, meta)` writing `<media>.json`.
- AC-9.2: `jobs.py` writes a sidecar per saved file (service/model/prompt/seed/params/ts/size).
- AC-9.3: `bridge.py` `read_meta(filename)` returns sidecar meta; falls back to `history.jsonl` (match by basename) when no sidecar.
- AC-9.4: `app.js` lightbox renders a metadata overlay from `read_meta` (model, prompt, seed, params, dims, time).
- Runtime: open a real image in the lightbox → overlay shows model+prompt+seed+params from its sidecar; an image with no sidecar still shows meta via history fallback.

## Evidence rule
Each AC: file:line + code snippet + a runtime DOM/functional receipt. Ledger GREEN only on observed evidence.
