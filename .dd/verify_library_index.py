"""Executable acceptance harness for Spec A — SQLite Library Index.

Runs on a synthetic tree + a seeded 5k DB (no NAS needed). Exit 0 all-green / 1 any-fail.
Instrumentation: we count filesystem crawls (Path.rglob) and sidecar reads (Path.read_text on
*.json) and expensive folder indexes, then assert the ACs against those counters.
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pathlib
from engine import library_index as LI

RESULTS = []


def check(ac, cond, detail=""):
    RESULTS.append((ac, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {ac}  {detail}")


# ---- filesystem instrumentation --------------------------------------------------
_counts = {"rglob": 0, "sidecar": 0}
_orig_rglob = pathlib.Path.rglob
_orig_read_text = pathlib.Path.read_text


def _rglob(self, *a, **k):
    _counts["rglob"] += 1
    return _orig_rglob(self, *a, **k)


def _read_text(self, *a, **k):
    if str(self).endswith(".json"):
        _counts["sidecar"] += 1
    return _orig_read_text(self, *a, **k)


pathlib.Path.rglob = _rglob
pathlib.Path.read_text = _read_text


def reset():
    _counts["rglob"] = 0
    _counts["sidecar"] = 0


def make_image(folder: Path, name: str, prompt: str, service="fal"):
    p = folder / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)  # fake but non-empty
    (folder / (name + ".json")).write_text(
        '{"service":"%s","model":"m1","prompt":"%s","category":"art"}' % (service, prompt),
        encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="libidx_"))
    A, B = tmp / "A", tmp / "B"
    A.mkdir(); B.mkdir()
    for i in range(3):
        make_image(A, f"a{i}.png", f"prompt alpha {i}")
    for i in range(2):
        make_image(B, f"b{i}.png", f"prompt beta {i}")

    idx = LI.LibraryIndex(str(tmp / "library.db"))

    # instrument the expensive per-folder index path
    indexed = []
    _orig_index = idx.index_folder
    idx.index_folder = lambda b: (indexed.append(b), _orig_index(b))[1]

    # first-run index (expensive, expected to crawl)
    reset()
    idx.ensure_indexed([str(A), str(B)])
    check("SETUP first-index crawls", _counts["rglob"] >= 2 and _counts["sidecar"] == 5,
          f"rglob={_counts['rglob']} sidecar={_counts['sidecar']}")

    # AC-4: warm list performs ZERO sidecar opens
    reset()
    rows = idx.list_images([str(A), str(B)])
    check("AC-4 warm list zero sidecar reads", _counts["sidecar"] == 0, f"sidecar={_counts['sidecar']}")
    check("AC-4b warm list is pure DB (no crawl)", _counts["rglob"] == 0, f"rglob={_counts['rglob']}")
    check("SETUP list returns all rows", len(rows) == 5 and rows[0]["prompt"].startswith("prompt"),
          f"n={len(rows)}")

    # AC-1: toggle a folder off/on → ZERO filesystem reads, rows never dropped
    reset(); indexed.clear()
    idx.set_folder_enabled(str(A), False)
    only_b = idx.list_images([str(B)])
    idx.set_folder_enabled(str(A), True)
    both = idx.list_images([str(A), str(B)])
    check("AC-1 toggle zero fs reads", _counts["rglob"] == 0 and _counts["sidecar"] == 0,
          f"rglob={_counts['rglob']} sidecar={_counts['sidecar']}")
    check("AC-1b toggle triggers no re-index", indexed == [], f"reindexed={indexed}")
    check("AC-1c rows survive toggle", len(only_b) == 2 and len(both) == 5, f"B={len(only_b)} both={len(both)}")

    # AC-3: change one file in B → refresh re-reads ONLY B
    make_image(B, "b2_new.png", "prompt beta new")           # add
    (B / "b0.png").rename(B / "b0_renamed.png")               # rename
    (B / "a_none").write_text("x")                            # noise (non-image)
    indexed.clear()
    res = idx.refresh([str(A), str(B)])
    check("AC-3 refresh re-indexes only changed folder", indexed == [str(B)] and res["reindexed"] == [str(B)],
          f"reindexed={indexed}")
    after = {r["file"] for r in idx.list_images([str(A), str(B)])}
    check("AC-3b add+rename reflected", "b2_new.png" in after and "b0_renamed.png" in after and "b0.png" not in after,
          f"has_new={'b2_new.png' in after} renamed={'b0_renamed.png' in after}")

    # AC-3c: an unchanged folder is NOT re-indexed on refresh
    indexed.clear()
    idx.refresh([str(A), str(B)])
    check("AC-3c unchanged folders skipped", indexed == [], f"reindexed={indexed}")

    # AC-5: search works (FTS5 if present, else LIKE)
    hits = idx.search("beta", [str(A), str(B)])
    check("AC-5 search finds prompt terms", len(hits) >= 2 and all("beta" in (h.get("prompt") or "") for h in hits),
          f"fts={idx.fts} hits={len(hits)}")

    # AC-2: warm reload < 250ms at 5000 rows, ZERO filesystem access
    db = idx._db
    db.executemany(
        "INSERT OR REPLACE INTO images(path,folder,name,type,service,model,prompt) VALUES(?,?,?,?,?,?,?)",
        [(f"/seed/s{i}.png", "/seed", f"s{i}.png", "image", "fal", "m", f"seeded prompt {i}") for i in range(5000)])
    db.commit()
    reset()
    t0 = time.perf_counter()
    big = idx.list_images(["/seed"], limit=8000)
    dt = (time.perf_counter() - t0) * 1000
    check("AC-2 warm 5k list < 250ms", dt < 250 and len(big) == 5000, f"{dt:.1f}ms n={len(big)}")
    check("AC-2b warm 5k zero fs access", _counts["rglob"] == 0 and _counts["sidecar"] == 0,
          f"rglob={_counts['rglob']} sidecar={_counts['sidecar']}")

    # AC-6: migration from legacy JSON + corrupt-DB rebuild
    legacy = tmp / "library_index.json"
    legacy.write_text('{"files":[{"file":"leg.png","dir":"%s","type":"image","service":"fal","prompt":"legacy"}]}'
                      % str(A).replace("\\", "\\\\"), encoding="utf-8")
    idx2 = LI.LibraryIndex(str(tmp / "fresh.db"))
    n = idx2.migrate_from_json(str(legacy))
    migrated = {r["file"] for r in idx2.list_images([str(A)])}
    check("AC-6 legacy JSON migrates", n == 1 and "leg.png" in migrated, f"imported={n}")
    idx2.close()

    corrupt = tmp / "corrupt.db"
    corrupt.write_bytes(b"this is not a sqlite database at all" * 4)
    try:
        idx3 = LI.LibraryIndex(str(corrupt))          # must rebuild, not raise
        idx3.index_folder(str(A))
        ok = len(idx3.list_images([str(A)])) == 3
        idx3.close()
    except Exception as e:
        ok = False; print("   corrupt-open raised:", e)
    check("AC-6b corrupt DB rebuilds (no crash)", ok, "")

    idx.close()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{'='*50}\n{len(RESULTS)-len(failed)}/{len(RESULTS)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
