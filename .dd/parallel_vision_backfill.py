"""12-worker parallel vision-tag backfill (PRIME: '2 hours is brutal'). gpt-5.5 via cliproxy
(haiku vision 502s through the proxy — single proven lane, parallelized instead)."""
import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CLIPROXY_API_KEY"] = os.environ.get("CLIPROXY_API_KEY","").strip().strip('"').strip("'")
from engine import vision_tagging as VT
from engine.library_index import LibraryIndex

idx = LibraryIndex(".cache/library.db")
db = idx._db
rows = db.execute("SELECT path FROM images WHERE vision_tagged_at IS NULL").fetchall()
paths = [r["path"] for r in rows if Path(r["path"]).suffix.lower() in (".png",".jpg",".jpeg",".webp")]
print(f"to tag: {len(paths)} (12 workers, gpt-5.5)", flush=True)
lock = threading.Lock(); done = [0]; fail = [0]; t0 = time.time()

def work(p):
    tags = VT.tag_image(p)
    with lock:
        if tags:
            try: idx.mark_vision_tagged(p, tags); done[0]+=1
            except Exception: fail[0]+=1
        else: fail[0]+=1
        n = done[0]+fail[0]
        if n % 100 == 0:
            rate = n/max(1,time.time()-t0)
            print(f"{n}/{len(paths)} tagged={done[0]} fail={fail[0]} ({rate:.1f}/s, ~{(len(paths)-n)/max(rate,0.1)/60:.0f}m left)", flush=True)

with ThreadPoolExecutor(max_workers=12) as pool:
    list(pool.map(work, paths))
print(f"DONE {done[0]} tagged, {fail[0]} failed in {(time.time()-t0)/60:.1f} min", flush=True)
