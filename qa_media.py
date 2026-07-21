"""Prove fal video + 3D produce real output through the app's fal_api path."""
import sys, time
sys.path.insert(0, ".")
from bridge import Api
Api()  # export keys
from engine.backends import fal_api

CASES = [
    ("video", "bytedance/seedance-2.0/fast/text-to-video", {"prompt": "a red maple leaf spinning slowly on white"}),
    ("3d",    "fal-ai/hyper3d/rodin/v2.5/text-to-3d/fast",  {"prompt": "a small red maple leaf"}),
]
for kind, model, params in CASES:
    t = time.time()
    try:
        res = fal_api.generate(model, params, progress=lambda m: None)
        f = res[0] if res else None
        if isinstance(f, str) and "Error" in f:
            print(f"{kind:6} {model:44} {time.time()-t:5.0f}s  FAIL  {f[:150]}")
        elif isinstance(f, str) and f.startswith("http"):
            ext = f.split('?')[0].split('.')[-1]
            print(f"{kind:6} {model:44} {time.time()-t:5.0f}s  OK    .{ext}  {f[:70]}")
        else:
            print(f"{kind:6} {model:44} {time.time()-t:5.0f}s  ?     {type(f).__name__} {str(f)[:80]}")
    except Exception as e:
        print(f"{kind:6} {model:44} {time.time()-t:5.0f}s  FAIL  {type(e).__name__}: {e}"[:150])
