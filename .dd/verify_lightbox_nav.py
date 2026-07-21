"""R3 #2 — lightbox arrow-key nav static harness (same style as verify_pB.py).
Runtime proof was done live via a scratch probe (real keydown events against the real 5420-image
library: ArrowRight/ArrowLeft walked state.lbFile through state.libFiltered in order, clamped at
index 0, ignored keys while typing in the tag input, Escape still closed) — this just locks the
source-level contract in place. Run: python .dd/verify_lightbox_nav.py"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

checks = [
    ("2.1 openLightbox accepts an optional nav list", "async function openLightbox(file, dir, list)" in app_js),
    ("2.2 nav list + index tracked on state", "state.lbList = list" in app_js and "state.lbIndex" in app_js),
    ("2.3 navLightbox exists and clamps (no wraparound)", "function navLightbox(dir)" in app_js and "next < 0 || next >= state.lbList.length" in app_js),
    ("2.4 keydown handler wires ArrowLeft/ArrowRight to navLightbox", '"ArrowLeft"' in app_js and '"ArrowRight"' in app_js and "navLightbox(" in app_js),
    ("2.5 arrow nav ignored while focus is in an input/textarea (tag box)", "INPUT|TEXTAREA" in app_js),
    ("2.6 Escape still closes the lightbox", "closeLightbox()" in app_js and '"Escape"' in app_js),
    ("2.7 gallery tiles pass state.gallery as the nav list", "state.gallery[+t.dataset.i].file, null, state.gallery" in app_js),
    ("2.8 library tiles pass state.libFiltered as the nav list", "openLightbox(r.file, r.dir, state.libFiltered)" in app_js),
]

fails = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
print(f"\n{len(checks)-len(fails)}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
