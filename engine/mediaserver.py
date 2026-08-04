"""Tiny localhost static server for generated media + on-demand thumbnails.

WHY: WebView2 refuses to load file:// sub-resources (img/video/audio) from a
file:// page — generated images render as broken-link icons. Serving them over
http://127.0.0.1 fixes images, video, and audio in one mechanism. Bound to
127.0.0.1 only; serves basename-of-request from the current output dir (plus any
registered library roots), so there is no path traversal and no exposure beyond
those folders.

THUMBNAILS (added 2026-07-19): the LIBRARY grid used to load every tile at full
resolution from the NAS with `Cache-Control: no-store`, so reopening the app
re-downloaded thousands of full-size images. Now grid tiles request
`/thumb/<name>?s=NNN`, which returns a small JPEG generated once and cached on the
LOCAL disk (`.cache/thumbs/`) — subsequent opens read tiny local files, not full
NAS images. Full-res is still served (lightbox) from the original path.

# ponytail: full-body 200 responses, no HTTP Range. Add a 206 handler if long
# video seeking is needed.
"""
import mimetypes
import sqlite3
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_STATE = {"dir": None, "extra": [], "thumbs": None}  # output dir + library roots + thumb cache dir
_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_THUMB_LOCK = threading.Lock()
_FIND_CACHE: dict[str, str] = {}  # basename -> resolved absolute path (misses trigger one rglob)

# DB-backed name->path resolve (library.db has idx_images_name). Replaces the per-name recursive
# rglob for any INDEXED image — critical for nested archives like .replicate_recover/images/<id>/*
# where a filesystem walk of thousands of subdirs would otherwise run per uncached basename.
_DB_CONN = None
_DB_LOCK = threading.Lock()


def _db_conn():
    global _DB_CONN
    if _DB_CONN is None:
        db = Path(__file__).resolve().parent.parent / ".cache" / "library.db"
        if not db.is_file():
            return None
        try:
            _DB_CONN = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2, check_same_thread=False)
            _DB_CONN.execute("PRAGMA busy_timeout=2000")
        except Exception:
            _DB_CONN = None
    return _DB_CONN


def _db_resolve(name: str):
    """Resolve a basename to its absolute path via library.db (idx_images_name = index seek, no fs
    walk). Autocommit read so each query sees the latest WAL snapshot. Only trusts a row whose file
    still exists on disk. Returns Path or None."""
    con = _db_conn()
    if con is None:
        return None
    try:
        with _DB_LOCK:
            row = con.execute("SELECT path FROM images WHERE name=? LIMIT 1", (name,)).fetchone()
    except Exception:
        return None
    if row and Path(row[0]).is_file():
        return Path(row[0])
    return None


def _roots():
    return [_STATE["dir"], *_STATE.get("extra", [])]


def _find(name: str):
    """Resolve a basename to a real file under any root.

    Generations save to `<root>/generated/YYYY-MM/<file>`, so a top-level-only check 404s every
    generated image. Resolution order: (1) cache, (2) top-level of each root (fast, the common case
    for archive libraries whose files sit at the root), (3) library.db index seek on the basename
    (idx_images_name — resolves nested archive images with ZERO filesystem walk), (4) ONE recursive
    rglob per root as a last resort for names not yet indexed. After the first hit a name is a pure
    dict lookup forever.
    # ponytail: DB index seek replaces the per-name rglob for every indexed image (the .replicate_recover
    # nested archive would otherwise rglob thousands of subdirs per basename). rglob remains only for
    # un-indexed names (a fresh gen before its folder is indexed) — rare, and top-level-findable anyway.
    """
    if not name:
        return None
    cached = _FIND_CACHE.get(name)
    if cached and Path(cached).is_file():   # guard a moved/deleted cached path
        return Path(cached)
    for b in _roots():                      # fast path: top level (unchanged behavior)
        if b and (Path(b) / name).is_file():
            _FIND_CACHE[name] = str(Path(b) / name)
            return Path(b) / name
    hit = _db_resolve(name)                  # index seek (idx_images_name) — no filesystem walk
    if hit is not None:
        _FIND_CACHE[name] = str(hit)
        return hit
    for b in _roots():                      # slow path: recurse, first hit wins, cache it
        if not b:
            continue
        hit = next((p for p in Path(b).rglob(name) if p.is_file()), None)
        if hit is not None:
            _FIND_CACHE[name] = str(hit)
            return hit
    return None


