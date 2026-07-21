"""Single-scenario runner for the Spec A real-NAS benchmark (bench_nas.py's subprocess target).

Invoked as a FRESH process per scenario (`python _scenario.py <mode>`), mode in
{before, cold, warm}. Instruments pathlib.Path.rglob / .stat / .read_text and os.stat the
same way `.dd/verify_library_index.py` does, plus a NAS-prefix filter (derived from the
configured `library_directories` drive letters) so we can assert "zero NAS-prefix access"
on a warm read. Prints exactly one line, `RESULT_JSON:<json>`, as the last line of stdout —
the orchestrator parses that line and ignores anything else on stdout/stderr.

Read-only against NAS content: every mode only ever reads files under the configured library
dirs (rglob/stat/read_text) and writes to the LOCAL `.cache/library.db` — never touches/deletes
anything on the NAS share itself.
"""
import json
import os
import pathlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ---- config / bases ---------------------------------------------------------------
import bridge  # noqa: E402
from engine import config as engine_config  # noqa: E402
from engine.library_index import LibraryIndex  # noqa: E402

_cfg = engine_config.load()
_dirs = _cfg.get("library_directories")
if not isinstance(_dirs, list):
    single = _cfg.get("library_directory") or ""
    _dirs = [single] if single else []
BASES = [d for d in _dirs if d and os.path.isdir(d)]

DB_PATH = str(REPO_ROOT / ".cache" / "library.db")

NAS_PREFIXES = tuple(sorted({os.path.splitdrive(b)[0].lower() for b in BASES if os.path.splitdrive(b)[0]}))


def _is_nas(path_like) -> bool:
    s = str(path_like).lower()
    return any(s.startswith(pref) for pref in NAS_PREFIXES)


# ---- filesystem instrumentation (mirrors .dd/verify_library_index.py) -------------
_counts = {"rglob": 0, "nas_rglob": 0, "stat": 0, "nas_stat": 0,
           "sidecar_open": 0, "nas_sidecar_open": 0}

_orig_rglob = pathlib.Path.rglob
_orig_read_text = pathlib.Path.read_text
_orig_path_stat = pathlib.Path.stat
_orig_os_stat = os.stat


def _rglob(self, *a, **k):
    _counts["rglob"] += 1
    if _is_nas(self):
        _counts["nas_rglob"] += 1
    return _orig_rglob(self, *a, **k)


def _read_text(self, *a, **k):
    if str(self).lower().endswith(".json"):
        _counts["sidecar_open"] += 1
        if _is_nas(self):
            _counts["nas_sidecar_open"] += 1
    return _orig_read_text(self, *a, **k)


def _path_stat(self, *a, **k):
    _counts["stat"] += 1
    if _is_nas(self):
        _counts["nas_stat"] += 1
    return _orig_path_stat(self, *a, **k)


def _os_stat(path, *a, **k):
    _counts["stat"] += 1
    if _is_nas(path):
        _counts["nas_stat"] += 1
    return _orig_os_stat(path, *a, **k)


pathlib.Path.rglob = _rglob
pathlib.Path.read_text = _read_text
pathlib.Path.stat = _path_stat
os.stat = _os_stat


def _reset():
    for k in _counts:
        _counts[k] = 0


def _nas_access_total() -> int:
    return _counts["nas_rglob"] + _counts["nas_stat"] + _counts["nas_sidecar_open"]


# ---- scenarios ----------------------------------------------------------------------
def run_before() -> dict:
    """AC-0 'before': the OLD JSON-crawl path (`Api._scan_library`), unbound — no Api.__init__
    side effects (mediaserver, keypool, etc.), just the pure crawl logic + its class constants.
    Empirically proves folder_toggle_recrawl=True: a second call with one fewer folder ALSO
    does a full rglob+sidecar crawl over the remaining folders (the old design has no cache at
    all, so ANY change to the enabled-folder set re-crawls everything included in it)."""
    fake_self = SimpleNamespace(_LIB_EXTS=bridge.Api._LIB_EXTS, _VID_EXTS=bridge.Api._VID_EXTS)

    _reset()
    t0 = time.perf_counter()
    records_full = bridge.Api._scan_library(fake_self, BASES)
    wall_ms = (time.perf_counter() - t0) * 1000
    sidecar_open_count = _counts["sidecar_open"]
    smb_stat_count = _counts["nas_stat"]
    rglob_count = _counts["rglob"]

    # simulate a folder toggle (one folder disabled) and confirm the old design re-crawls
    # the remaining folders from scratch (no per-folder cache to reuse)
    toggle_bases = BASES[:-1] if len(BASES) > 1 else BASES
    _reset()
    records_toggle = bridge.Api._scan_library(fake_self, toggle_bases)
    folder_toggle_recrawl = bool(_counts["rglob"] > 0 and _counts["sidecar_open"] > 0)

    return {
        "mode": "before",
        "bases": BASES,
        "n_records": len(records_full),
        "n_records_after_toggle": len(records_toggle),
        "sidecar_open_count": sidecar_open_count,
        "smb_stat_count": smb_stat_count,
        "rglob_count": rglob_count,
        "wall_ms": round(wall_ms, 1),
        "folder_toggle_recrawl": folder_toggle_recrawl,
    }


