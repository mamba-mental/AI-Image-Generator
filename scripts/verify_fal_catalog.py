"""Acceptance verifier for Job 1 (.dd/fal-catalog-full-pull-contract.md).

Reads engine/fal_models.json and checks each AC; prints PASS/FAIL per criterion.
Exit 0 = all pass, 1 = any fail.  Run: python scripts/verify_fal_catalog.py
"""
import glob
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAT = json.loads((ROOT / "engine" / "fal_models.json").read_text(encoding="utf-8"))
MODELS = CAT["models"]
BY = Counter(m["category"] for m in MODELS)

checks = []


def chk(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


chk("AC-1 >=194 text-to-image", BY.get("text-to-image", 0) >= 194, f"{BY.get('text-to-image',0)}")
chk("AC-2 >=125 text-to-video", BY.get("text-to-video", 0) >= 125, f"{BY.get('text-to-video',0)}")
chk("AC-3 image-to-image + image-to-video populated",
    BY.get("image-to-image", 0) > 0 and BY.get("image-to-video", 0) >= 187,
    f"i2i={BY.get('image-to-image',0)} i2v={BY.get('image-to-video',0)}")
with_params = sum(1 for m in MODELS if m.get("params"))
chk("AC-4 >=95% models have params[]", with_params >= 0.95 * len(MODELS),
    f"{with_params}/{len(MODELS)}")
with_desc = sum(1 for m in MODELS for p in m.get("params", []) if p.get("description"))
chk("AC-5 params carry descriptions", with_desc > 0, f"{with_desc} described params total")
chk("AC-6 every model has supports_relaxed_safety(bool)",
    all(isinstance(m.get("supports_relaxed_safety"), bool) for m in MODELS),
    f"{sum(1 for m in MODELS if m.get('supports_relaxed_safety'))} relaxable")
chk("AC-7 every model has price + thumb fields",
    all("price" in m and "thumb" in m for m in MODELS))
baks = glob.glob(str(ROOT / "engine" / "fal_models.json.bak-*"))
chk("AC-8 prior catalog backed up", len(baks) >= 1, f"{len(baks)} backup(s)")

print(f"\nTotal models: {len(MODELS)} across {len(BY)} categories")
for c, n in sorted(BY.items()):
    print(f"  {c}: {n}")

failed = [n for n, ok, _ in checks if not ok]
print(f"\n{'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)}")
sys.exit(1 if failed else 0)
