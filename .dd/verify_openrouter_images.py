"""verify openrouter /api/v1/images migration: dedicated endpoint tried first with size control,
400 → aspect_ratio-only retry, then legacy chat fallback. Mocks the network (no spend)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os; os.environ["OPENROUTER_API_KEY"] = "test-key"
from engine.backends import openrouter_api as OR
from PIL import Image
import io, base64

calls = []
def _png_b64():
    b = io.BytesIO(); Image.new("RGB",(8,8),(1,2,3)).save(b,"PNG"); return base64.b64encode(b.getvalue()).decode()

checks = []
def chk(n, ok): checks.append(ok); print(f"[{'PASS' if ok else 'FAIL'}] {n}")

# scenario A: /images works first try with size
def post_A(url, body, key, timeout=180):
    calls.append((url, dict(body)))
    return {"data":[{"b64_json": _png_b64()}]}
OR._post = post_A; calls.clear()
out = OR.generate("google/gemini-3-flash-image", {"prompt":"x","width":1536,"height":1024,"aspect_ratio":"3:2"})
chk("A hits /images endpoint first", calls and calls[0][0].endswith("/images"))
chk("A sends size 1536x1024", calls[0][1].get("size")=="1536x1024")
chk("A sends aspect_ratio", calls[0][1].get("aspect_ratio")=="3:2")
chk("A returns a PIL image", len(out)==1 and hasattr(out[0],"size"))

# scenario B: /images 400 on full → aspect_only retry succeeds
import urllib.error
state = {"n":0}
def post_B(url, body, key, timeout=180):
    calls.append((url, dict(body)))
    if url.endswith("/images") and "size" in body:
        raise urllib.error.HTTPError(url, 400, "bad size trio", {}, io.BytesIO(b"mismatch"))
    return {"data":[{"b64_json": _png_b64()}]}
OR._post = post_B; calls.clear()
out = OR.generate("m", {"prompt":"x","width":1024,"height":1024,"aspect_ratio":"1:1"})
chk("B retries aspect_ratio-only after 400", any(c[0].endswith("/images") and "size" not in c[1] and c[1].get("aspect_ratio")=="1:1" for c in calls))
chk("B recovers an image", len(out)==1 and hasattr(out[0],"size"))

# scenario C: /images always 400 → legacy chat fallback
def post_C(url, body, key, timeout=180):
    calls.append((url, dict(body)))
    if url.endswith("/images"):
        raise urllib.error.HTTPError(url, 400, "unsupported", {}, io.BytesIO(b"no"))
    return {"choices":[{"message":{"images":[{"image_url":{"url":"data:image/png;base64,"+_png_b64()}}]}}]}
OR._post = post_C; calls.clear()
out = OR.generate("legacy/model", {"prompt":"x","aspect_ratio":"16:9"})
chk("C falls back to chat/completions", any(c[0].endswith("/chat/completions") for c in calls))
chk("C still returns an image via legacy", len(out)==1 and hasattr(out[0],"size"))

print(f"\n{'ALL PASS' if all(checks) else 'FAILED '+str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
