"""Acceptance verifier for the Runware lane (Agent A batch, 2026-07-21): key auth, a real
resolved-AIR render, prompt-sha provenance on the evidence, and the console reflecting it.
Run: python .dd/verify_runware_lane.py"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import config as ecfg  # noqa: E402

checks = []


def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


cfg = ecfg.load()
ecfg.resolve_keys(cfg)
KEY = os.environ.get("RUNWARE_API_KEY")

# AC-1 — key auth OK (a live, free modelSearch call — no image spend)
if KEY:
    req = urllib.request.Request(
        "https://api.runware.ai/v1",
        data=json.dumps([{"taskType": "modelSearch", "taskUUID": str(uuid.uuid4()),
                           "search": "flux", "limit": 1}]).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        auth_ok = bool(d.get("data")) and not d.get("errors")
        chk("AC-1 Runware key auth OK (modelSearch round-trip)", auth_ok,
            "" if auth_ok else json.dumps(d.get("errors", d))[:200])
    except urllib.error.HTTPError as e:
        chk("AC-1 Runware key auth OK (modelSearch round-trip)", False, f"HTTP {e.code}")
else:
    chk("AC-1 Runware key auth OK (modelSearch round-trip)", False, "RUNWARE_API_KEY not configured")

# AC-2 — resolved checkpoints/loras files exist with real AIRs (never a guessed id)
ck_path = ROOT / "engine" / "runware_checkpoints.json"
lo_path = ROOT / "engine" / "runware_loras.json"
ck = json.loads(ck_path.read_text(encoding="utf-8")) if ck_path.exists() else {}
lo = json.loads(lo_path.read_text(encoding="utf-8")) if lo_path.exists() else {}
chk("AC-2 runware_checkpoints.json has resolved AIRs", bool(ck.get("checkpoints")),
    f"{len(ck.get('checkpoints', []))} rows")
chk("AC-2 runware_loras.json has resolved AIRs", bool(lo.get("loras")),
    f"{len(lo.get('loras', []))} rows")
chk("AC-2 every resolved checkpoint AIR has a provider prefix (civitai:/x:/…, never guessed)",
    all(":" in r["air"] and "@" in r["air"] for r in ck.get("checkpoints", [])))

# AC-3 — nsfw_capability.json has runware evidence rows carrying the prompt sha + a real render URL
PROMPT_SHA = hashlib.sha256((ROOT / "engine" / "nsfw_benchmark_prompt.txt").read_text(encoding="utf-8").strip().encode()).hexdigest()
cap = json.loads((ROOT / "engine" / "nsfw_capability.json").read_text(encoding="utf-8"))
rw_rows = {k: v for k, v in cap.get("models", {}).items() if v.get("provider") == "runware"}
chk("AC-3 nsfw_capability.json has runware evidence rows", bool(rw_rows), f"{len(rw_rows)} rows")
chk("AC-3 runware evidence carries the correct sent_prompt_sha256",
    all(v.get("sent_prompt_sha256") == PROMPT_SHA for v in rw_rows.values()))
verified_with_url = [v for v in rw_rows.values() if v.get("grade") == "verified" and (v.get("sample_urls") or [])]
chk("AC-3 >=1 runware AIR produced a real verified render URL", len(verified_with_url) >= 1,
    f"{len(verified_with_url)} verified w/ sample_urls")

# AC-4 — console reflects it (live NAS deploy)
console_json = ROOT.parent / "dashboards" / "data" / "nsfw-verified.json"
# repo root here is the AI-Image-Generator checkout; the console lives in the sibling AI CoWork repo
console_json = Path(r"C:/AI CoWork/dashboards/data/nsfw-verified.json")
cj = json.loads(console_json.read_text(encoding="utf-8")) if console_json.exists() else {}
console_rw = [m for m in cj.get("models", []) if m.get("provider") == "runware"]
chk("AC-4 console data (dashboards/data/nsfw-verified.json) includes runware rows", bool(console_rw),
    f"{len(console_rw)} rows")
try:
    live = json.loads(urllib.request.urlopen("http://192.168.86.97:31961/data/nsfw-verified.json", timeout=10).read())
    live_rw = [m for m in live.get("models", []) if m.get("provider") == "runware"]
    chk("AC-4 live NAS console (:31961) serves runware rows", bool(live_rw), f"{len(live_rw)} rows")
except Exception as e:
    chk("AC-4 live NAS console (:31961) serves runware rows", False, f"{type(e).__name__}: {e}")

print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
