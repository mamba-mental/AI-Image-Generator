"""Generation history — one JSONL line per completed job, in the output dir.
Survives restarts; the UI reads it for the History view."""
import json
import threading
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()


def _path(output_dir: str) -> Path:
    return Path(output_dir) / "history.jsonl"


def record(output_dir: str, entry: dict) -> None:
    row = {**entry, "ts": datetime.now().isoformat(timespec="seconds")}
    try:
        p = _path(output_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:
        print(f"history record failed: {e}")


def read(output_dir: str, limit: int = 300) -> list:
    p = _path(output_dir)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines[-limit:]):  # newest first
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out
