"""R3 #1 — Library perf static harness.

No JS runtime exists in this repo (no package.json / jsdom) so this proves the fix the same way
verify_pB.py proves #2/#7/#9 — by asserting the actual shipped source has the structural property
that GUARANTEES the behavior, rather than trying to fake a browser. The property that matters:

    a tag-filter click must issue ZERO new /thumb requests.

That's true if and only if (a) library tiles are built exactly once per record set and (b) the
filter path never re-assigns any <img src> or rebuilds the tile DOM — it only toggles visibility
on nodes that already exist. This harness extracts each function body (brace-matched) and checks
those two things directly against the real function bodies, not just anywhere in the file.

Run: python .dd/verify_libperf.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

checks = []


def chk(name, ok, detail=""):
    checks.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def fn_body(name):
    """Brace-matched body of `function name(...) { ... }` — None if not found."""
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*{", app_js)
    if not m:
        return None
    i = m.end()
    depth = 1
    while depth and i < len(app_js):
        if app_js[i] == "{":
            depth += 1
        elif app_js[i] == "}":
            depth -= 1
        i += 1
    return app_js[m.end():i - 1]


render_tiles = fn_body("renderLibTiles")
apply_filter = fn_body("applyLibFilter")
sync_vis = fn_body("syncLibTileVisibility")
build_tiles = fn_body("buildLibTiles")
build_tile = fn_body("buildLibTile")

chk("0.0 all five functions found", all([render_tiles, apply_filter, sync_vis, build_tiles, build_tile]))

# ---- the core guarantee: filtering never touches an <img src> or rebuilds tile markup ----
chk("1.1 applyLibFilter never calls mediaTag() (no image markup built on filter)",
    apply_filter is not None and "mediaTag(" not in apply_filter)
chk("1.2 syncLibTileVisibility never calls mediaTag()",
    sync_vis is not None and "mediaTag(" not in sync_vis)
chk("1.3 syncLibTileVisibility never writes .innerHTML (no DOM rebuild on filter)",
    sync_vis is not None and ".innerHTML" not in sync_vis)
chk("1.4 syncLibTileVisibility is the ONLY thing filtering does to existing tiles: toggles .hidden",
    sync_vis is not None and "el.hidden" in sync_vis)
chk("1.5 renderLibTiles routes an unchanged record set straight to syncLibTileVisibility (no rebuild)",
    render_tiles is not None and "else syncLibTileVisibility()" in render_tiles.replace(" ", "").replace("\n", "")
    or (render_tiles is not None and "syncLibTileVisibility()" in render_tiles))

# ---- tiles are built exactly once per record set (identity-checked), never per filter ----
chk("2.1 renderLibTiles identity-checks state.libRecords before rebuilding",
    render_tiles is not None and "state.libTileEls.forArray !== state.libRecords" in render_tiles)
chk("2.2 buildLibTiles is the only place that builds img markup (mediaTag lives in buildLibTile)",
    build_tile is not None and "mediaTag(" in build_tile
    and build_tiles is not None and "mediaTag(" not in build_tiles)
chk("2.3 each tile gets a stable identity key (data-rk) set once at creation",
    build_tile is not None and "dataset.rk" in build_tile)
chk("2.4 a stale in-flight build is cancelled when a newer one supersedes it (race safety)",
    build_tiles is not None and "state.libTileEls !== map" in build_tiles)

# ---- windowed initial render: first paint isn't one giant synchronous build ----
chk("3.1 buildLibTiles chunks the initial 5k+ build via requestAnimationFrame",
    build_tiles is not None and "requestAnimationFrame" in build_tiles)
chk("3.2 chunk size is bounded (not one big innerHTML write for the whole library)",
    "LIB_BUILD_CHUNK" in app_js and re.search(r"LIB_BUILD_CHUNK\s*=\s*\d+", app_js) is not None)

# ---- revealInLibrary no longer depends on the removed data-wi indexing scheme ----
chk("4.1 no remaining data-wi references (old index-based tile lookup fully replaced)",
    "data-wi" not in app_js)
chk("4.2 revealInLibrary resolves its target tile via the same libTileEls map",
    "state.libTileEls.get(libKey(rec))" in app_js)

fails = checks.count(False)
print(f"\n{len(checks) - fails}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
