"""Acceptance verifier for .dd/output-findability-contract.md (Spec C #6).
Hermetic (temp dirs, no NAS). Run: python .dd/verify_output.py"""
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows cp1252 stdout can't encode → / — glyphs
except Exception:
    pass
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bridge  # noqa: E402
from engine import save  # noqa: E402

checks = []
def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))

tmp = Path(tempfile.mkdtemp(prefix="voidout_"))
out = tmp / "out"; out.mkdir()

# ── AC-6.1 — dated folder + collision-proof, sortable, parseable filename ──
paths = save.make_output_paths(str(out), 3, ext=".png", seed=1234567)
rel = [os.path.relpath(p, str(out)).replace("\\", "/") for p in paths]
ym = save.month_dir(str(out))
chk("AC-6.1 saves under generated/YYYY-MM/", all(r.startswith("generated/") and re.match(r"generated/\d{4}-\d{2}/", r) for r in rel),
    rel[0])
pat = re.compile(r"^\d{8}-\d{6}-\d{3}-\d{4}-[0-9a-z]{6}\.png$")
names = [Path(p).name for p in paths]
chk("AC-6.1 filename pattern (stamp-ms-seq-seedslug)", all(pat.match(n) for n in names), names[0])
chk("AC-6.1 3 concurrent-run names distinct", len(set(names)) == 3)
chk("AC-6.1 seed slug encodes seed (not 000000)", names[0].split("-")[-1] != "000000.png", names[0])
chk("AC-6.1 no-seed → 000000 slug", save._seed_slug(None) == "000000")
chk("AC-6.1 names sort chronologically", names == sorted(names))

# ── AC-6.3 — validate_output_root guard ──
drive_root = Path(str(out).split(os.sep)[0] + os.sep)          # e.g. C:\
chk("AC-6.3 rejects drive root", save.validate_output_root(str(drive_root))[0] is False, str(drive_root))
chk("AC-6.3 rejects UNC share root", save.validate_output_root(r"\\server\share")[0] is False)
chk("AC-6.3 rejects filesystem root", save.validate_output_root("/")[0] is False)
chk("AC-6.3 rejects nonexistent dir", save.validate_output_root(str(tmp / "nope"))[0] is False)
chk("AC-6.3 accepts a real writable subfolder", save.validate_output_root(str(out))[0] is True)

# ── AC-6.2 — auto-register + immediate findability via the Api ──
api = bridge.Api.__new__(bridge.Api)
api.config = {"output_directory": str(out), "library_directories": []}
api._library_index_path = lambda: str(tmp / "index.json")
api._persist = lambda: None

# set_config rejects a bad root and accepts a good one
chk("AC-6.3 set_config rejects drive root", api.set_config({"output_directory": str(drive_root)}).get("ok") is False)
chk("AC-6.3 set_config accepts valid dir", api.set_config({"output_directory": str(out)}).get("ok") is True)

# a fresh generation lands in generated/YYYY-MM
gen = Path(save.make_output_paths(str(out), 1)[0])
gen.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
gen_json = Path(str(gen) + ".json")
gen_json.write_text('{"service":"fal","model":"m","prompt":"a test render"}', encoding="utf-8")

api._ensure_output_registered()
chk("AC-6.2 generated root auto-registered in scan set",
    save.generated_root(str(out)) in api._all_library_dirs())
api.refresh_generated()
found = {r["file"] for r in api.list_library(8000)}
chk("AC-6.2 fresh generation findable in Library", gen.name in found, gen.name)

if hasattr(api, "_lib_idx"):
    api._lib_idx.close()
print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
