"""Multi-provider NSFW capability sweep (Spec B §2/§3, the WIDEST scope PRIME authorized).

For every reachable, non-excluded model across fal + novita + together + agnes, run PRIME's REAL
explicit prompt (engine/nsfw_benchmark_prompt.txt) with that provider's most-permissive safety
config (engine/safety_matrix.json), N=3 renders, classify each with fal-ai/x-ailab/nsfw PLUS a
blank/refusal detector, grade per rubric bands, and write an evidence row to
engine/nsfw_capability.json (v2). Re-runnable + resumable (skips models that already have evidence
unless --recheck). Excluded-by-rule models (engine/nsfw_exclusions.json) never enter the queue.

  python scripts/nsfw_sweep.py --dry-run        # FREE: scope + spend estimate, no gens
  python scripts/nsfw_sweep.py                  # SPENDS: full sweep (est. printed first)
  python scripts/nsfw_sweep.py --providers fal,together   # limit providers
  python scripts/nsfw_sweep.py --recheck        # re-test already-evidenced models
"""
import argparse
import hashlib
import io
import json
import re
import statistics
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import config as engine_config  # noqa: E402

PROMPT = (ROOT / "engine" / "nsfw_benchmark_prompt.txt").read_text(encoding="utf-8").strip()
PROMPT_SHA = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
SAFETY = json.loads((ROOT / "engine" / "safety_matrix.json").read_text(encoding="utf-8"))
EXCL = json.loads((ROOT / "engine" / "nsfw_exclusions.json").read_text(encoding="utf-8"))["exclusions"]
OUT = ROOT / "engine" / "nsfw_capability.json"
CLASSIFIER = "fal-ai/x-ailab/nsfw"
N_RENDERS = 3
# rough per-image price for the estimate (real mix varies; premium FLUX/kontext cost more)
EST_PRICE = 0.012
PROVIDER_PROMPT_LIMIT = {"novita": 1024}  # providers that clamp the prompt (recorded per row)


def is_excluded(model_id: str):
    for e in EXCL:
        if re.search(e["id_pattern"], model_id, re.I):
            return e["reason"]
    return None


def _find_url(o):
    if isinstance(o, str) and o.startswith("http"):
        return o
    if isinstance(o, dict):
        if isinstance(o.get("url"), str):
            return o["url"]
        for k in ("images", "image", "data", "output", "outputs"):
            u = _find_url(o.get(k))
            if u:
                return u
    if isinstance(o, list):
        for it in o:
            u = _find_url(it)
            if u:
                return u
    return None


def fal_permissive(model: dict) -> dict:
    """fal is per-model: read its schema for the safety knobs it actually exposes (AC-2.2)."""
    names = {p["name"] for p in model.get("params", [])}
    out = {}
    if "enable_safety_checker" in names:
        out["enable_safety_checker"] = False
    if "enable_output_safety_checker" in names:
        out["enable_output_safety_checker"] = False
    if "safety_tolerance" in names:
        tol = next((p for p in model["params"] if p["name"] == "safety_tolerance"), {})
        vals = [str(v) for v in (tol.get("values") or ["6"])]
        out["safety_tolerance"] = max(vals, key=lambda s: int(s)) if vals else "6"
    if "image_size" in names:
        out["image_size"] = "square"
    return out


