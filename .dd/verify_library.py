"""Acceptance verifier for .dd/library-features-contract.md (Phase 2 library features).
Hermetic: builds a temp two-folder library with media + sidecars, exercises the SHIPPED
Api methods, asserts AC-1..7 (+AC-3 by source reflection). No app run. Run: python .dd/verify_library.py"""
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bridge  # noqa: E402
from engine import mediaserver, jobs  # noqa: E402

checks = []
def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))

tmp = Path(tempfile.mkdtemp(prefix="voidlib_"))
dirA, dirB = tmp / "archiveA", tmp / "archiveB"
for d in (dirA, dirB, tmp / "out"):
    d.mkdir()
(dirA / "img1.webp").write_bytes(b"x")
(dirA / "img1.webp.json").write_text(json.dumps(
    {"service": "ideogram", "model": "V_3_1", "prompt": "a red apple", "category": "text-to-image"}), encoding="utf-8")
(dirA / "clip1.mp4").write_bytes(b"x")            # video, no sidecar
(dirB / "img2.png").write_bytes(b"x")
(dirB / "img2.png.json").write_text(json.dumps({"service": "xai", "prompt": "blue sky"}), encoding="utf-8")
(dirB / "img1.webp").write_bytes(b"x")            # basename collision with dirA/img1.webp

api = bridge.Api.__new__(bridge.Api)              # bypass heavy __init__
api.config = {"output_directory": str(tmp / "out"), "library_directories": [str(dirA), str(dirB)]}
idxfile = tmp / "index.json"
api._library_index_path = lambda: str(idxfile)
api._persist = lambda: None

# AC-1 — per-image records with folded sidecar fields
recs = api._scan_library([str(dirA), str(dirB)])
byfile = {r["file"]: r for r in recs}
chk("AC-1 records are dicts w/ file+dir+type", all(isinstance(r, dict) and {"file", "dir", "type"} <= set(r) for r in recs))
chk("AC-1 sidecar service/prompt/category folded in",
    byfile.get("img1.webp", {}).get("service") == "ideogram"
    and byfile["img1.webp"].get("prompt") == "a red apple"
    and byfile["img1.webp"].get("category") == "text-to-image")
chk("AC-1 video type derived from ext", byfile.get("clip1.mp4", {}).get("type") == "video")
chk("AC-1 image type derived from ext", byfile.get("img2.png", {}).get("type") == "image")
chk("AC-1 no _path leaks into records", all("_path" not in r for r in recs))

# AC-7 — de-dup by basename, dir integrity
chk("AC-7 basename de-dup (img1.webp once)", [r["file"] for r in recs].count("img1.webp") == 1)
chk("AC-7 every dir is a scanned base", all(r["dir"] in (str(dirA), str(dirB)) for r in recs))

# AC-2 — SQLite Library Index (ADR 0001): returns records, warm reload is stable, DB created
out1 = api.list_library(8000)
chk("AC-2 list_library returns records", bool(out1) and isinstance(out1[0], dict) and "file" in out1[0])
out1b = api.list_library(8000)  # warm reload — pure DB read, same set, no re-crawl
chk("AC-2 warm reload returns same set", {r["file"] for r in out1b} == {r["file"] for r in out1})
chk("AC-2 records carry dir + folded sidecar fields", isinstance(out1[0].get("dir"), str)
    and any(r.get("service") for r in out1))
dbfile = Path(os.path.dirname(idxfile)) / "library.db"
chk("AC-2 SQLite index DB created (replaces JSON index)", dbfile.exists())

# AC-4 — folder enable/disable
chk("AC-4 both dirs enabled initially", set(api._library_dirs()) == {str(dirA), str(dirB)})
api.set_library_dir_enabled(str(dirB), False)
chk("AC-4 disable removes from _library_dirs", str(dirB) not in api._library_dirs() and str(dirA) in api._library_dirs())
chk("AC-4 list_library_dirs marks it disabled", any(d["path"] == str(dirB) and d["enabled"] is False for d in api.list_library_dirs()))
api.set_library_dir_enabled(str(dirB), True)
chk("AC-4 re-enable restores it", str(dirB) in api._library_dirs())

# AC-5 — add folder (valid appends, dup + invalid are no-ops)
dirC = tmp / "archiveC"; dirC.mkdir()
res = api.add_library_dir(str(dirC))
chk("AC-5 add valid dir appends", res.get("ok") and str(dirC) in api._all_library_dirs())
before = len(api._all_library_dirs())
api.add_library_dir(str(dirC))
chk("AC-5 duplicate add is a no-op", len(api._all_library_dirs()) == before)
chk("AC-5 invalid path returns not-ok", api.add_library_dir(str(tmp / "does-not-exist")).get("ok") is False)

# AC-6 — media-server root add/remove round-trip
mediaserver.add_root(str(dirA))
chk("AC-6 add_root registers extra root", str(dirA) in mediaserver._STATE.get("extra", []))
mediaserver.remove_root(str(dirA))
chk("AC-6 remove_root unregisters it", str(dirA) not in mediaserver._STATE.get("extra", []))

# AC-3 — jobs.py persists category into meta (source reflection)
chk("AC-3 jobs.py adds category to saved meta", '"category": params.get("category")' in inspect.getsource(jobs))

print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
