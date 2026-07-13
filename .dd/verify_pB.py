"""Batch B static harness — checks code artifacts for #2/#7/#9 exist.
Runtime DOM proof is done separately in the browser. RED before build, GREEN after."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
app_css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
bridge = (ROOT / "bridge.py").read_text(encoding="utf-8")
save = (ROOT / "engine" / "save.py").read_text(encoding="utf-8")
jobs = (ROOT / "engine" / "jobs.py").read_text(encoding="utf-8")

checks = [
    # #2 grid
    ("2.1 gridpick in html", 'id="gridpick"' in index),
    ("2.2 setGrid + persist", "function setGrid" in app_js and "ui_grid" in app_js),
    ("2.3 boot restores ui_grid", "cfg.ui_grid" in app_js),
    ("2.4 css grid sizing", '[data-grid="s"]' in app_css or "[data-grid='s']" in app_css),
    # #7 lightbox
    ("7.1 lightbox el", 'id="lightbox"' in index),
    ("7.2 openLightbox", "function openLightbox" in app_js),
    ("7.3 lightbox actions", "open_in_editor" in app_js and "open_output_folder" in app_js),
    ("7.4 bridge open_in_editor edit verb", "def open_in_editor" in bridge and '"edit"' in bridge),
    ("7.5 tile-click opens lightbox", "openLightbox(" in app_js),
    # #9 sidecar
    ("9.1 save.write_sidecar", "def write_sidecar" in save),
    ("9.2 jobs writes sidecar", "write_sidecar" in jobs),
    ("9.3 bridge read_meta + fallback", "def read_meta" in bridge and "history" in bridge),
    ("9.4 lightbox renders meta", "read_meta" in app_js),
]

fails = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
print(f"\n{len(checks)-len(fails)}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
