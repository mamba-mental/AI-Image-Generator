"""AC-8 — lightbox metadata resolves for NESTED archive images (the recover folder).

The bug: bridge.read_meta scanned only <library_dir>/<name>.json (top level), so a recover image at
.replicate_recover/images/<id>/<name> — whose sidecar sits BESIDE it, nested — always missed → the
lightbox showed no prompt/metadata even though the tile (fed by the DB) showed it.

This proves: (a) the OLD top-level scan finds nothing for a recover image, and (b) the NEW resolution
(library.db name->real path, then <path>.json) returns the prompt. Mirrors bridge.read_meta step (1).

Run: python .dd/verify_lightbox_meta.py
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / ".cache" / "library.db"
RECOVER = str(ROOT / "scripts" / ".replicate_recover" / "images")
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
con.row_factory = sqlite3.Row
con.execute("PRAGMA busy_timeout=5000")
# a recover image that HAS a prompt in the DB
row = con.execute("SELECT name, path, prompt FROM images WHERE folder=? "
                  "AND prompt IS NOT NULL AND trim(prompt)!='' LIMIT 1", (RECOVER,)).fetchone()
chk("setup: found a recover image with a prompt", row is not None)

if row:
    name = row["name"]
    # (a) OLD behavior — top-level sidecar scan of the registered folder: MUST miss (proves the bug)
    top_level = os.path.join(RECOVER, name + ".json")
    chk("AC-8a OLD top-level sidecar scan misses the nested recover image (the bug)",
        not os.path.exists(top_level), f"top-level path absent: {name}.json")

    # (b) NEW behavior — bridge.read_meta step (1): DB name -> real path -> nested sidecar with prompt
    r = con.execute("SELECT path, prompt FROM images WHERE name=? LIMIT 1", (name,)).fetchone()
    nested_side = str(r["path"]) + ".json"
    side_ok = os.path.exists(nested_side)
    prompt_ok = False
    if side_ok:
        try:
            data = json.loads(Path(nested_side).read_text(encoding="utf-8"))
            prompt_ok = bool((data.get("prompt") or "").strip())
        except Exception:
            pass
    chk("AC-8b NEW resolution finds the nested sidecar", side_ok, nested_side)
    chk("AC-8c NEW resolution yields a non-empty prompt", prompt_ok,
        f"prompt: {str(r['prompt'])[:50]!r}")

con.close()

# (c) source-level guard: read_meta actually queries the DB (step 1), not only the top-level scan
src = (ROOT / "bridge.py").read_text(encoding="utf-8")
rm = src[src.find("def read_meta"):src.find("def save_as")]
chk("AC-8d read_meta resolves via library.db before the top-level scan",
    "library.db" in rm and "SELECT path" in rm and "WHERE name=?" in rm)

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