def run_cold() -> dict:
    """AC-0 'after' cold: fresh process, NO existing library.db (orchestrator deletes it first)
    → full index build via ensure_indexed(). This is the one-time slow path. `library.db` is
    empty at this point so `connect_ms` (which includes PRAGMA integrity_check) is expected to
    be cheap — reported separately from `index_build_ms` for transparency."""
    _reset()
    t0 = time.perf_counter()
    idx = LibraryIndex(DB_PATH)
    connect_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    idx.ensure_indexed(BASES)
    index_build_ms = (time.perf_counter() - t1) * 1000
    wall_ms = (time.perf_counter() - t0) * 1000
    n_rows = idx._db.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    idx.close()
    return {
        "mode": "cold",
        "bases": BASES,
        "n_rows_indexed": n_rows,
        "sidecar_open_count": _counts["sidecar_open"],
        "smb_stat_count": _counts["nas_stat"],
        "rglob_count": _counts["rglob"],
        "connect_ms": round(connect_ms, 1),
        "index_build_ms": round(index_build_ms, 1),
        "wall_ms": round(wall_ms, 1),
    }


def run_warm() -> dict:
    """AC-2/AC-0 'after' warm: fresh process, EXISTING (already-populated) library.db → the
    exact call sequence `bridge.Api.list_library()` runs on a plain (non-refresh) tab-open:
    LibraryIndex() construction (connect + PRAGMA integrity_check + schema) + ensure_indexed()
    (a per-folder DB flag check, no crawl for already-indexed folders) + list_images(). Asserts
    zero NAS-prefix filesystem access. Reports connect/ensure_indexed/list_images as separate
    phases (not just the lump wall_ms) because the fresh-process constructor cost — dominated
    by SQLite's PRAGMA integrity_check over the full (now-populated, ~25MB) db file — is a
    LOCAL, non-NAS cost distinct from the AC-2 'query + row hydration' scope."""
    _reset()
    t0 = time.perf_counter()
    idx = LibraryIndex(DB_PATH)
    connect_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    idx.ensure_indexed(BASES)
    ensure_indexed_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    rows = idx.list_images(BASES, 8000)
    list_images_ms = (time.perf_counter() - t2) * 1000
    wall_ms = (time.perf_counter() - t0) * 1000
    idx.close()
    return {
        "mode": "warm",
        "bases": BASES,
        "n_rows": len(rows),
        "sidecar_open_count": _counts["sidecar_open"],
        "smb_stat_count": _counts["nas_stat"],
        "rglob_count": _counts["rglob"],
        "nas_rglob_count": _counts["nas_rglob"],
        "nas_stat_count": _counts["nas_stat"],
        "nas_sidecar_open_count": _counts["nas_sidecar_open"],
        "nas_access_total": _nas_access_total(),
        "connect_ms": round(connect_ms, 1),
        "ensure_indexed_ms": round(ensure_indexed_ms, 1),
        "list_images_ms": round(list_images_ms, 1),
        "wall_ms": round(wall_ms, 1),
    }


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("before", "cold", "warm"):
        print(f"RESULT_JSON:{json.dumps({'error': f'unknown mode {mode!r}'})}")
        return 1
    if not BASES:
        print(f"RESULT_JSON:{json.dumps({'error': 'no reachable library_directories', 'configured': _dirs})}")
        return 1
    try:
        result = {"before": run_before, "cold": run_cold, "warm": run_warm}[mode]()
    except Exception as e:  # honest failure, never fabricate numbers
        print(f"RESULT_JSON:{json.dumps({'error': f'{type(e).__name__}: {e}', 'mode': mode})}")
        return 1
    print(f"RESULT_JSON:{json.dumps(result)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
