# AI Studio Void — 15-Item Build Ledger
# status: PENDING (not started) · RED (in progress / unproven) · GREEN (observed end-to-end)

| # | item | phase | status | verify-evidence |
|---|------|-------|--------|-----------------|
| 4  | img2img blank tile (save.py ext) | P1 | GREEN | live kontext gen saved .jpg not .bin (verify_p1_bugfix AC-2) |
| 8  | model-id 404s (purge + guard)    | P1 | GREEN | 9 dead ids purged x3 configs, grep-0; normalize guard AC-4 |
| 10 | NAS drive off C: + WSL/PWSH      | P2 | PARTIAL | folder /volume1/DevProjects/AI-Studio-Void created; 200->200 migrated; output_directory repointed both configs -> Z:\AI-Studio-Void; write-test OK. LETTER (I:) gated on PRIME a/b + confirm-before-mount |
| 14 | ring-buffer error log + panel    | P2 | GREEN | engine/logbuf.py deque(500); jobs.emit logs all events + format_exc; bridge get_logs/clear_logs. Real-job proof: error captured w/ traceback, search 'boom-xyz'=1 'zzz'=0. DOM: LOGS tab, 3 rows, error+detail, search->1, copy+clear |
| 13 | multi-key pool + auto-swap       | P2 | PENDING | |
| 2  | S/M/L library grid size          | P3 | GREEN | gridpick 3 btns (index.html); setGrid+applyGrid+persist (app.js); css auto-fill/columns per data-grid. DOM: grid_l_applied+grid_s_applied+grid_persisted=true |
| 7  | lightbox + open-editor + folder  | P3 | GREEN | openLightbox (app.js) + bridge.open_in_editor 'edit'-verb+fallback+missing-negative (proven). DOM: tile-click lightbox_open+has_img, lb_actions=edit,folder,save, editor_called+folder_called+closed=true |
| 9  | metadata overlay                 | P3 | GREEN | save.write_sidecar (dims/bytes/ts real-file proof) + bridge.read_meta sidecar->history->none (proven). DOM: overlay meta_model(full)+prompt+seed+size+source=true |
| 15 | staged status + error popup      | P3 | GREEN | jobs emits 'saving…' stage + job_error carries detail(full trace). Real-job proof: queued->saving->done; detail has Traceback. DOM: errpop opens on job_error, errbody has trace, copy->clipboard, close |
| 5  | labeled safety-tolerance         | P3 | GREEN | SAFETY_LABELS web/app.js; DOM: 6 labeled options rendered |
| 6  | sync-mode + param tooltips       | P3 | GREEN | PARAM_HELP web/app.js renderParams; DOM: 4 tooltips+icons |
| 11 | OpenRouter backend               | P4 | PENDING | |
| 12 | per-family prompting refs        | P4 | PENDING | |
| 1  | max-coverage NSFW posture        | P4 | PENDING | |
| 3  | img->prompt (/oracle+soft+ui)    | P4 | PENDING | |
