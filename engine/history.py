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


def _read_records(p: Path) -> list:
    """Parse a history.jsonl into a list of dicts (skips blank/corrupt lines)."""
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _dedup_key(rec: dict):
    """Identity for de-duping merged records: (ts, first-file). ts alone can collide (two gens in
    the same second); the first output file disambiguates. Falls back to the whole record when a
    row carries no files, so a distinct-but-file-less record is never silently dropped."""
    files = rec.get("files") or []
    return (rec.get("ts"), files[0] if files else json.dumps(rec, sort_keys=True))


def merge_records(*record_lists) -> list:
    """Merge record lists, de-dup by _dedup_key (first occurrence wins), return chronological order."""
    seen, merged = set(), []
    for recs in record_lists:
        for r in recs:
            k = _dedup_key(r)
            if k in seen:
                continue
            seen.add(k)
            merged.append(r)
    merged.sort(key=lambda r: r.get("ts") or "")   # ISO strings sort chronologically
    return merged


def _write_records(p: Path, records: list) -> None:
    with _LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")


def _pull_forward_parent(output_dir: str) -> None:
    """If the output dir moved (e.g. `I:\\` -> `I:\\generated`), a history.jsonl gets stranded ONE
    level up. Merge the immediate parent's records forward (dedup) so a dir move never strands
    history again. Bounded to the parent only, and rewrites ONCE — subsequent calls find the parent
    fully subsumed and do nothing (no churn on every read)."""
    try:
        out = _path(output_dir)
        parent = Path(output_dir).parent / "history.jsonl"
        if not parent.exists() or parent.resolve() == out.resolve():
            return
        out_recs = _read_records(out)
        parent_recs = _read_records(parent)
        seen = {_dedup_key(r) for r in out_recs}
        if not any(_dedup_key(r) not in seen for r in parent_recs):
            return   # parent already fully present — nothing to pull forward, no rewrite
        _write_records(out, merge_records(out_recs, parent_recs))
    except Exception as e:
        print(f"history pull-forward failed: {e}")


def read(output_dir: str, limit: int = 300) -> list:
    _pull_forward_parent(output_dir)   # defensive: recover a history.jsonl stranded by a dir move
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
