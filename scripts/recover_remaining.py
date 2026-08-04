"""Targeted recovery of the still-fetchable legacy predictions the bulk run missed.

Only Succeeded + Web predictions retain their input/output on replicate.com (API-source and Failed
predictions have their data auto-removed after ~1h). This fetches exactly that subset from the
`missing` set (in ids.json but not yet in manifest.json), parses prompt/params + downloads images
with UNIQUE basenames (`<pid>_<n>.<ext>`), and appends to the manifest. Resume-safe + idempotent.

Run: python scripts/recover_remaining.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replicate_legacy_scrape import (  # noqa: E402 — reuse the proven fetch/parse/download
    DELAY, DETAIL, IMG_DIR, MANIFEST, IDS_FILE, OUT, _ext, download, fetch, get_cookie,
    load_json, parse_detail,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    cookie = get_cookie()
    ids = load_json(IDS_FILE, [])
    manifest = load_json(MANIFEST, [])
    done = {m["id"] for m in manifest}
    # the only recoverable subset: Succeeded + Web, not already captured
    todo = [r for r in ids if r["id"] not in done
            and r.get("status") == "Succeeded" and r.get("source") == "Web"]
    print(f"{len(todo)} Succeeded+Web predictions to recover ({len(done)} already in manifest)")

    added, imgs_total, skipped = 0, 0, 0
    for i, row in enumerate(todo, 1):
        pid = row["id"]
        try:
            d = parse_detail(pid, fetch(DETAIL.format(pid), cookie))
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(todo)}] {pid} FETCH FAIL {type(e).__name__} — skip")
            skipped += 1
            time.sleep(DELAY)
            continue
        d["created"] = row.get("created", "")
        d["source"] = row.get("source", "")
        if not d["model"]:
            d["model"] = row.get("model", "")
        files = []
        for n, u in enumerate(d["output_urls"]):
            dest = IMG_DIR / pid / f"{pid}_{n}{_ext(u)}"   # UNIQUE basename (matches the naming patch)
            if dest.exists() or download(u, dest):
                files.append(str(dest.relative_to(OUT)))
        d["images"] = files
        imgs_total += len(files)
        manifest.append(d)
        added += 1
        if i % 10 == 0 or i == len(todo):
            MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(f"[{i}/{len(todo)}] {pid} {d['model'][:26]:26} imgs {len(files)} "
              f"prompt {str(d['prompt'])[:36]!r}")
        time.sleep(DELAY)
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\nDONE — added {added} records, {imgs_total} images, {skipped} skipped. "
          f"manifest now {len(manifest)}.")
    print("Next: ingest_to_library.py --manifest ... --register, then rename_recover_unique.py (idempotent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
