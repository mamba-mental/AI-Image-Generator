"""Tiny localhost static server for generated media.

WHY: WebView2 refuses to load file:// sub-resources (img/video/audio) from a
file:// page — generated images render as broken-link icons. Serving them over
http://127.0.0.1 fixes images, video, and audio in one mechanism (no per-file
base64 bloat). Bound to 127.0.0.1 only; serves basename-of-request from the
current output dir (plus any registered library roots), so there is no path
traversal and no exposure beyond those folders.

# ponytail: full-body 200 responses, no HTTP Range. Images/audio/short clips play
# fine; seeking inside a long video won't. Add a 206 range handler if that bites.
"""
import mimetypes
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_STATE = {"dir": None, "extra": []}  # primary output dir + extra library roots (mutable; set by the bridge)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request stderr spam
        pass

    def _serve(self, body: bool):
        roots = [_STATE["dir"], *_STATE.get("extra", [])]  # output dir first, then library archives
        if roots[0] is None:
            self.send_error(503, "media dir not set")
            return
        name = Path(urllib.parse.unquote(self.path.lstrip("/"))).name  # basename only
        target = next((Path(b) / name for b in roots if b and (Path(b) / name).is_file()), None)
        if not name or target is None:
            self.send_error(404)
            return
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(data)

    def do_GET(self):
        self._serve(body=True)

    def do_HEAD(self):
        self._serve(body=False)


def start(output_dir: str) -> str:
    """Start (once) the media server on an ephemeral port. Returns the base URL."""
    _STATE["dir"] = output_dir
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


def add_root(path: str) -> None:
    """Register an extra folder the server also serves basenames from (e.g. a captioned library
    archive). First matching root wins; archive names (UUIDs/timestamps) won't collide with output."""
    _STATE.setdefault("extra", [])
    if path and path not in _STATE["extra"]:
        _STATE["extra"].append(path)
