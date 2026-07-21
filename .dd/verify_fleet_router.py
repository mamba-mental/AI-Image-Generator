"""Acceptance verifier for docs/specs/E-fleet-access-advisor.md (Spec E — model-fleet
access advisor dashboard). Runs against the LIVE dashboards_server on :31960 — restart it
after any server-side edit before running this. Run: python ".dd/verify_fleet_router.py"
"""
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:31960"
AI_COWORK = Path(r"C:\AI CoWork")
SERVER_SRC = AI_COWORK / "scripts" / "dashboards_server.py"
CHECK_VOCAB = AI_COWORK / "scripts" / "check_router_vocab.py"

checks = []


def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


def get(path, timeout=15):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read()


def post_json(path, body, timeout=90):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# AC-E5 / page-serves — model-fleet-router.html is 200 over :31960
try:
    status, body = get("/model-fleet-router.html")
    chk("page serves 200 over :31960", status == 200 and b"Model Fleet Router" in body and len(body) > 0,
        f"status={status} bytes={len(body)}")
except Exception as e:  # noqa: BLE001
    chk("page serves 200 over :31960", False, f"request failed: {e}")

# AC-E-DATA — GET /api/fleet-catalog schema, >=1 model, accessible flags present
allowed_ids = set()
try:
    status, body = get("/api/fleet-catalog")
    data = json.loads(body.decode("utf-8"))
    schema_ok = (status == 200 and {"fetched_at", "live_ok", "models"} <= set(data.keys())
                 and isinstance(data["models"], list) and len(data["models"]) >= 1
                 and all({"id", "provider", "access_path", "capability", "price", "accessible"} <= set(m.keys())
                         for m in data["models"]))
    chk("GET /api/fleet-catalog returns the AC-E-DATA schema with >=1 model + accessible flags",
        schema_ok, f"status={status} models={len(data.get('models', []))} live_ok={data.get('live_ok')}")
    allowed_ids = {m["id"] for m in data.get("models", [])}
    accessible_ids = {m["id"]: m for m in data.get("models", []) if m.get("accessible")}
except Exception as e:  # noqa: BLE001
    chk("GET /api/fleet-catalog returns the AC-E-DATA schema with >=1 model + accessible flags", False, str(e))
    accessible_ids = {}

# AC-E2 — "fleet" registered in BOTH SYSTEM_PROMPTS and PROSE_SCOPES (grep the server source)
try:
    src = SERVER_SRC.read_text(encoding="utf-8", errors="replace")
    sp_block_m = re.search(r"SYSTEM_PROMPTS\s*=\s*\{(.*?)\n\}", src, re.S)
    sp_block = sp_block_m.group(1) if sp_block_m else ""
    in_system_prompts = bool(re.search(r'["\']fleet["\']\s*:', sp_block))
    ps_line_m = re.search(r"PROSE_SCOPES\s*=\s*\{([^}]*)\}", src)
    ps_line = ps_line_m.group(1) if ps_line_m else ""
    in_prose_scopes = bool(re.search(r'["\']fleet["\']', ps_line))
    chk('"fleet" registered in SYSTEM_PROMPTS', in_system_prompts)
    chk('"fleet" registered in PROSE_SCOPES', in_prose_scopes)
except Exception as e:  # noqa: BLE001
    chk('"fleet" registered in SYSTEM_PROMPTS', False, str(e))
    chk('"fleet" registered in PROSE_SCOPES', False, str(e))

# AC-E2 — /api/route scope=fleet does NOT 400 / fall back to an unknown-scope error
status, resp = post_json("/api/route", {"query": "sanity ping — do not answer, just confirm scope routing", "scope": "fleet"})
chk("/api/route scope=fleet does not 400 / fall back", status == 200 and "error" not in resp,
    f"status={status} keys={sorted(resp.keys())}")

# AC-E3 — a real Ask-AI fleet call: >=1 model id EXACTLY in allowed_ids (from /api/fleet-catalog)
# + that model's provider + access-path, plus the Source: citation line, verbatim in the answer.
status, resp = post_json(
    "/api/route",
    {"query": "Which model should I use for a general coding task with a large context window?", "scope": "fleet"})
answer = (resp.get("answer") or "") if status == 200 else ""
named_allowed = [mid for mid in allowed_ids if mid and mid in answer]
chk("fleet Ask-AI answer names >=1 model id exactly in allowed_ids", len(named_allowed) >= 1,
    f"named={named_allowed[:3]}")
if named_allowed:
    m = accessible_ids.get(named_allowed[0]) or {}
    prov_ok = bool(m.get("provider")) and m["provider"] in answer
    path_ok = bool(m.get("access_path")) and m["access_path"] in answer
    chk("answer includes that model's provider", prov_ok, m.get("provider"))
    chk("answer includes that model's access-path", path_ok, m.get("access_path"))
else:
    chk("answer includes that model's provider", False, "no named model to check")
    chk("answer includes that model's access-path", False, "no named model to check")
chk('answer ends with the "Source: fleet-catalog.json @ <ts> · cliproxy @ <ts>" citation line',
    bool(re.search(r"Source:\s*fleet-catalog\.json\s*@\s*.+?\s*·\s*cliproxy\s*@\s*\S+", answer)),
    answer[-140:] if answer else "(empty answer)")

# check_router_vocab.py green
try:
    r = subprocess.run([sys.executable, str(CHECK_VOCAB)], capture_output=True, text=True, timeout=120,
                        cwd=str(AI_COWORK))
    chk("scripts/check_router_vocab.py exits 0 (green)", r.returncode == 0,
        (r.stdout.strip().splitlines() or ["no output"])[-1])
except Exception as e:  # noqa: BLE001
    chk("scripts/check_router_vocab.py exits 0 (green)", False, str(e))

print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
