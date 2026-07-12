#!/usr/bin/env python3
"""
AI Studio Void — web UI entry point (pywebview shell over webui/ + bridge.Api).
Direction 4 "Power-User Studio". The Tkinter app.py remains as the fallback entry.

  python app_web.py           # launch the desktop window
  python app_web.py --smoke   # construct everything headless, print SMOKE OK, exit 0
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bridge import Api


def run_smoke():
    api = Api(start_server=True, media_port=0)
    try:
        assert api.providers() == ["fal", "replicate", "hf", "gemini"]
        assert isinstance(api.models(), dict) and api.models()["fal"], "catalog empty"
        assert (ROOT / "webui" / "index.html").exists(), "webui/index.html missing"
        _ = api.gallery(limit=3)  # must not raise
        print("SMOKE OK")
        return 0
    finally:
        api.shutdown()


def run_window():
    import webview
    api = Api(start_server=True)
    index = (ROOT / "webui" / "index.html").as_uri()
    window = webview.create_window(
        "AI Studio Void", url=index, js_api=api,
        width=1440, height=960, min_size=(1100, 720), background_color="#08080d",
    )
    # Hand the window the media base so JS can resolve gallery URLs.
    def _boot():
        window.evaluate_js(f"window.__VOID_MEDIA_BASE__ = '{api._base}';")
    webview.start(_boot)
    api.shutdown()


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        sys.exit(run_smoke())
    run_window()