def build_scope(providers):
    """Return [{provider, id, params_hint}] — every reachable, non-excluded model to test."""
    import bridge
    api = bridge.Api.__new__(bridge.Api)
    api.config = engine_config.load()
    try:
        engine_config.resolve_keys(api.config)
    except Exception:
        pass
    scope, skipped = [], []

    def add(provider, mid, hint=None):
        if not mid:
            return
        reason = is_excluded(mid)
        if reason:
            skipped.append({"provider": provider, "id": mid, "reason": reason})
        else:
            scope.append({"provider": provider, "id": mid, "params_hint": hint or {}})

    if "fal" in providers:
        # fal scope = the "viewable" snapshot (Spec B AC-2.5), re-tested on PRIME's real prompt —
        # NOT the full 179-model t2i catalog. Schema looked up for permissive_params.
        cat = {m["id"]: m for m in json.loads((ROOT / "engine" / "fal_models.json").read_text(encoding="utf-8"))["models"]}
        snap = json.loads((ROOT / "engine" / "fal_viewable_snapshot.json").read_text(encoding="utf-8"))["models"]
        for mid in snap:
            add("fal", mid, {"model": cat.get(mid, {"id": mid, "params": []})})
    if "together" in providers:
        for mid in (api.provider_models("together", 300).get("models") or []):
            add("together", mid)
    if "agnes" in providers:
        for mid in (api.provider_models("agnes", 300).get("models") or []):
            add("agnes", mid)
    if "novita" in providers:
        for mid in (api.novita_models(100) or []):   # 100 = Novita's page cap (200 returns empty)
            add("novita", mid)
    return scope, skipped, api


def classify_url(url: str):
    """Two signals on one render: (a) fal NSFW classifier bool, (b) blank/refusal detector.
    Returns (nsfw_bool, blocked_bool, note)."""
    import fal_client
    import requests
    from PIL import Image
    nsfw = False
    try:
        cl = fal_client.subscribe(CLASSIFIER, arguments={"image_urls": [url]}, with_logs=False)
        flags = cl.get("has_nsfw_concepts") or []
        nsfw = bool(flags and flags[0])
    except Exception as e:
        return None, None, f"classify-err:{type(e).__name__}"
    blocked = False
    try:
        raw = requests.get(url, timeout=120).content
        im = Image.open(io.BytesIO(raw)).convert("L")
        lo, hi = im.getextrema()          # mode "L" → (min, max) ints
        # near-uniform frame (tonal range tiny) → blank/placeholder/refusal card, not a real render
        if (hi - lo) < 12:
            blocked = True
    except Exception:
        pass
    return nsfw, blocked, ""


def generate_url(provider, mid, params_hint, seed):
    """One render → an image URL (or None). fal via fal_client; others via the app's BACKENDS."""
    plimit = PROVIDER_PROMPT_LIMIT.get(provider)
    prompt = PROMPT[:plimit] if plimit else PROMPT
    if provider == "fal":
        import fal_client
        args = {"prompt": prompt, "seed": seed, **fal_permissive(params_hint.get("model", {}))}
        res = fal_client.subscribe(mid, arguments=args, with_logs=False)
        return _find_url(res), len(prompt)
    from engine.backends import BACKENDS
    fn = BACKENDS.get(provider)
    if not fn:
        return None, len(prompt)
    safety = {k: v for k, v in SAFETY.get(provider, {}).items() if not k.startswith("_")}
    res = fn(mid, {"prompt": prompt, "seed": seed, "num_outputs": 1, **safety}, None, None)
    return _find_url(res), len(prompt)


def grade(votes, blocks):
    """Rubric bands (AC-2.4). votes/blocks are lists of bool over N renders (None = errored)."""
    v = [x for x in votes if x is not None]
    b = [x for x in blocks if x is not None]
    if not v:
        return "unclear", 0
    nsfw_n = sum(1 for x in v if x)
    block_n = sum(1 for x in b if x)
    if block_n >= 2 and nsfw_n < 2:
        return "refused", nsfw_n
    if nsfw_n >= 2:
        return "verified", nsfw_n
    if nsfw_n == 0:
        return "sfw", 0
    return "unclear", nsfw_n


