"""Acceptance verifier for R3 #4 — Settings > Tags panel (list/rename=merge/delete + "add a tag +
rescan"). Hermetic (mktemp fixtures, mocked urlopen — no NAS, no real network). Same executable
style as verify_tags.py. Run: python .dd/verify_tag_management.py"""
import json
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bridge  # noqa: E402
from engine import library_index as LI, vision_tagging as VT  # noqa: E402
from PIL import Image  # noqa: E402

checks = []


def chk(n, ok, d=""):
    checks.append(bool(ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


tmp = Path(tempfile.mkdtemp(prefix="voidtagmgmt_"))
folder_a = tmp / "gen_a"; folder_a.mkdir()
folder_b = tmp / "gen_b"; folder_b.mkdir()


def make_png(folder: Path, name: str) -> Path:
    p = folder / name
    Image.new("RGB", (8, 8), (10, 20, 30)).save(p)
    return p


idx = LI.LibraryIndex(str(tmp / "library.db"))
img1 = make_png(folder_a, "a.png")
img2 = make_png(folder_a, "b.png")
img3 = make_png(folder_a, "c.png")
idx.index_folder(str(folder_a))
idx.add_tag(str(img1), "Red")
idx.add_tag(str(img1), "beach")
idx.add_tag(str(img2), " red ")   # AC-8.1-style normalization: "Red" / " red " -> same tag
idx.add_tag(str(img3), "forest")

# ---- all_tags: counts correct, normalized, sorted by frequency then name ----
tags = idx.all_tags()
by_name = {t["tag"]: t["count"] for t in tags}
chk("4.1 all_tags normalizes case/whitespace into one tag", by_name.get("red") == 2, by_name)
chk("4.2 all_tags counts are correct per-tag", by_name.get("beach") == 1 and by_name.get("forest") == 1, by_name)
# index_folder also lands auto-tags (AC-8.1, e.g. the "YYYY-MM" date tag on every image) —
# don't assume "red" is the top tag, just assert the list is ACTUALLY sorted by count desc / name asc.
names_and_counts = [(t["tag"], t["count"]) for t in tags]
sorted_correctly = names_and_counts == sorted(names_and_counts, key=lambda x: (-x[1], x[0]))
chk("4.3 all_tags sorted by frequency desc then name", sorted_correctly, names_and_counts)

# ---- rename_tag: plain rename + MERGE (rename into an existing tag) ----
touched = idx.rename_tag("beach", "coast")
chk("4.4 rename_tag: plain rename touches exactly 1 row", touched == 1, touched)
chk("4.5 rename_tag: old name gone, new name present on that image",
    "coast" in idx.get_tags(str(img1)) and "beach" not in idx.get_tags(str(img1)))
touched_merge = idx.rename_tag("coast", "red")   # img1 now has BOTH coast+red -> merges into just "red"
chk("4.6 rename_tag MERGE: renaming into an existing tag collapses to one (no duplicate)",
    idx.get_tags(str(img1)).count("red") == 1 and "coast" not in idx.get_tags(str(img1)),
    idx.get_tags(str(img1)))
chk("4.7 rename_tag no-op on an unused tag name touches 0 rows", idx.rename_tag("nonexistent", "x") == 0)

# ---- delete_tag ----
del_touched = idx.delete_tag("red")
chk("4.8 delete_tag removes it from every carrying image", del_touched == 2, del_touched)
chk("4.9 delete_tag: image no longer carries it, other tags untouched",
    "red" not in idx.get_tags(str(img1)) and "forest" in idx.get_tags(str(img3)))

# ---- all_image_paths: NOT de-duped by basename (unlike list_images, which IS for display) ----
dup1 = make_png(folder_a, "dup.png")
dup2 = make_png(folder_b, "dup.png")   # same basename, different folder
idx.index_folder(str(folder_a))
idx.index_folder(str(folder_b))
paths = idx.all_image_paths([str(folder_a), str(folder_b)])
chk("4.10 all_image_paths returns BOTH same-named files across folders (rescan needs every real file)",
    str(dup1) in paths and str(dup2) in paths, len(paths))
display = idx.list_images([str(folder_a), str(folder_b)])
dup_in_display = sum(1 for r in display if r["file"] == "dup.png")
chk("4.11 confirms list_images DOES de-dupe by basename (contrast case for 4.10)", dup_in_display == 1, dup_in_display)

# ---- vision_tagging.tag_matches: targeted yes/no classification, mocked endpoint ----
import os
os.environ["VISION_TAG_BASE_URL"] = "http://192.168.86.191:8317/v1"
os.environ["VISION_TAG_API_KEY"] = "test-key-not-real"
captured = {}


class _FakeResp:
    def __init__(self, data):
        self._data = data
    def read(self):
        return self._data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _fake_urlopen_yes(req, timeout=None):
    captured["url"] = req.full_url
    captured["body"] = json.loads(req.data)
    body = json.dumps({"choices": [{"message": {"content": "yes"}}]}).encode()
    return _FakeResp(body)


def _fake_urlopen_no(req, timeout=None):
    body = json.dumps({"choices": [{"message": {"content": "No."}}]}).encode()
    return _FakeResp(body)


_orig_urlopen = VT.urllib.request.urlopen
VT.urllib.request.urlopen = _fake_urlopen_yes
try:
    result = VT.tag_matches(str(img2), "beach")
    chk("4.12 tag_matches parses a 'yes' response as True", result is True, result)
    chk("4.13 tag_matches sends the targeted concept in the prompt",
        "beach" in json.dumps(captured.get("body", {})), captured.get("body"))
finally:
    VT.urllib.request.urlopen = _orig_urlopen

VT.urllib.request.urlopen = _fake_urlopen_no
try:
    result2 = VT.tag_matches(str(img2), "beach")
    chk("4.14 tag_matches parses a 'no' response as False", result2 is False, result2)
finally:
    VT.urllib.request.urlopen = _orig_urlopen

# ---- parallel_rescan_tag: 12-worker batch, only 'yes' results get the tag applied ----
scan_folder = tmp / "scan"; scan_folder.mkdir()
scan_imgs = [make_png(scan_folder, f"s{i}.png") for i in range(6)]
idx.index_folder(str(scan_folder))
yes_set = {str(scan_imgs[0]), str(scan_imgs[2]), str(scan_imgs[4])}


def _fake_matches(path, tag):
    if path in yes_set:
        return True
    if path == str(scan_imgs[5]):
        return None   # simulate a timeout/failure
    return False


_orig_tag_matches = VT.tag_matches
VT.tag_matches = _fake_matches
progress_calls = []
try:
    result = VT.parallel_rescan_tag([str(p) for p in scan_imgs], "sunny", idx, max_workers=4,
                                     on_progress=lambda d, t: progress_calls.append((d, t)))
    chk("4.15 parallel_rescan_tag: correct matched/no_match/failed counts",
        result == {"matched": 3, "no_match": 2, "failed": 1}, result)
    applied = {str(p) for p in scan_imgs if "sunny" in idx.get_tags(str(p))}
    chk("4.16 parallel_rescan_tag: tag applied ONLY to the yes-matches", applied == yes_set, applied)
    chk("4.17 parallel_rescan_tag: a 'no'/failure never gets the tag",
        "sunny" not in idx.get_tags(str(scan_imgs[1])) and "sunny" not in idx.get_tags(str(scan_imgs[5])))
    chk("4.18 parallel_rescan_tag: on_progress fired once per image", len(progress_calls) == 6, len(progress_calls))
finally:
    VT.tag_matches = _orig_tag_matches

# ---- bridge wiring smoke: list_all_tags / rename_tag / delete_tag / start_tag_rescan / status ----
api = bridge.Api.__new__(bridge.Api)
api.config = {"output_directory": str(folder_a), "library_directories": [str(folder_a)]}
api._library_index_path = lambda: str(tmp / "index.json")
api._persist = lambda: None
api._lib_idx = idx   # reuse the same in-memory-backed instance so bridge sees our fixtures

r = api.list_all_tags()
chk("bridge list_all_tags reaches the index", isinstance(r, list) and any(t["tag"] == "forest" for t in r), r)
r2 = api.rename_tag("forest", "woods")
chk("bridge rename_tag round-trips", r2.get("ok") and r2.get("touched") == 1, r2)
r3 = api.delete_tag("woods")
chk("bridge delete_tag round-trips", r3.get("ok") and r3.get("touched") == 1, r3)

# off-by-default gate: start_tag_rescan refuses cleanly when vision isn't configured
_was_key = os.environ.pop("VISION_TAG_API_KEY", None)
os.environ.pop("CLIPROXY_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
r4 = api.start_tag_rescan("sunset")
chk("bridge start_tag_rescan: off-by-default gate (AC-8.7 philosophy) refuses without a vision endpoint",
    r4.get("ok") is False and "vision endpoint" in (r4.get("error") or ""), r4)
if _was_key is not None:
    os.environ["VISION_TAG_API_KEY"] = _was_key

r5 = api.rescan_tag_status()
chk("bridge rescan_tag_status: safe default when nothing has ever run", r5.get("running") is False, r5)

idx.close()
print(f"\n{'ALL PASS' if all(checks) else 'FAILED ' + str(checks.count(False))} ({sum(checks)}/{len(checks)})")
sys.exit(0 if all(checks) else 1)
