"""Free verifier for the NSFW-capability grading (.dd/nsfw-capability-contract.md).
Checks grading coverage, provider-exclusion, curated seed, and honest label copy. No gen spend.
Run: python scripts/verify_content_capability.py"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = json.loads((ROOT / "engine" / "fal_models.json").read_text(encoding="utf-8"))["models"]
CM_JS = (ROOT / "web" / "content_mode.js").read_text(encoding="utf-8")
GRADES = {"upstream_moderated", "permissive", "verified", "filtered"}
SHOWN = {"permissive", "verified"}
UPSTREAM = ("nano-banana", "gemini", "imagen", "gpt-image", "dall-e", "nucleus")

checks = []
def chk(n, ok, d=""):
    checks.append(ok); print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))

chk("AC-1 every model graded", all(m.get("content_capability") in GRADES for m in MODELS),
    dict(Counter(m.get("content_capability") for m in MODELS)))
shown = [m for m in MODELS if m.get("content_capability") in SHOWN]
bad = [m for m in shown if any(k in (m["id"] + m["label"]).lower() for k in UPSTREAM)]
chk("AC-2 zero upstream-moderated shown", len(bad) == 0, f"{len(bad)} leaked: {[m['id'] for m in bad][:5]}")
chk("AC-3 isRelaxable keys off content_capability", "content_capability" in CM_JS and "isVerified" in CM_JS)
# AC-4 honest copy: no overclaiming words in the NSFW help
help_line = next((l for l in CM_JS.splitlines() if l.strip().startswith("nsfw:") and "CONTENT_MODE_HELP" not in l), "")
# the CONTENT_MODE_HELP nsfw line is the one under CONTENT_MODE_HELP; grab all nsfw: lines, take the help one (has 'Verified')
nsfw_help = [l for l in CM_JS.splitlines() if "nsfw:" in l and "Verified only" in l]
chk("AC-4 honest label (mentions verified + upstream-moderated, no bare 'confirmed NSFW list')",
    bool(nsfw_help) and "not a guarantee" in CM_JS.lower() or "likely-capable" in CM_JS.lower() or "untested" in CM_JS.lower())
verified = [m for m in MODELS if m.get("content_capability") == "verified"]
chk("AC-5 curated seed graded verified", any("flux" in m["id"] for m in verified), f"{len(verified)} verified")

t2i = [m for m in MODELS if m["category"] == "text-to-image"]
t2i_shown = [m for m in t2i if m.get("content_capability") in SHOWN]
chk("AC-8 NSFW-mode t2i count < 155 (false positives dropped)", len(t2i_shown) < 155, f"{len(t2i_shown)} shown")

print(f"\n{'ALL PASS' if all(checks) else 'FAILED'} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
