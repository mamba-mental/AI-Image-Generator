"""AI Studio Void — web-view shell entry point.

Usage:
  python main.py            # run the app
  python main.py --smoke    # open, call get_state() from JS, print JSON, exit 0
"""
import sys

import webview

from bridge import Api
from engine import config as engine_config
from engine.jobs import REGISTRY

MIN_SIZE = (1100, 720)


def _smoke(window, api):
    import json
    import threading

    def run():
        try:
            js_sees = window.evaluate_js("window.pywebview && window.pywebview.api ? 'api-present' : 'api-missing'")
            state = api.get_state()  # same object JS reaches via pywebview.api
            print("SMOKE js sees api:", js_sees)
            print("SMOKE get_state():", json.dumps(state)[:400], "...")
            # Library filter-bar DOM probe (Phase 2): renderLibrary() sync-injects the filter bar
            # + folder toggles before its async NAS crawl, so the controls exist immediately.
            lib = window.evaluate_js(
                "(function(){try{renderLibrary();return JSON.stringify({"
                "filters:!!document.querySelector('.libfilters'),q:!!document.getElementById('libq'),"
                "svc:!!document.getElementById('libsvc'),type:!!document.getElementById('libtype'),"
                "folders:!!document.getElementById('libfolders'),add:document.body.innerHTML.indexOf('libadd')>-1"
                "});}catch(e){return 'ERR: '+e.message;}})()")
            print("SMOKE library DOM:", lib)
            print("SMOKE OK")
        except Exception as e:
            print(f"SMOKE FAILED: {e}")
            sys.exit(1)
        finally:
            window.destroy()

    threading.Timer(3.0, run).start()


def main():
    smoke = "--smoke" in sys.argv
    api = Api()
    index = engine_config.resource_path("web/index.html")
    window = webview.create_window(
        engine_config.APP_NAME,
        url=str(index),
        js_api=api,
        width=1280, height=820,
        min_size=MIN_SIZE,
        background_color="#000000",
    )
    REGISTRY.attach_window(window)
    if smoke:
        webview.start(_smoke, (window, api))
    else:
        webview.start()


if __name__ == "__main__":
    main()
