"""Batch C static harness — #14/#15 code artifacts. RED before build, GREEN after."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
bridge = (ROOT / "bridge.py").read_text(encoding="utf-8")
jobs = (ROOT / "engine" / "jobs.py").read_text(encoding="utf-8")
logbuf_p = ROOT / "engine" / "logbuf.py"
logbuf = logbuf_p.read_text(encoding="utf-8") if logbuf_p.exists() else ""

checks = [
    # #14
    ("14.1 logbuf ring buffer", "deque" in logbuf and "def append" in logbuf and "def read" in logbuf),
    ("14.2 emit logs + full traceback", "logbuf" in jobs and "format_exc" in jobs),
    ("14.3 bridge get_logs+clear_logs", "def get_logs" in bridge and "def clear_logs" in bridge),
    ("14.4 LOGS tab + renderLogs", 'data-view="logs"' in index and "function renderLogs" in app_js),
    ("14.4b logs search+copy+clear", "get_logs" in app_js and ("clear_logs" in app_js)),
    # #15
    ("15.1 saving stage emit", '"saving' in jobs or "'saving" in jobs),
    ("15.2 job_error carries detail", '"detail"' in jobs and "job_error" in jobs),
    ("15.3 error popup el + handler", 'id="errpop"' in index and "errpop" in app_js),
    ("15.4 popup copy", "errcopy" in app_js or "clipboard" in app_js),
]

fails = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
print(f"\n{len(checks)-len(fails)}/{len(checks)} static checks pass")
sys.exit(1 if fails else 0)
