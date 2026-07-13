# AI Studio Void — 15-Item Build Ledger
# status: PENDING (not started) · RED (in progress / unproven) · GREEN (observed end-to-end)

| # | item | phase | status | verify-evidence |
|---|------|-------|--------|-----------------|
| 4  | img2img blank tile (save.py ext) | P1 | GREEN | live kontext gen saved .jpg not .bin (verify_p1_bugfix AC-2) |
| 8  | model-id 404s (purge + guard)    | P1 | GREEN | 9 dead ids purged x3 configs, grep-0; normalize guard AC-4 |
| 10 | NAS drive off C: + WSL/PWSH      | P2 | GREEN* | AC (location created + repoint + migrate w/ count) MET: NAS folder /volume1/DevProjects/AI-Studio-Void (off C:, 13T vol); output_directory repointed both configs -> Z:\AI-Studio-Void; 200->200 migrated (count verified); write-test OK. *distinct drive-LETTER (I:) offered pending PRIME confirm-before-mount (SMB off on NAS -> needs WinFsp-launcher SSHFS entry) |
| 14 | ring-buffer error log + panel    | P2 | GREEN | engine/logbuf.py deque(500); jobs.emit logs all events + format_exc; bridge get_logs/clear_logs. Real-job proof: error captured w/ traceback, search 'boom-xyz'=1 'zzz'=0. DOM: LOGS tab, 3 rows, error+detail, search->1, copy+clear |
| 13 | multi-key pool + auto-swap       | P2 | GREEN | engine/keypool.py pool (primary+_2..9+comma), resolve_keys builds pools, jobs._run rotates on 401/403/429. Real-job: 429 on k1 -> "switching to key 2/4" -> job_done on k3. UI: key_pools in get_state -> "N keys (auto-swap)" in settings |
| 2  | S/M/L library grid size          | P3 | GREEN | gridpick 3 btns (index.html); setGrid+applyGrid+persist (app.js); css auto-fill/columns per data-grid. DOM: grid_l_applied+grid_s_applied+grid_persisted=true |
| 7  | lightbox + open-editor + folder  | P3 | GREEN | openLightbox (app.js) + bridge.open_in_editor 'edit'-verb+fallback+missing-negative (proven). DOM: tile-click lightbox_open+has_img, lb_actions=edit,folder,save, editor_called+folder_called+closed=true |
| 9  | metadata overlay                 | P3 | GREEN | save.write_sidecar (dims/bytes/ts real-file proof) + bridge.read_meta sidecar->history->none (proven). DOM: overlay meta_model(full)+prompt+seed+size+source=true |
| 15 | staged status + error popup      | P3 | GREEN | jobs emits 'saving…' stage + job_error carries detail(full trace). Real-job proof: queued->saving->done; detail has Traceback. DOM: errpop opens on job_error, errbody has trace, copy->clipboard, close |
| 5  | labeled safety-tolerance         | P3 | GREEN | SAFETY_LABELS web/app.js; DOM: 6 labeled options rendered |
| 6  | sync-mode + param tooltips       | P3 | GREEN | PARAM_HELP web/app.js renderParams; DOM: 4 tooltips+icons |
| 11 | OpenRouter backend               | P4 | GREEN | engine/backends/openrouter_api.py (chat/completions image modality, data-URI->PIL); registered in BACKENDS + config KEY_FIELDS + services + _VALIDATE + balance. REAL-GEN: 1024x1024 png via google/gemini-2.5-flash-image (key from PRIME keys doc, not echoed). Parser+negative funcproof. DOM: selectable, models populate, settings row |
| 12 | per-family prompting refs        | P4 | GREEN | PROMPT_GUIDE per family + renderPromptGuide + negative gating by family (app.js). DOM: FLUX->guide+neg hidden; Imagen->guide+neg shown |
| 1  | max-coverage NSFW posture        | P4 | GREEN | NSFW_POLICY 6-provider reference panel (DOM 6 rows, openai hard-no); Content toggle -> collectParams enable_safety_checker/safety_tolerance via real GENERATE both directions; fal backstop wires FLUX_DISABLE_SAFETY (funcproof: default false + UI-wins + no-422 on unsupported) |
| 3  | img->prompt (/oracle+soft+ui)    | P4 | GREEN | bridge.analyze_image: DETECT via read_meta(sidecar/history) else ANALYZE via fal-ai/moondream3-preview/caption (reuse, no rebuild). Real proof: sidecar-detect + live caption ("solid red square centered..."). DOM: lightbox Analyze btn -> analyze_image -> prompt box seeded -> session view |
