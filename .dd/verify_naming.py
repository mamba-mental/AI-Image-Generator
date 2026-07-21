"""Spec D (product identity / naming, #7) EXECUTABLE verifier.

Per D-product-identity.md "Verification":
  - product-name-picker.html exists on disk
  - it serves 200 over dashboards_server (:31960)
  - its finalist data array has 5-8 entries, each carrying
    {name, rationale, scores, availability}

Run: python .dd/verify_naming.py
(needs dashboards_server.py already running on :31960 — it is a separate
process this repo doesn't own; if it's down, AC-2/3 fail honestly rather
than being skipped silently.)
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

PAGE_PATH = Path(r"C:\AI CoWork\dashboards\product-name-picker.html")
PAGE_URL = "http://localhost:31960/product-name-picker.html"
REQUIRED_KEYS = ("name", "rationale", "scores", "availability")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


print("Spec D naming-pass verifier")
print("=" * 60)

# ---- AC-1: file exists ----
exists = PAGE_PATH.is_file()
check("AC-1 product-name-picker.html exists", exists, str(PAGE_PATH))
if not exists:
    print("\nBLOCKED — page missing, cannot check further ACs.")
    sys.exit(1)

html = PAGE_PATH.read_text(encoding="utf-8")

# ---- AC-2: serves 200 over :31960 ----
try:
    with urllib.request.urlopen(PAGE_URL, timeout=8) as resp:
        status = resp.status
        served_html = resp.read().decode("utf-8", errors="replace")
    check("AC-2 serves 200 over :31960", status == 200, f"url={PAGE_URL} status={status}")
except Exception as e:  # noqa: BLE001 — report honestly, don't hide network failures
    check("AC-2 serves 200 over :31960", False, f"request failed: {e}")
    served_html = ""

# ---- AC-3: finalist data array, 5-8 entries, each with required keys ----
m = re.search(r"const\s+FINALISTS\s*=\s*(\[.*?\]);", html, re.S)
check("AC-3a FINALISTS array literal found in page source", bool(m))

finalists = []
if m:
    array_src = m.group(1)
    # The array is JS (unquoted keys, HTML strings) not strict JSON — shell out
    # to node (already a system dependency) to eval it and dump real JSON.
    node_script = (
        "const FINALISTS = " + array_src + ";\n"
        "process.stdout.write(JSON.stringify(FINALISTS));\n"
    )
    try:
        proc = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            finalists = json.loads(proc.stdout)
        else:
            check("AC-3b node eval of FINALISTS array", False, proc.stderr.strip()[:300])
    except Exception as e:  # noqa: BLE001
        check("AC-3b node eval of FINALISTS array", False, str(e))

count_ok = 5 <= len(finalists) <= 8
check("AC-3c finalist count in [5, 8]", count_ok, f"count={len(finalists)}")

all_keys_ok = True
missing_detail = []
for f in finalists:
    for k in REQUIRED_KEYS:
        val = f.get(k)
        present = k in f and val not in (None, "", [], {})
        if not present:
            all_keys_ok = False
            missing_detail.append(f"{f.get('name', '<unnamed>')}.{k}")
check(
    "AC-3d every finalist carries name/rationale/scores/availability",
    all_keys_ok,
    "missing: " + ", ".join(missing_detail) if missing_detail else f"{len(finalists)} finalists all complete",
)

# ---- AC-4: credit footer present (dashboard-credit-footer.md hard rule) ----
footer_ok = 'class="prime-credit"' in html and "Spec D naming pass" in html
check("AC-4 mandatory credit footer present", footer_ok)

# ---- AC-5: keep-the-name honest argument present (AC-D8a) ----
keep_ok = "keeping" in html.lower() and "AI Studio Void" in html
check("AC-5 honest keep-the-name argument present (AC-D8a)", keep_ok)

# ---- AC-6: safe-rename plan present (§9 / AC-D9) ----
rename_ok = "APP_NAME" in html and "config-directory migration" in html.lower().replace("<b>", "").replace("</b>", "") or "Config-directory migration" in html
check("AC-6 safe-rename plan present (§9)", rename_ok)

print("=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"{passed}/{total} checks passed")
sys.exit(0 if passed == total else 1)
