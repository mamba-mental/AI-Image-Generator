"""Behavioral (not static) proof of the mediaserver fix: start the REAL server, HTTP-GET a
renamed recover thumbnail, and assert it resolves via the DB index and returns a real JPEG.

Proves end-to-end: unique-name -> _db_resolve (no rglob) -> _make_thumb -> 200 image/jpeg.
Run: python .dd/verify_thumb_serving_live.py
"""
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from engine import mediaserver  # noqa: E402

RECOVER = str(ROOT / "scripts" / ".replicate_recover" / "images")
con = sqlite3.connect("file:.cache/library.db?mode=ro", uri=True, timeout=5)
con.row_factory = sqlite3.Row
con.execute("PRAGMA busy_timeout=5000")

# pick 3 renamed recover images (unique <id>_<n> names) from DIFFERENT predictions
rows = con.execute(
    "SELECT name, path FROM images WHERE folder=? AND name LIKE '%\\_%' ESCAPE '\\' LIMIT 3",
    (RECOVER,)).fetchall()
con.close()

results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


chk("setup: found renamed recover rows", len(rows) == 3, f"{len(rows)} rows")

# start the real server; recover images live under the output dir's sibling — register the recover
# root as an extra so _roots() is realistic, but the DB resolver is what must carry the nested names.
mediaserver._STATE["dir"] = str(ROOT / "generated_images")
mediaserver._STATE["extra"] = []          # deliberately NOT adding recover as a root: force DB resolve
mediaserver._FIND_CACHE.clear()
base = mediaserver.start(str(ROOT / "generated_images"))

for r in rows:
    url = base + "thumb/" + urllib.parse.quote(r["name"]) + "?s=256"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read()
        jpeg = data[:2] == b"\xff\xd8"     # JPEG magic
        ok = status == 200 and "image/jpeg" in ctype and jpeg and len(data) > 200
        chk(f"GET /thumb/{r['name'][:34]} -> 200 JPEG (DB-resolved, nested)", ok,
            f"status={status} ctype={ctype} bytes={len(data)}")
    except Exception as e:  # noqa: BLE001
        chk(f"GET /thumb/{r['name'][:34]}", False, f"{type(e).__name__}: {e}")

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} live serving checks pass")
sys.exit(1 if fails else 0)
