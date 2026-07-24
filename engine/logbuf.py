"""In-memory ring buffer of engine events + errors (#14 — Portainer-style logs).

Thread-safe and bounded (never grows unbounded). Also TEES every event to a size-capped rotating file
so the Logs panel survives a restart — the deque is wiped on each launch, the file is not. The bridge
reads/searches both for the Logs panel."""
import json
import os
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()
_BUF = deque(maxlen=500)

_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "app.log"
_ROLL = _LOG_FILE.parent / (_LOG_FILE.name + ".1")   # single rollover target
_MAX_BYTES = 1_000_000   # ~1 MB, then roll over once


def _write_line(entry: dict) -> None:
    """Append one JSON line to the persisted log, rolling over once past ~1 MB. Best-effort: a file
    I/O failure never breaks the app (the deque still holds the entry for the live view)."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > _MAX_BYTES:
            try:
                os.replace(_LOG_FILE, _ROLL)   # atomic single rollover, overwrites a prior .1
            except OSError:
                _LOG_FILE.unlink(missing_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def append(level: str, etype: str, message: str, detail: str = "") -> None:
    entry = {"ts": datetime.now().isoformat(timespec="seconds"),
             "level": level, "type": etype, "message": str(message), "detail": str(detail)}
    with _LOCK:
        _BUF.append(entry)
        _write_line(entry)


def _entry_key(e: dict):
    return (e.get("ts"), e.get("level"), e.get("type"), e.get("message"), e.get("detail"))


def _read_file(max_lines: int = 4000) -> list:
    """Parse the persisted log (rollover first, then current) into entries, oldest→newest, capped."""
    entries = []
    for p in (_ROLL, _LOG_FILE):
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except OSError:
            pass
    return entries[-max_lines:]


def read(query: str = "", level: str = "", limit: int = 300) -> list:
    """Newest-first, optionally filtered by a free-text query (message/detail/type) and level.
    Merges the persisted file (survives restart) with the live deque, de-duped so a teed entry that
    is in BOTH isn't shown twice — only deque entries whose file-tee failed get folded back in."""
    q = (query or "").lower()
    lv = (level or "").lower()
    file_recs = _read_file()
    seen = {_entry_key(e) for e in file_recs}
    with _LOCK:
        mem = [e for e in _BUF if _entry_key(e) not in seen]
    combined = file_recs + mem   # file (older) then any unflushed live tail
    out = []
    for r in reversed(combined):   # newest first
        if lv and r.get("level") != lv:
            continue
        if q and q not in (str(r.get("message", "")) + " " + str(r.get("detail", "")) + " " + str(r.get("type", ""))).lower():
            continue
        out.append(r)
        if len(out) >= int(limit):
            break
    return out


def clear() -> None:
    """Clear both the live view and the persisted log (an explicit 'clear logs' means gone, not just
    hidden until the file re-merges)."""
    with _LOCK:
        _BUF.clear()
        for p in (_LOG_FILE, _ROLL):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
