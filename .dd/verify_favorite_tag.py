"""AC — favorites/tags resolve for NESTED archive images (recover folder).

Bug: _resolve_full checked `dir/<name>` (top-level) then `output_dir/<name>` — both miss a nested
recover image (.replicate_recover/images/<id>/<name>), so add_tag/get_image_tags hit "file not
found" and favorites silently failed (tile star toggled optimistically; nothing persisted; lightbox
showed nothing). Fix: _resolve_full now DB-resolves the basename to its real nested path.

Proves: _db_path_for_name + _resolve_full return the real nested path for a recover image, and a
FLAT folder still resolves via the fast dir/<name> path (no regression). No DB mutation.
Run: python .dd/verify_favorite_tag.py
"""
import os
import sqlite3
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from bridge import Api  # noqa: E402

DB = ROOT / ".cache" / "library.db"
RECOVER = str(ROOT / "scripts" / ".replicate_recover" / "images")
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
con.row_factory = sqlite3.Row
con.execute("PRAGMA busy_timeout=5000")
rec = con.execute("SELECT name, path, folder FROM images WHERE folder=? LIMIT 1", (RECOVER,)).fetchone()
flat = con.execute("SELECT name, path, folder FROM images WHERE folder LIKE '%generated_images' LIMIT 1").fetchone()
con.close()

fake = types.SimpleNamespace(config={"output_directory": str(ROOT / "generated_images")})
# bind the methods _resolve_full calls internally so the unbound-method test can run
fake._db_path_for_name = types.MethodType(Api._db_path_for_name, fake)
fake._resolve = types.MethodType(Api._resolve, fake)
fake._resolve_full = types.MethodType(Api._resolve_full, fake)

# recover (nested): _db_path_for_name + _resolve_full must return the REAL nested path
chk("setup: found a recover image", rec is not None)
if rec:
    dbp = Api._db_path_for_name(fake, rec["name"])
    chk("_db_path_for_name resolves nested recover basename", os.path.normcase(dbp) == os.path.normcase(rec["path"]), dbp)
    rf = Api._resolve_full(fake, rec["name"], rec["folder"])
    chk("_resolve_full returns the real nested path (was output_dir/<name>, nonexistent)",
        os.path.normcase(rf) == os.path.normcase(rec["path"]), rf)
    chk("resolved path actually exists (add_tag/get_image_tags will find it)", os.path.exists(rf))

# flat folder: fast dir/<name> path still wins (no regression)
if flat:
    rf2 = Api._resolve_full(fake, flat["name"], flat["folder"])
    chk("AC no-regression: flat-folder image still resolves", os.path.exists(rf2) and os.path.normcase(rf2) == os.path.normcase(flat["path"]))

# source guard: tag ops go through _resolve_full
src = (ROOT / "bridge.py").read_text(encoding="utf-8")
for fn in ("get_image_tags", "add_tag", "remove_tag"):
    body = src[src.find(f"def {fn}("):src.find(f"def {fn}(") + 400]
    chk(f"{fn} resolves via _resolve_full", "_resolve_full" in body)

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
