"""AC-7 — no regression to non-recover library folders.

Every ENABLED folder that isn't the recover archive must still (a) return its rows via list_images
and (b) resolve a sample basename through mediaserver to the correct path (the DB resolver is
additive — top-level folders hit the fast path first). Offline-drive folders (0 rows) are skipped.

Run: python .dd/verify_ac7_no_regression.py
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from engine.library_index import LibraryIndex   # noqa: E402
from engine import mediaserver                   # noqa: E402

con = sqlite3.connect("file:.cache/library.db?mode=ro", uri=True, timeout=5)
con.row_factory = sqlite3.Row
con.execute("PRAGMA busy_timeout=5000")
idx = LibraryIndex(".cache/library.db")

folders = [r["path"] for r in con.execute("SELECT path FROM folders WHERE enabled=1").fetchall()]
ok_all, checked = True, 0
for f in folders:
    if "replicate_recover" in f.lower():
        continue
    n = con.execute("SELECT COUNT(*) c FROM images WHERE folder=?", (f,)).fetchone()["c"]
    if n == 0:
        print(f"  (skip {Path(f).name}: 0 rows / offline drive)")
        continue
    recs = idx.list_images([f], 50000)
    row = con.execute("SELECT name,path FROM images WHERE folder=? LIMIT 1", (f,)).fetchone()
    mediaserver._STATE["dir"] = f
    mediaserver._STATE["extra"] = []
    mediaserver._FIND_CACHE.clear()
    got = mediaserver._find(row["name"])
    ok = got is not None and os.path.normcase(str(got)) == os.path.normcase(row["path"])
    ok_all = ok_all and ok and len(recs) > 0
    checked += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {Path(f).name}: rows={n} list_images={len(recs)} "
          f"resolve={'OK' if ok else 'WRONG:' + str(got)}")
con.close()
print(f"\nAC-7 {'PASS' if (ok_all and checked) else 'FAIL'} — {checked} non-recover folders checked")
sys.exit(0 if (ok_all and checked) else 1)
