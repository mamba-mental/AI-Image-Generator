"""In-memory ring buffer of engine events + errors (#14 — Portainer-style logs).
Thread-safe and bounded (never grows unbounded). The bridge reads/searches it for the Logs panel."""
import threading
from collections import deque
from datetime import datetime

_LOCK = threading.Lock()
_BUF = deque(maxlen=500)


def append(level: str, etype: str, message: str, detail: str = "") -> None:
    entry = {"ts": datetime.now().isoformat(timespec="seconds"),
             "level": level, "type": etype, "message": str(message), "detail": str(detail)}
    with _LOCK:
        _BUF.append(entry)


def read(query: str = "", level: str = "", limit: int = 300) -> list:
    """Newest-first, optionally filtered by a free-text query (message/detail/type) and level."""
    q = (query or "").lower()
    lv = (level or "").lower()
    with _LOCK:
        rows = list(_BUF)
    out = []
    for r in reversed(rows):
        if lv and r["level"] != lv:
            continue
        if q and q not in (r["message"] + " " + r["detail"] + " " + r["type"]).lower():
            continue
        out.append(r)
        if len(out) >= int(limit):
            break
    return out


def clear() -> None:
    with _LOCK:
        _BUF.clear()
