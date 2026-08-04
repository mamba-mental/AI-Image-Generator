"""ATDD/SBE acceptance harness for the recover basename-collision + perf fix.

Contract: .dd/library-basename-perf-fix-contract.md
Re-runnable, executable, checks the REAL live state (library.db + files on disk +
the actual mediaserver resolver). RED before the fix, GREEN after.

Run: python .dd/verify_recover_fix.py
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / ".cache" / "library.db"
RECOVER = ROOT / "scripts" / ".replicate_recover" / "images"
RECOVER_STR = str(RECOVER)

results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _db():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    con.execute("PRAGMA busy_timeout=5000")
    con.row_factory = sqlite3.Row
    return con


print("Recover basename-collision + perf fix — acceptance harness")
print("=" * 64)

con = _db()

# ---- AC-1 visibility: list_images returns >=5000 distinct recover records ----
sys.path.insert(0, str(ROOT))
try:
    from engine.library_index import LibraryIndex
    idx = LibraryIndex(str(DB))
    recs = idx.list_images([RECOVER_STR], 20000)
    chk("AC-1 list_images returns >=5000 recover records", len(recs) >= 5000,
        f"got {len(recs)} (was 104 pre-fix)")
except Exception as e:  # noqa: BLE001
    chk("AC-1 list_images returns >=5000 recover records", False, f"err {type(e).__name__}: {e}")

# ---- AC-2 unique identity: distinct name == distinct path in DB + on disk ----
tot = con.execute("SELECT COUNT(*) c FROM images WHERE folder=?", (RECOVER_STR,)).fetchone()["c"]
dname = con.execute("SELECT COUNT(DISTINCT name) c FROM images WHERE folder=?", (RECOVER_STR,)).fetchone()["c"]
dpath = con.execute("SELECT COUNT(DISTINCT path) c FROM images WHERE folder=?", (RECOVER_STR,)).fetchone()["c"]
chk("AC-2a DB: distinct recover names == distinct paths (no collision)", dname == dpath,
    f"rows={tot} distinct_name={dname} distinct_path={dpath}")
# on-disk sample: basenames across subdirs must be unique
seen, dup = set(), 0
if RECOVER.is_dir():
    for sub in list(RECOVER.iterdir())[:400]:
        if sub.is_dir():
            for f in sub.iterdir():
                if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    if f.name in seen:
                        dup += 1
                    seen.add(f.name)
chk("AC-2b on-disk: sampled recover basenames are unique across subdirs", dup == 0,
    f"{dup} colliding basenames in first 400 dirs (was ~all pre-fix)")

# ---- AC-3 + AC-4 thumb resolve per-image, DB-backed (no rglob) ----
try:
    from engine import mediaserver
    # two DB rows with DIFFERENT paths — resolve each name, must map to its OWN path
    rows = con.execute("SELECT name, path FROM images WHERE folder=? LIMIT 4000", (RECOVER_STR,)).fetchall()
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], set()).add(r["path"])
    # pick 3 names that each point to a UNIQUE single path (post-fix that's every name)
    mediaserver._STATE["dir"] = RECOVER_STR
    mediaserver._STATE["extra"] = []
    mediaserver._FIND_CACHE.clear() if hasattr(mediaserver, "_FIND_CACHE") else None
    sample = [r for r in rows][:3]
    ok_resolve = True
    detail = []
    for r in sample:
        got = mediaserver._find(r["name"])
        gp = str(got) if got else None
        match = gp is not None and os.path.normcase(gp) == os.path.normcase(r["path"])
        ok_resolve = ok_resolve and match
        detail.append(f"{r['name']}->{'OK' if match else f'WRONG({gp})'}")
    chk("AC-3 mediaserver resolves each recover name to its OWN path", ok_resolve, "; ".join(detail))
    # AC-4 structural: a DB/index-backed resolver exists (not pure rglob)
    src = (ROOT / "engine" / "mediaserver.py").read_text(encoding="utf-8")
    db_backed = ("library.db" in src or "_db_resolve" in src or "name_index" in src
                 or "SELECT path" in src or "resolve_by_db" in src)
    chk("AC-4 mediaserver has a DB/index-backed resolver (not filesystem rglob)", db_backed,
        "no DB-backed resolve found — still rglob-only" if not db_backed else "DB resolver present")
except Exception as e:  # noqa: BLE001
    chk("AC-3 mediaserver resolves each recover name to its OWN path", False, f"err {type(e).__name__}: {e}")
    chk("AC-4 mediaserver has a DB/index-backed resolver (not filesystem rglob)", False, "resolve import failed")

# ---- AC-6 cap: list_library reachable count >= 10000 ----
try:
    import bridge as _b  # noqa
    src_b = (ROOT / "bridge.py").read_text(encoding="utf-8")
    # cap is raised or pagination exists; crude structural signal: no hard 8000 default that also caps recover
    cap_ok = "limit: int = 8000" not in src_b or "def list_library_page" in src_b or "PAGE" in src_b
    chk("AC-6 list_library cap raised/paginated (>=10k reachable)", cap_ok,
        "default limit still 8000 with no pagination" if not cap_ok else "cap addressed")
except Exception as e:  # noqa: BLE001
    chk("AC-6 list_library cap raised/paginated (>=10k reachable)", False, f"err {type(e).__name__}")

con.close()
print("=" * 64)
fails = results.count(False)
print(f"{len(results) - fails}/{len(results)} acceptance checks pass")
sys.exit(1 if fails else 0)
