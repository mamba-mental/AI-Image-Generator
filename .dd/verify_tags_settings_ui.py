"""R3 #4 — Settings > Tags panel frontend wiring, static harness (same style as verify_pB.py).
Backend logic (rename=merge/delete/all_tags/parallel_rescan_tag) is proven executable in
.dd/verify_tag_management.py; this just locks the UI is actually wired to it.
Run: python .dd/verify_tags_settings_ui.py"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

checks = [
    ("4.19 Tags panel + rescan form exist in Settings", 'id="tagsmanager"' in index and 'id="tagrescanbtn"' in index),
    ("4.20 renderTagsManager lists + wires rename/delete per tag", "function renderTagsManager" in app_js
        and 'api().rename_tag(' in app_js and 'api().delete_tag(' in app_js),
    ("4.21 rescan form calls start_tag_rescan with the typed tag+model", 'api().start_tag_rescan(tag, model)' in app_js),
    ("4.22 progress is polled (not fire-and-forget) via rescan_tag_status", "function pollTagRescan" in app_js
        and "api().rescan_tag_status()" in app_js and "setInterval(" in app_js),
    ("4.23 poll loop is stoppable (no leaked interval across repeated rescans)", "function stopTagRescanPoll" in app_js
        and "clearInterval(" in app_js),
    ("4.24 tags panel refreshes when Settings opens (same trigger as presets/vision status)",
        "renderTagsManager();" in app_js and "renderPresetsManager();" in app_js),
    ("4.25 an open Library tab is force-refreshed after a bulk tag edit (stale-tile guard)",
        "function refreshLibraryIfOpen" in app_js and "refreshLibraryIfOpen();" in app_js),
    ("4.26 rescan model field pre-fills from the live vision_tagging_status (no fabricated model list)",
        's.model || ""' in app_js and "tagrescan-model" in app_js),
    ("4.27 reuses the existing .presetrow/.presetmanager visual language for tag rows (no new CSS)",
        'class="presetrow" data-tag=' in app_js),
    # PROVEN LIVE: PRIME's real captioned library has 34,499 distinct tags (near-unique vision-
    # caption phrases) — rendering all of them would repeat R3 #1's exact perf bug.
    ("4.28 tag list is CAPPED (not rendering all 34k+ real tags as DOM rows)",
        "TAGS_MANAGER_CAP" in app_js and ".slice(0, TAGS_MANAGER_CAP)" in app_js),
    ("4.29 a client-side search exists so a specific tag is reachable past the cap",
        'id="tagsearch"' in index and "renderTagsManagerList" in app_js
        and "filtered=q?all.filter(" in app_js.replace(" ", "")),
]

fails = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
print(f"\n{len(checks)-len(fails)}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
