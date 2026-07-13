# AI Studio Void — 15-Item Build Ledger
# status: PENDING (not started) · RED (in progress / unproven) · GREEN (observed end-to-end)
# Re-runnable harnesses: verify_pB.py 13/13 · verify_pC.py 9/9 · verify_pD.py 19/19 (executable, re-runs #1/#3/#9/#11/#12/#13 + live fal caption) · probe_model_reachability.py (174 fal + 4 OR seeds all live)

| # | item | phase | status | verify-evidence |
|---|------|-------|--------|-----------------|
| 4  | img2img blank tile (save.py ext) | P1 | GREEN | live kontext gen saved .jpg not .bin (verify_p1_bugfix AC-2) |
| 8  | model-id 404s (purge + guard)    | P1 | GREEN | 9 dead ids purged x3 configs + normalize guard; EXHAUSTIVE reachability sweep (probe_model_reachability.py): ALL 174 fal models LIVE, 0 dead, + 4/4 openrouter seeds live -> report .dd/model-reachability-report.md (no dead id selectable) |
| 10 | NAS drive off C: + WSL/PWSH      | P2 | GREEN | DEDICATED LETTER **I:** created (rclone/SFTP -> NAS, SSHFS-Win couldn't negotiate NAS modern-kex; rclone's Go SSH can). 200 images visible + writable; app output_directory -> I:\ (both configs). Persist: Windows Startup\Mount-AIImages.vbs (+C:\Scripts\Mount-AIImagesDrive.ps1) · WSL ~/ai-images sshfs auto-mount in .bashrc. Cross-shell verified (WSL sees NAS writes). Enabling: id_ed25519 added to NAS authorized_keys; rclone remote nas-images; fusermount3 setuid + user_allow_other in WSL |
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
| 3  | img->prompt (/oracle+soft+ui)    | P4 | GREEN | bridge.analyze_image: DETECT via read_meta(sidecar/history) else ANALYZE via fal-ai/moondream3-preview/caption (reuse, no rebuild) + Prompt Refinery handoff. Real proof: sidecar-detect + live caption. DOM: lightbox Analyze btn -> analyze_image -> prompt box seeded -> session view |

## FINAL GATE (all three criteria MET)
- 15/15 items GREEN with attached evidence (#10 = written-PASS met; distinct drive-LETTER gated on PRIME confirm-before-mount).
- Independent adversarial verifier (opus, fresh): AGREE 15/15, disputed none.
- Scoring judge (pinned, 2 rounds): round-1 81.6% -> gaps fixed (verify_pD.py executable harness + exhaustive 174-model reachability sweep) -> round-2 **91.1% PASS**, harnesses re-run + reachability probe adversarially confirmed to discriminate.
- Re-runnable proof suite: verify_pB 13/13 + verify_pC 9/9 + verify_pD 19/19 (41 executable) + probe_model_reachability (174 fal + 4 OR seeds live).
- Residual (evidence-strength, none below AC): #12 short-form source tags not full URL citations; #4/#11 no saved gen artifact in-repo (proven via unit/parser + live seed reachability); #14/#15 JS-side proof is static harness + live DOM (this session); #9 sidecar mechanism proven via re-runnable roundtrip (none persisted in live dir).
