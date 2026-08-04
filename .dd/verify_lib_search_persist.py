"""Library search/filters persist across view switches. Static harness (no JS runtime in repo):
proves the query+filters live in state (not just the DOM), are restored on render, saved on filter.
Run: python .dd/verify_lib_search_persist.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
checks = []


def chk(name, ok, detail=""):
    checks.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def fn(name):
    m = re.search(r"function " + name + r"\([^)]*\)\s*\{", app_js)
    if not m:
        return ""
    i, depth = m.end(), 1
    while depth and i < len(app_js):
        if app_js[i] == "{":
            depth += 1
        elif app_js[i] == "}":
            depth -= 1
        i += 1
    return app_js[m.end():i - 1]


# state carries the fields
chk("state.libFilter has q/folder/service/type fields",
    all(k in app_js for k in ("libFilter: {", "q: \"\"")) and re.search(r"libFilter:\s*\{[^}]*q:", app_js) is not None)

# the search input is seeded from state on render
chk("renderLibrary seeds #libq value from state.libFilter.q",
    'id="libq"' in app_js and "value=\"${escapeHtml(state.libFilter.q" in app_js)

# applyLibFilter WRITES the current values back to state (so they survive a rebuild)
af = fn("applyLibFilter")
chk("applyLibFilter persists q/folder/service/type into state.libFilter",
    "Object.assign(state.libFilter" in af and "q: rawq" in af and "service: svc" in af and "type" in af)

# loadLibrary RESTORES the selects from state
ll = fn("loadLibrary")
chk("loadLibrary restores folder/service/type selects from state",
    "folderSel.value = state.libFilter.folder" in ll and "svcSel.value = state.libFilter.service" in ll
    and 'state.libFilter.type' in ll)

fails = checks.count(False)
print(f"\n{len(checks) - fails}/{len(checks)} checks pass")
sys.exit(1 if fails else 0)
