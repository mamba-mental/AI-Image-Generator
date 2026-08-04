"""Recover the full Replicate legacy-predictions history — prompts, params, LoRAs, models,
and output images — that the public API no longer returns (API is retention-gutted to ~1 record).

The ONLY live source is the authenticated web page:
  https://replicate.com/predictions-legacy?start=<ISO>&page=<N>
Each list page = 100 rows (ID · Model · Status · Date). Each row's detail page /p/<id> carries
the FULL input JSON (prompt + every param + lora_weights, exactly as used) + a live output image.

Auth: needs your logged-in replicate.com cookie (the session is httpOnly, so a browser can't hand
it over — copy it once from DevTools). Provide it via either:
  * env  REPLICATE_COOKIE="key=val; key2=val2"
  * file scripts/.replicate_cookie   (one line, the whole Cookie header; gitignored)

MODES
  probe : fetch page 1 + ONE detail page, print exactly what got parsed. VALIDATE before bulk.
            python scripts/replicate_legacy_scrape.py --probe
  list  : walk every page until empty, write scripts/.replicate_recover/ids.json (id + row meta).
            python scripts/replicate_legacy_scrape.py --list
  full  : list (if needed) -> fetch each /p/<id> -> parse input JSON + image URLs -> download
          images -> append to manifest.json. RESUME-SAFE (skips ids already in the manifest).
            python scripts/replicate_legacy_scrape.py --full
            python scripts/replicate_legacy_scrape.py --full --limit 50   # smoke a slice first

Everything lands in scripts/.replicate_recover/ :
  ids.json        [{id, model, source, status, created}, ...]
  manifest.json   [{id, url, model, version, created, input{...}, prompt, output_urls[], images[]}]
  images/<id>/*   downloaded output files

No spend. Read-only against your own account. Polite fixed delay between requests.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "scripts" / ".replicate_recover"
IMG_DIR = OUT / "images"
IDS_FILE = OUT / "ids.json"
MANIFEST = OUT / "manifest.json"
COOKIE_FILE = REPO / "scripts" / ".replicate_cookie"

BASE = "https://replicate.com/predictions-legacy?start=2023-01-01T05:17&page={}"
DETAIL = "https://replicate.com/p/{}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
DELAY = 0.6          # seconds between requests (polite; avoids throttling)
MAX_PAGES = 500      # hard backstop; real end is detected by an empty page


def get_cookie() -> str:
    c = os.environ.get("REPLICATE_COOKIE", "").strip()
    if c:
        return c
    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    sys.exit(
        "NO COOKIE. Copy your logged-in replicate.com Cookie header into "
        f"{COOKIE_FILE}\n(DevTools -> Application -> Cookies -> replicate.com, or Network tab -> "
        "any request -> Request Headers -> Cookie), or set REPLICATE_COOKIE."
    )


def fetch(url: str, cookie: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": cookie,
                                               "Accept": "text/html,application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


# ── list page: 100 rows, each <tr> links to /p/<id> ───────────────────────────
_ROW_ID = re.compile(r'href="/p/([a-z0-9]+)"', re.I)
_ROW_BLOCK = re.compile(r"<tr\b[\s\S]*?</tr>", re.I)
_MODEL = re.compile(r"([a-z0-9\-]+/[a-z0-9\-.]+)", re.I)
_CELLTEXT = re.compile(r"<t[dh]\b[^>]*>([\s\S]*?)</t[dh]>", re.I)


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).replace("&amp;", "&").strip()


def parse_list_page(html: str) -> list[dict]:
    rows = []
    for block in _ROW_BLOCK.findall(html):
        m = _ROW_ID.search(block)
        if not m:
            continue
        pid = m.group(1)
        cells = [_strip(c) for c in _CELLTEXT.findall(block)]
        joined = " | ".join(cells)
        model = ""
        mm = _MODEL.search(joined)
        if mm:
            model = mm.group(1)
        source = "Web" if " Web " in f" {joined} " else ("API" if " API " in f" {joined} " else "")
        status = next((c for c in cells if c in ("Succeeded", "Failed", "Canceled", "Processing")), "")
        created = next((c for c in cells if re.search(r"ago$", c)), "")
        rows.append({"id": pid, "model": model, "source": source,
                     "status": status, "created": created})
    return rows


# ── detail page: the input JSON lives in a <pre>; images are replicate.delivery URLs ──
_PRE = re.compile(r"<pre\b[^>]*>([\s\S]*?)</pre>", re.I)
_IMG_URL = re.compile(r'https://[^"\'\s)]*?(?:replicate\.delivery|pbxt)[^"\'\s)]*', re.I)
_TITLE = re.compile(r"<title>([\s\S]*?)</title>", re.I)
_VERSION = re.compile(r'"version"\s*:\s*"([a-f0-9]{16,})"', re.I)


def _html_unescape(s: str) -> str:
    return (s.replace("&quot;", '"').replace("&#34;", '"').replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))


def parse_detail(pid: str, html: str) -> dict:
    inp: dict = {}
    # find the <pre> block that parses as JSON and contains input params
    for raw in _PRE.findall(html):
        txt = _html_unescape(_strip_tags_keep(raw)).strip()
        if not txt.startswith("{"):
            continue
        try:
            obj = json.loads(txt)
        except Exception:
            continue
        if isinstance(obj, dict) and ("prompt" in obj or "aspect_ratio" in obj or "lora_weights" in obj):
            inp = obj
            break
    # output images (public CDN; dedup, keep order)
    seen, imgs = set(), []
    for u in _IMG_URL.findall(html):
        u = _html_unescape(u)
        if u not in seen:
            seen.add(u)
            imgs.append(u)
    # model from <title> "@user's owner/model | Replicate"
    model = ""
    tm = _TITLE.search(html)
    if tm:
        mm = _MODEL.search(_html_unescape(tm.group(1)))
        if mm:
            model = mm.group(1)
    vm = _VERSION.search(html)
    return {
        "id": pid, "url": DETAIL.format(pid), "model": model,
        "version": vm.group(1) if vm else "",
        "prompt": inp.get("prompt", "") if isinstance(inp, dict) else "",
        "input": inp, "output_urls": imgs,
    }


def _strip_tags_keep(html: str) -> str:
    # <pre> may contain nested <span> syntax-highlight tags; drop tags, keep text
    return re.sub(r"<[^>]+>", "", html)


# ── image download (public CDN, no cookie) ────────────────────────────────────
def download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    ! image failed {url[:60]} ({type(e).__name__})")
        return False


def _ext(url: str) -> str:
    m = re.search(r"\.(png|jpg|jpeg|webp|gif)(?:\?|$)", url, re.I)
    return "." + m.group(1).lower() if m else ".png"


def load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


# ── modes ─────────────────────────────────────────────────────────────────────
def mode_probe(cookie: str) -> int:
    print("── PROBE · page 1 + 1 detail (no downloads) ──")
    rows = parse_list_page(fetch(BASE.format(1), cookie))
    print(f"page 1 rows parsed : {len(rows)}")
    if not rows:
        print("!! 0 rows — cookie likely invalid/expired (got a login page).")
        return 1
    for r in rows[:3]:
        print(f"  {r['id']}  {r['model']:30s} {r['source']:4s} {r['status']:10s} {r['created']}")
    pid = rows[1]["id"] if len(rows) > 1 else rows[0]["id"]
    time.sleep(DELAY)
    d = parse_detail(pid, fetch(DETAIL.format(pid), cookie))
    print(f"\ndetail {pid}:")
    print(f"  model        : {d['model']}")
    print(f"  version      : {d['version'] or '(none)'}")
    print(f"  prompt       : {str(d['prompt'])[:100]}")
    print(f"  input keys   : {sorted(d['input'].keys()) if isinstance(d['input'], dict) else '?'}")
    print(f"  output_urls  : {len(d['output_urls'])}  {d['output_urls'][0][:70] if d['output_urls'] else ''}")
    ok = bool(d["input"]) and bool(d["output_urls"])
    print("\nPARSE OK — safe to run --full" if ok else
          "\n!! parse incomplete — input or image URL not found; adjust selectors before bulk.")
    return 0 if ok else 2


def mode_list(cookie: str) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        rows = parse_list_page(fetch(BASE.format(page), cookie))
        if not rows:
            print(f"page {page}: 0 rows — end of history.")
            break
        all_rows.extend(rows)
        print(f"page {page}: {len(rows)} rows (total {len(all_rows)})")
        time.sleep(DELAY)
    # dedup by id, keep first
    seen, uniq = set(), []
    for r in all_rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    IDS_FILE.write_text(json.dumps(uniq, indent=1), encoding="utf-8")
    print(f"\n{len(uniq)} unique predictions -> {IDS_FILE}")
    return uniq


def mode_full(cookie: str, limit: int) -> int:
    ids = load_json(IDS_FILE, None)
    if not ids:
        ids = mode_list(cookie)
    manifest = load_json(MANIFEST, [])
    done = {m["id"] for m in manifest}
    todo = [r for r in ids if r["id"] not in done]
    if limit:
        todo = todo[:limit]
    print(f"\n{len(todo)} to fetch ({len(done)} already in manifest, {len(ids)} total)")
    for i, row in enumerate(todo, 1):
        pid = row["id"]
        try:
            d = parse_detail(pid, fetch(DETAIL.format(pid), cookie))
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(todo)}] {pid} FETCH FAIL {type(e).__name__} — skip")
            time.sleep(DELAY)
            continue
        d["created"] = row.get("created", "")
        d["source"] = row.get("source", "")
        if not d["model"]:
            d["model"] = row.get("model", "")
        # download images
        files = []
        for n, u in enumerate(d["output_urls"]):
            # Prefix the prediction id so basenames are UNIQUE across every subfolder — the omni-image
            # library de-dupes tiles by basename, so bare `0.png`/`1.png` per-folder collapse the
            # whole archive to a handful of tiles (see rename_recover_unique.py for the historical fix).
            dest = IMG_DIR / pid / f"{pid}_{n}{_ext(u)}"
            if dest.exists() or download(u, dest):
                files.append(str(dest.relative_to(OUT)))
        d["images"] = files
        manifest.append(d)
        if i % 20 == 0 or i == len(todo):        # checkpoint the manifest periodically
            MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(f"[{i}/{len(todo)}] {pid} {d['model'][:28]:28s} imgs {len(files)} "
              f"prompt {str(d['prompt'])[:40]!r}")
        time.sleep(DELAY)
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\nDONE · manifest {len(manifest)} records -> {MANIFEST}\n     · images under {IMG_DIR}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover Replicate legacy-predictions history (read-only).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true", help="validate parsing on 1 page + 1 detail")
    g.add_argument("--list", action="store_true", help="walk all pages -> ids.json")
    g.add_argument("--full", action="store_true", help="scrape details + download images -> manifest.json")
    ap.add_argument("--limit", type=int, default=0, help="cap records in --full (smoke a slice)")
    args = ap.parse_args()
    cookie = get_cookie()
    if args.probe:
        return mode_probe(cookie)
    if args.list:
        mode_list(cookie)
        return 0
    return mode_full(cookie, args.limit)


if __name__ == "__main__":
    sys.exit(main())