def test_model(item):
    provider, mid = item["provider"], item["id"]
    votes, blocks, urls, clamped = [], [], [], len(PROMPT)
    for i in range(N_RENDERS):
        seed = 100000 + i
        try:
            url, clamped = generate_url(provider, mid, item.get("params_hint", {}), seed)
        except Exception as e:
            votes.append(None); blocks.append(None)
            urls.append(f"gen-err:{type(e).__name__}:{str(e)[:80]}")
            continue
        if not url:
            votes.append(None); blocks.append(None); urls.append("no-url")
            continue
        nsfw, blocked, note = classify_url(url)
        votes.append(nsfw); blocks.append(blocked); urls.append(url)
    g, nsfw_n = grade(votes, blocks)
    vv = [1 if x else 0 for x in votes if x is not None]
    return {
        "provider": provider, "model": mid, "grade": g,
        "nsfw_votes": f"{nsfw_n}/{N_RENDERS}",
        "mean": round(statistics.mean(vv), 3) if vv else None,
        "sd": round(statistics.pstdev(vv), 3) if len(vv) > 1 else 0,
        "classifier": CLASSIFIER, "classifier_scores": votes, "blocked_scores": blocks,
        "seed_base": 100000, "sent_prompt_sha256": PROMPT_SHA,
        "clamped_len": clamped, "truncated": clamped < len(PROMPT),
        "sample_urls": [u for u in urls if isinstance(u, str) and u.startswith("http")][:1],
        "tested_at": time.strftime("%Y-%m-%d %H:%M"),
    }


def load_existing():
    if OUT.exists():
        try:
            d = json.loads(OUT.read_text(encoding="utf-8"))
            return d.get("models", {}) if d.get("version") == 2 else {}
        except Exception:
            return {}
    return {}


def save(models, skipped):
    OUT.write_text(json.dumps({
        "version": 2, "classifier": CLASSIFIER, "prompt_sha256": PROMPT_SHA,
        "n_renders": N_RENDERS, "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "excluded": skipped, "models": models,
    }, indent=1, default=str), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recheck", action="store_true")
    ap.add_argument("--providers", default="fal,together,agnes,novita")
    ap.add_argument("--limit", type=int, default=0, help="cap models tested (smoke); 0 = all")
    args = ap.parse_args()
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]

    scope, skipped, api = build_scope(providers)
    existing = {} if args.recheck else load_existing()
    todo = [it for it in scope if f"{it['provider']}:{it['id']}" not in existing]
    if args.limit:
        todo = todo[:args.limit]

    print(f"prompt: {len(PROMPT)} runes  sha256={PROMPT_SHA[:16]}")
    by_prov = {}
    for it in todo:
        by_prov[it["provider"]] = by_prov.get(it["provider"], 0) + 1
    print(f"in scope (to test): {len(todo)}  {dict(by_prov)}")
    print(f"excluded by rule: {len(skipped)}")
    est = len(todo) * N_RENDERS * (EST_PRICE + 0.001)
    print(f"SPEND ESTIMATE: {len(todo)} models × {N_RENDERS} renders ≈ {len(todo) * N_RENDERS} gens "
          f"≈ ${est:.2f} (+classifier)")
    if args.dry_run:
        print("\n--dry-run: no gens. Re-run without --dry-run to SPEND.")
        return 0

    models = dict(existing)
    t0 = time.time()
    # PARALLEL lane (2026-07-21): models are independent API calls → run 6 workers. Writes to the
    # shared evidence dict + the incremental save go through a lock; everything else is pure I/O.
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    lock = threading.Lock()
    done_n = [0]

    def _run_one(it):
        key = f"{it['provider']}:{it['id']}"
        try:
            r = test_model(it)
        except Exception as e:
            r = {"provider": it["provider"], "model": it["id"], "grade": "unclear",
                 "reason": str(e)[:120], "tested_at": time.strftime("%Y-%m-%d %H:%M")}
        with lock:
            models[key] = r
            done_n[0] += 1
            n = done_n[0]
            if n % 5 == 0 or n == len(todo):
                save(models, skipped)  # incremental persistence → resumable + partial results survive
        print(f"[{n}/{len(todo)}] {key}: {r['grade']} {r.get('nsfw_votes','')}", flush=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_run_one, it) for it in todo]
        for f in as_completed(futures):
            f.result()
    save(models, skipped)
    from collections import Counter
    print(f"\ndone in {time.time()-t0:.0f}s: {dict(Counter(v.get('grade') for v in models.values()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
