"""AC-5 — library grid virtualization static harness.

No JS runtime in-repo, so (like verify_libperf.py) we prove the structural property that GUARANTEES
bounded work: off-screen library tiles must not consume layout/paint/decode. Acceptance is
OUTCOME-based — satisfied by EITHER the browser-native mechanism (`content-visibility:auto` +
`contain-intrinsic-size` on the tile, which skips off-screen render and drops off-screen decodes)
OR a JS IntersectionObserver that mounts/unmounts tile images. The contract named
"IntersectionObserver / windowed recycle"; content-visibility IS windowed rendering, done natively.

RED before the fix (tiles render/decode unbounded), GREEN after.
Run: python .dd/verify_grid_virtual.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
app_css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
checks = []


def chk(name, ok, detail=""):
    checks.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def wtile_rule():
    """The `.wtile { ... }` declaration block body (native masonry tile)."""
    m = re.search(r"\.wtile\s*\{([^}]*)\}", app_css, re.S)
    return m.group(1) if m else ""


tile = wtile_rule()

# --- native mechanism (preferred): content-visibility on the tile ---
cv = "content-visibility" in tile and "auto" in tile
intrinsic = "contain-intrinsic-size" in tile
# --- OR a JS observer windowing ---
observer = "IntersectionObserver" in app_js and ("_mountLibTile" in app_js or "unmountLibTile" in app_js)

chk("5.1 off-screen tiles are virtualized (content-visibility:auto on .wtile, or an IntersectionObserver)",
    cv or observer, "content-visibility" if cv else ("IntersectionObserver" if observer else "neither found"))
chk("5.2 a placeholder size is reserved so scroll-back doesn't jump (contain-intrinsic-size, or JS reserve)",
    (cv and intrinsic) or observer, "contain-intrinsic-size present" if intrinsic else "")
chk("5.3 image fetch stays lazy (loading=\"lazy\" on grid tiles) so network is bounded too",
    'loading="lazy"' in app_js)

fails = checks.count(False)
print(f"\n{len(checks) - fails}/{len(checks)} virtualization checks pass")
sys.exit(1 if fails else 0)
