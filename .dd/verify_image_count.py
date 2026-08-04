"""Replicate loop-N image count. Run: python .dd/verify_image_count.py"""
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import jobs  # noqa: E402

jobs.keypool.size = lambda s: 1   # single key → no rotation noise in the test
reg = jobs.JobRegistry()
cancel = threading.Event()
def prog(*a, **k): pass
app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
results = []


def chk(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ---- AC-1/2/3: N calls, distinct seeds, num_outputs forced to 1 ----
calls = []
def mock(model, params, progress=None, cancel_event=None):
    calls.append(dict(params))
    return [f"https://x/{len(calls)}.png"]
res, cancelled = reg._batch_generate("replicate", mock, "m", {"_n_images": 3, "seed": 100}, prog, cancel)
chk("AC-1 N=3 -> 3 results, 3 backend calls", len(res) == 3 and len(calls) == 3, f"{len(res)} results / {len(calls)} calls")
chk("AC-3 each call forces num_outputs=1 while looping", all(c.get("num_outputs") == 1 for c in calls))
chk("AC-2 seeds distinct per pass", [c.get("seed") for c in calls] == [100, 101, 102], str([c.get("seed") for c in calls]))

# ---- AC-4: no _n_images -> exactly ONE call, params untouched ----
calls.clear()
res, _ = reg._batch_generate("replicate", mock, "m", {"seed": 5}, prog, cancel)
chk("AC-4 target=1 -> single call, num_outputs untouched", len(calls) == 1 and "num_outputs" not in calls[0])

# ---- AC-5a: first-call error -> surfaced ----
res, _ = reg._batch_generate("replicate", lambda *a, **k: ["Replicate Error: boom"], "m", {"_n_images": 3}, prog, cancel)
chk("AC-5a first-call error returned as error", len(res) == 1 and "Error" in res[0])

# ---- AC-5b: error AFTER partial -> keep the partial ----
seq = [["https://x/ok.png"], ["Replicate Error: later boom"]]
box = {"i": 0}
def mock_partial(model, params, progress=None, cancel_event=None):
    r = seq[min(box["i"], len(seq) - 1)]; box["i"] += 1; return r
res, _ = reg._batch_generate("replicate", mock_partial, "m", {"_n_images": 4}, prog, cancel)
chk("AC-5b error after partial -> keep the good results", res == ["https://x/ok.png"], str(res))

# ---- AC-6: frontend control + wiring ----
chk("AC-6 #numimages control in index.html", 'id="numimages"' in index_html and 'id="numimgwrap"' in index_html)
chk("AC-6 request sends _n_images for replicate", 'genParams._n_images = state.numImages' in app_js)
chk("AC-6 num_outputs hidden from Replicate param form",
    'state.service === "replicate"' in app_js and 'p.name !== "num_outputs"' in app_js)

fails = results.count(False)
print(f"\n{len(results) - fails}/{len(results)} checks pass")
sys.exit(1 if fails else 0)