def _thumb_dir() -> Path:
    d = _STATE.get("thumbs") or (Path.cwd() / ".cache" / "thumbs")
    return Path(d)


def _make_thumb(src: Path, dst: Path, size: int) -> bool:
    """Generate a downscaled JPEG thumbnail. Returns False if the source can't be imaged."""
    try:
        from PIL import Image
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((size, size))
            im.save(dst, "JPEG", quality=80)
        return True
    except Exception:
        return False


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request stderr spam
        pass

    def _send(self, data: bytes, ctype: str, cache: str, body: bool):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if body:
            self.wfile.write(data)

    def _serve_thumb(self, body: bool):
        parsed = urllib.parse.urlparse(self.path)
        name = Path(urllib.parse.unquote(parsed.path)).name  # basename only
        try:
            size = max(64, min(1024, int(urllib.parse.parse_qs(parsed.query).get("s", ["400"])[0])))
        except ValueError:
            size = 400
        src = _find(name)
        if not name or src is None:
            self.send_error(404)
            return
        if src.suffix.lower() not in _IMG_EXT:  # non-image → just serve the original
            self._serve_file(src, body)
            return
        thumb = _thumb_dir() / f"{name}.{size}.jpg"
        try:
            fresh = thumb.exists() and thumb.stat().st_mtime >= src.stat().st_mtime
        except OSError:
            fresh = False
        if not fresh:
            with _THUMB_LOCK:  # serialize generation so concurrent tiles don't collide
                if not (thumb.exists() and thumb.stat().st_mtime >= src.stat().st_mtime):
                    if not _make_thumb(src, thumb, size):
                        self._serve_file(src, body)  # fall back to full-res on failure
                        return
        self._send(thumb.read_bytes(), "image/jpeg", "public, max-age=2592000", body)

    def _serve_file(self, target: Path, body: bool):
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        # Archive/output filenames are unique & content-stable → safe to cache for a day.
        self._send(data, ctype, "max-age=86400", body)

    def _serve(self, body: bool):
        if _STATE["dir"] is None:
            self.send_error(503, "media dir not set")
            return
        if self.path.startswith("/thumb/"):
            self._serve_thumb(body)
            return
        name = Path(urllib.parse.unquote(self.path.lstrip("/"))).name  # basename only
        target = _find(name)
        if not name or target is None:
            self.send_error(404)
            return
        self._serve_file(target, body)

    def do_GET(self):
        self._serve(body=True)

    def do_HEAD(self):
        self._serve(body=False)


def start(output_dir: str) -> str:
    """Start (once) the media server on an ephemeral port. Returns the base URL."""
    _STATE["dir"] = output_dir
    if _STATE.get("thumbs") is None:
        _STATE["thumbs"] = str(Path(__file__).resolve().parent.parent / ".cache" / "thumbs")
    if _STATE.get("base"):
        return _STATE["base"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _STATE["server"] = server
    _STATE["base"] = f"http://127.0.0.1:{port}/"
    return _STATE["base"]


def set_dir(output_dir: str) -> None:
    _STATE["dir"] = output_dir
    _FIND_CACHE.clear()   # roots changed — a cached path may no longer be under a served root


def add_root(path: str) -> None:
    """Register an extra folder the server also serves basenames from (e.g. a captioned library
    archive). First matching root wins; archive names (UUIDs/timestamps) won't collide with output."""
    _STATE.setdefault("extra", [])
    if path and path not in _STATE["extra"]:
        _STATE["extra"].append(path)
        _FIND_CACHE.clear()   # a new root can change what a basename resolves to


def remove_root(path: str) -> None:
    """Stop serving from a previously-added extra root (e.g. a library folder toggled off), so a
    disabled folder stops serving without an app restart. No-op if it wasn't a registered root."""
    if path and path in _STATE.get("extra", []):
        _STATE["extra"].remove(path)
        _FIND_CACHE.clear()   # drop any entries that pointed into the removed root
