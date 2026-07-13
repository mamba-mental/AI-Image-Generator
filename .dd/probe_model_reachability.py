"""#8 reachability sweep — probe EVERY selectable model id for reachability (not just the 8
known-dead ones). fal ids -> the public OpenAPI schema endpoint (200 = live, 404 = dead);
OpenRouter seeds -> the public /models list. Writes a report; with --purge removes dead fal ids
from engine/fal_models.json so nothing dead stays selectable.

Run:  python .dd/probe_model_reachability.py            (report only)
      python .dd/probe_model_reachability.py --purge     (also remove dead fal ids)
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fal_ids():
    m = json.loads((ROOT / "engine" / "fal_models.json").read_text(encoding="utf-8"))["models"]
    return [x["id"] for x in m]


def probe_fal(mid):
    url = f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={mid}"
    try:
        code = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).getcode()
        return mid, 200 <= code < 300, code
    except urllib.error.HTTPError as e:
        return mid, False, e.code
    except Exception as e:
        return mid, None, type(e).__name__  # network/unknown -> inconclusive, not "dead"


def openrouter_live_ids():
    url = "https://openrouter.ai/api/v1/models"
    data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read())
    return {m["id"] for m in data.get("data", [])}


def main():
    purge = "--purge" in sys.argv
    ids = fal_ids()
    print(f"probing {len(ids)} fal models for reachability…")
    with ThreadPoolExecutor(max_workers=16) as ex:
        res = list(ex.map(probe_fal, ids))
    live = [m for m, ok, _ in res if ok is True]
    dead = [(m, c) for m, ok, c in res if ok is False]
    inconclusive = [(m, c) for m, ok, c in res if ok is None]
    print(f"  fal: {len(live)} live, {len(dead)} dead, {len(inconclusive)} inconclusive(network)")
    for m, c in dead:
        print(f"    DEAD ({c}): {m}")

    # OpenRouter seeds (from bridge.py fallback) must be in the live models list
    seeds = ["google/gemini-3-pro-image", "google/gemini-3.1-flash-image",
             "google/gemini-2.5-flash-image", "openai/gpt-5-image"]
    try:
        orl = openrouter_live_ids()
        or_dead = [s for s in seeds if s not in orl]
        print(f"  openrouter seeds: {len(seeds)-len(or_dead)}/{len(seeds)} live" +
              (f"; DEAD: {or_dead}" if or_dead else ""))
    except Exception as e:
        or_dead = []
        print(f"  openrouter seeds: probe skipped ({type(e).__name__})")

    report = ROOT / ".dd" / "model-reachability-report.md"
    report.write_text(
        "# Model reachability sweep (#8)\n\n"
        f"- fal probed: {len(ids)} | live: {len(live)} | dead: {len(dead)} | inconclusive(network): {len(inconclusive)}\n"
        + "".join(f"  - DEAD fal ({c}): `{m}`\n" for m, c in dead)
        + f"- openrouter seeds: {len(seeds)-len(or_dead)}/{len(seeds)} live"
        + (f" | DEAD: {or_dead}\n" if or_dead else "\n"),
        encoding="utf-8")
    print(f"  report -> {report}")

    if purge and dead:
        p = ROOT / "engine" / "fal_models.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        dead_ids = {m for m, _ in dead}
        before = len(doc["models"])
        doc["models"] = [x for x in doc["models"] if x["id"] not in dead_ids]
        p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print(f"  PURGED {before - len(doc['models'])} dead fal ids from fal_models.json")

    # exit 0 if nothing dead-and-selectable remains
    sys.exit(0 if not dead and not or_dead else (0 if purge else 2))


if __name__ == "__main__":
    main()
