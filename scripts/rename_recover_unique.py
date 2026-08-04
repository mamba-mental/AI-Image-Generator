"""Give the recovered Replicate images UNIQUE basenames so the omni-image library stops
collapsing them (it de-dupes tiles by basename, and every prediction's outputs were named
`0.png`/`1.png` inside their own subfolder -> 5,080 images shown as ~104 tiles).

Rename  images/<id>/<n>.<ext>  ->  images/<id>/<id>_<n>.<ext>
and follow it atomically in library.db (name + path) and in the `<image>.json` sidecar.

SAFE:
  * online DB backup to .cache/library.db.bak-<ts> BEFORE any write (consistent snapshot).
  * DRY-RUN by default — prints the plan + a collision check. Pass --go to execute.
  * IDEMPOTENT — a row/file already named `<id>_...` is skipped, so re-runs are no-ops.
  * REVERSIBLE — writes scripts/.replicate_recover/rename_map.json (new->old) for rollback.

Run:
  python scripts/rename_recover_unique.py            # dry-run (plan only)
  python scripts/rename_recover_unique.py --go        # execute
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")   # cron/pipe-safe (cp1252 crashes on em-dash/emoji)
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
DB = REPO / ".cache" / "library.db"
RECOVER = REPO / "scripts" / ".replicate_recover" / "images"
RECOVER_STR = str(RECOVER)
MAP_FILE = REPO / "scripts" / ".replicate_recover" / "rename_map.json"


def new_name(pid: str, old_name: str) -> str:
    """Pure mapping: prefix the basename with the prediction id (its parent dir). Idempotent."""
    return old_name if old_name.startswith(pid + "_") else f"{pid}_{old_name}"


def build_plan(con: sqlite3.Connection) -> list[dict]:
    """One entry per recover DB row that still needs renaming. Drives off the DB (what the app reads);
    verifies the file on disk separately at execute time."""
    plan = []
    for r in con.execute("SELECT name, path FROM images WHERE folder=?", (RECOVER_STR,)):
        old_path = Path(r["path"])
        pid = old_path.parent.name
        nn = new_name(pid, r["name"])
        if nn == r["name"]:
            continue  # already unique — idempotent skip
        plan.append({
            "pid": pid,
            "old_name": r["name"], "new_name": nn,
            "old_path": str(old_path), "new_path": str(old_path.with_name(nn)),
        })
    return plan


def check_collisions(plan: list[dict]) -> list[str]:
    seen, dups = set(), []
    for e in plan:
        if e["new_path"] in seen:
            dups.append(e["new_path"])
        seen.add(e["new_path"])
    return dups


def main() -> int:
    go = "--go" in sys.argv
    if not DB.exists():
        print(f"NO DB at {DB}")
        return 2

    con = sqlite3.connect(str(DB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.row_factory = sqlite3.Row

    plan = build_plan(con)
    dups = check_collisions(plan)
    print(f"recover rows needing rename : {len(plan)}")
    print(f"planned new-path collisions : {len(dups)}  (must be 0)")
    if plan[:2]:
        for e in plan[:2]:
            print(f"  e.g. {e['old_name']}  ->  {e['new_name']}")
    if dups:
        print("ABORT — collisions in the plan, no changes made.")
        return 3
    if not plan:
        print("Nothing to do — all recover names already unique (idempotent).")
        return 0
    if not go:
        print("\nDRY-RUN. Re-run with --go to execute (DB is backed up first).")
        return 0

    # ---- online DB backup (consistent even while the app holds the DB) ----
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = DB.with_suffix(f".db.bak-{ts}")
    with sqlite3.connect(str(bak)) as bcon:
        con.backup(bcon)
    print(f"DB backed up -> {bak.name}")

    # ---- execute: rename file + sidecar, then UPDATE the DB row, batch-commit ----
    rmap, renamed, missing, sidecars = {}, 0, 0, 0
    for i, e in enumerate(plan, 1):
        op, np = Path(e["old_path"]), Path(e["new_path"])
        if op.exists():
            op.rename(np)
        elif np.exists():
            pass  # already moved on disk (idempotent), still fix the DB below
        else:
            missing += 1
            continue
        # sidecar `<image>.json` follows the image
        os_side, ns_side = Path(str(op) + ".json"), Path(str(np) + ".json")
        if os_side.exists():
            os_side.rename(ns_side)
            sidecars += 1
        con.execute("UPDATE images SET name=?, path=? WHERE path=?",
                    (e["new_name"], e["new_path"], e["old_path"]))
        rmap[e["new_path"]] = e["old_path"]
        renamed += 1
        if i % 500 == 0:
            con.commit()
            print(f"  ...{i}/{len(plan)}")
    con.commit()
    con.close()

    prior = json.loads(MAP_FILE.read_text(encoding="utf-8")) if MAP_FILE.exists() else {}
    prior.update(rmap)
    MAP_FILE.write_text(json.dumps(prior, indent=1), encoding="utf-8")

    print(f"\nDONE — files renamed {renamed}, sidecars {sidecars}, missing-on-disk {missing}")
    print(f"reversal map -> {MAP_FILE}  ({len(prior)} entries)")
    print("Restart / ↻-refresh the app so its in-memory library + thumb-cache pick up the new names.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
