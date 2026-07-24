"""Tests for the Omni-Image root-cause fixes (2026-07-23):
  - mediaserver `_find` recursion + cache (nested-generation 404 fix)
  - history merge/dedup + defensive parent pull-forward (stranded history recovery)
  - logbuf persistence across restart + dedup

Run: python test_fixes.py   → per-test PASS/FAIL, exits non-zero on any failure.
Self-contained (temp dirs) — touches no live config, NAS, or the running app."""
import json
import tempfile
from pathlib import Path

from engine import mediaserver, history, logbuf


def test_mediaserver_find_recursion():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nested = root / "generated" / "2026-07"
        nested.mkdir(parents=True)
        f = nested / "img_abc.png"
        f.write_bytes(b"x")
        mediaserver._STATE["dir"] = str(root)
        mediaserver._STATE["extra"] = []
        mediaserver._FIND_CACHE.clear()
        # top-level miss, recursive hit
        hit = mediaserver._find("img_abc.png")
        assert hit is not None and hit.resolve() == f.resolve(), f"nested file not found: {hit}"
        # the hit is cached and the cached lookup returns the same path
        assert mediaserver._FIND_CACHE.get("img_abc.png"), "hit not cached"
        assert mediaserver._find("img_abc.png").resolve() == f.resolve()
        # a genuinely-absent name → None
        assert mediaserver._find("nope.png") is None
        # a top-level file still resolves via the fast path
        top = root / "top.jpg"
        top.write_bytes(b"y")
        mediaserver._FIND_CACHE.clear()
        assert mediaserver._find("top.jpg").resolve() == top.resolve()
    # reset shared module state so the test can't leak into anything else
    mediaserver._STATE["dir"] = None
    mediaserver._STATE["extra"] = []
    mediaserver._FIND_CACHE.clear()
    print("PASS mediaserver _find recursion + cache")


def test_history_merge_dedup():
    a = [{"ts": "2026-07-01T00:00:00", "files": ["a.png"]},
         {"ts": "2026-07-02T00:00:00", "files": ["b.png"]}]
    b = [{"ts": "2026-07-02T00:00:00", "files": ["b.png"]},    # exact dup of a[1]
         {"ts": "2026-07-03T00:00:00", "files": ["c.png"]}]
    merged = history.merge_records(a, b)
    assert len(merged) == 3, f"expected 3 after dedup, got {len(merged)}"
    ts = [r["ts"] for r in merged]
    assert ts == sorted(ts), f"not chronological: {ts}"
    # same ts, different first file → distinct records, NOT deduped
    c = [{"ts": "2026-07-04T00:00:00", "files": ["d.png"]}]
    d = [{"ts": "2026-07-04T00:00:00", "files": ["e.png"]}]
    assert len(history.merge_records(c, d)) == 2, "same-ts different-file was wrongly deduped"
    print("PASS history merge/dedup")


def test_history_pull_forward():
    with tempfile.TemporaryDirectory() as td:
        parent = Path(td)
        out = parent / "generated"
        out.mkdir()
        (parent / "history.jsonl").write_text(   # stranded one level up (the real I:\ case)
            json.dumps({"ts": "2026-07-01T00:00:00", "files": ["old.png"]}) + "\n", encoding="utf-8")
        (out / "history.jsonl").write_text(
            json.dumps({"ts": "2026-07-05T00:00:00", "files": ["new.png"]}) + "\n", encoding="utf-8")
        recs = history.read(str(out))
        files = {r["files"][0] for r in recs}
        assert files == {"old.png", "new.png"}, f"pull-forward missed a record: {files}"
        recs2 = history.read(str(out))   # idempotent — no duplication on a second read
        assert len(recs2) == 2, f"pull-forward not idempotent: {len(recs2)}"
    print("PASS history parent pull-forward (defensive)")


def test_logbuf_persist():
    with tempfile.TemporaryDirectory() as td:
        logbuf._LOG_FILE = Path(td) / "app.log"
        logbuf._ROLL = Path(td) / "app.log.1"
        logbuf.clear()
        logbuf.append("info", "gen", "hello world")
        logbuf.append("error", "save", "boom", "stack")
        assert logbuf._LOG_FILE.exists(), "log file not written"
        logbuf._BUF.clear()                # simulate a restart: deque wiped, file kept
        msgs = [r["message"] for r in logbuf.read()]
        assert "hello world" in msgs and "boom" in msgs, f"logs didn't survive restart: {msgs}"
        # an entry present in BOTH file and deque appears exactly once
        logbuf._BUF.clear()
        logbuf.append("info", "x", "once")
        once = [r for r in logbuf.read(query="once") if r["message"] == "once"]
        assert len(once) == 1, f"duplicate across file+deque: {len(once)}"
        assert all(r["level"] == "error" for r in logbuf.read(level="error")), "level filter leaked"
    print("PASS logbuf persist + dedup + filters")


if __name__ == "__main__":
    import sys
    fails = 0
    for t in (test_mediaserver_find_recursion, test_history_merge_dedup,
              test_history_pull_forward, test_logbuf_persist):
        try:
            t()
        except AssertionError as e:
            fails += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            fails += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)
