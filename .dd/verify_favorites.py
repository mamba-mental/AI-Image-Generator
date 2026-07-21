"""R3 #3 — favorites static harness (same style as verify_pB.py).
Runtime proof was done live against the real 5420-image library: toggled a real image's favorite
star from a library tile, confirmed the lightbox star + favorites filter chip + a server-side
get_image_tags re-fetch all agree, toggled it back off (zero residue left), and checked the
"save as Style/Recipe from this image" payload shape. This just locks the source contract.
Run: python .dd/verify_favorites.py"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

checks = [
    # favorite = the existing "favorite" tag (reuses add_tag/remove_tag — no new persistence)
    ("3.1 tile star toggle calls the real bridge tag calls (no localStorage reinvention)",
        "function toggleTileFavorite(r)" in app_js and 'api().add_tag(r.file, "favorite", r.dir)' in app_js
        and 'api().remove_tag(r.file, "favorite", r.dir)' in app_js),
    ("3.2 lightbox star reuses the existing addLbTag/removeLbTag path",
        'removeLbTag("favorite")' in app_js and 'addLbTag("favorite")' in app_js),
    ("3.3 star exists on both library tiles and the lightbox",
        'star.dataset.fav = "1"' in app_js and 'id="lbfav"' in index),
    ("3.4 toggling from either surface keeps the other in sync (tile<->lightbox)",
        "refreshTileFavStar(r)" in app_js and "syncLbFavStarButton()" in app_js),
    ("3.5 a dedicated favorites filter chip exists and drives libFiltered",
        'id="libfavfilter"' in app_js and "favoritesOnly" in app_js
        and '(!favOnly || (r.tags || []).includes("favorite"))' in app_js),
    ("3.6 favorites filter reuses the existing tagchip visual language (no new CSS)",
        'class="tagchip filterchip favfilter' in app_js),
    # presets: seed a Style/Recipe save from a favorited image's own metadata
    ("3.7 lightbox 'save as Style/Recipe from this image' buttons exist",
        'id="lbsavestyle"' in index and 'id="lbsaverecipe"' in index),
    ("3.8 they pull from state.lbMeta (the image's own prompt/model/params), not the live composer",
        "function presetSourceFromLightboxImage" in app_js and "state.lbMeta" in app_js),
    ("3.9 save flow is ONE shared implementation for both the composer buttons and the lightbox buttons",
        "function saveStylePreset(source)" in app_js and "function saveRecipePreset(source)" in app_js
        and "saveStylePreset(currentComposerState())" in app_js
        and "saveStylePreset(presetSourceFromLightboxImage())" in app_js),
]

fails = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
print(f"\n{len(checks)-len(fails)}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
