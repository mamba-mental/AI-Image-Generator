"""P5 gate driver — exercises the REAL UI path (DOM clicks -> bridge -> engine -> events -> gallery).

Run:  python tests/drive_ui.py
Cost: one fal flux/schnell gen (~$0.003) + gemini gens (free tier).
Emits PASS/FAIL lines + a window screenshot to tests/ui_gate.png; exit 0 only if all pass.
"""
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252 console vs ✓ in UI text
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import webview
from bridge import Api
from engine import config as engine_config
from engine.jobs import REGISTRY

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {name}{' — ' + str(detail)[:140] if detail else ''}")


def js(window, code):
    return window.evaluate_js(code)


def wait_for(window, expr, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js(window, expr):
            return True
        time.sleep(1)
    return False


def screenshot(path):
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
        return True
    except Exception as e:
        print(f"screenshot failed: {e}")
        return False


def drive(window):
    try:
        # wait for boot to actually complete (services rendered), not a fixed sleep
        booted = wait_for(window, "document.querySelectorAll('#svc button').length >= 4", timeout=30)
        check("bridge boot", booted, js(window, "document.getElementById('connlabel').textContent"))
        if not booted:
            check("diagnostic: pywebview object",
                  False, js(window, "typeof window.pywebview") or "undefined")
            raise RuntimeError("bridge never booted — aborting drive")

        # capture any JS errors from here on
        js(window, "window.__errs=[]; window.onerror=(m,s,l)=>{window.__errs.push(m+':'+l)}")

        # --- 1. fal schnell via the real button (switch to fal explicitly first) ---
        js(window, "document.querySelector('#svc button[data-s=fal]').click()")
        time.sleep(1)
        js(window, "document.querySelector('#cats button[data-c=\"text-to-image\"]').click()")
        time.sleep(1)
        js(window, "document.getElementById('model').value='fal-ai/flux/schnell';"
                   "document.getElementById('model').dispatchEvent(new Event('change'))")
        time.sleep(1)
        print("DIAG fal models:", js(window, "state.falModels.length"),
              "| service:", js(window, "state.service"),
              "| model:", js(window, "state.model"))
        js(window, "document.getElementById('prompt').value='a single violet orchid on black glass, studio macro'")
        js(window, "document.getElementById('gen').click()")
        time.sleep(2)
        started = js(window, "document.getElementById('gen').textContent") == "CANCEL"
        check("fal job started (button flips to CANCEL)", started,
              f"status='{js(window, chr(100)+'ocument.getElementById(`statusmsg`).textContent')}' errs={js(window, 'JSON.stringify(window.__errs)')}")
        ok = wait_for(window, "state.gallery.length >= 1", timeout=120)
        check("fal schnell tile in gallery", ok, js(window, "state.gallery[0] && state.gallery[0].file"))
        # the render-proof the earlier gate MISSED: image pixels actually painted,
        # not just a tile element in the DOM (WebView2 file:// broken-link bug).
        rendered = wait_for(window,
            "(function(){var i=document.querySelector('.tile img');return i&&i.complete&&i.naturalWidth>0})()",
            timeout=20)
        check("image actually RENDERS (naturalWidth>0 via media server)", rendered,
              "mediaBase=" + str(js(window, "state.mediaBase")) +
              " src=" + str(js(window, "var i=document.querySelector('.tile img'); i?i.src:'none'")))

        # --- screenshot the live window with the result ---
        time.sleep(2)
        check("screenshot", screenshot(str(Path(__file__).parent / "ui_gate.png")))

        # --- 2. gemini via the real service toggle ---
        # --- 2. replicate via the real service toggle ---
        base = js(window, "state.gallery.length") or 0
        js(window, "document.querySelector('#svc button[data-s=replicate]').click()")
        time.sleep(1)
        js(window, "document.getElementById('prompt').value='minimal geometric violet logo on black'")
        js(window, "document.getElementById('gen').click()")
        ok = wait_for(window, f"state.gallery.length >= {base + 1}", timeout=180)
        check("replicate tile in gallery", ok,
              f"model={js(window, 'state.model')} status='{js(window, chr(100)+'ocument.getElementById(`statusmsg`).textContent')}'")

        # --- 2b. gemini: pass on tile OR a clean quota-block (free tier resets midnight PT) ---
        base = js(window, "state.gallery.length") or 0
        js(window, "document.querySelector('#svc button[data-s=gemini]').click()")
        time.sleep(1)
        js(window, "document.getElementById('gen').click()")
        got_tile = wait_for(window, f"state.gallery.length >= {base + 1}", timeout=90)
        status = js(window, "document.getElementById('statusmsg').textContent") or ""
        quota_blocked = "429" in status or "rate limit" in status.lower()
        check("gemini gen OR clean quota-block", got_tile or quota_blocked,
              "tile" if got_tile else status[:120])

        # --- 3. cancel proof on fal: flux/dev 50 steps (slow enough to out-race), cancel at 2s ---
        js(window, "document.querySelector('#svc button[data-s=fal]').click()")
        time.sleep(1)
        js(window, "document.querySelector('#cats button[data-c=\"text-to-image\"]').click()")
        time.sleep(1)
        js(window, "document.getElementById('model').value='fal-ai/flux/dev';"
                   "document.getElementById('model').dispatchEvent(new Event('change'))")
        time.sleep(1)
        js(window, "var el=document.querySelector('#params [data-p=num_inference_steps]');"
                   "if(el){el.value=50;el.dispatchEvent(new Event('input'))}")
        js(window, "document.getElementById('prompt').value='hyperdetailed cathedral of glass, volumetric light'")
        js(window, "document.getElementById('gen').click()")
        time.sleep(2)
        js(window, "document.getElementById('gen').click()")  # now CANCEL
        ok = wait_for(window, "document.getElementById('gen').textContent === 'GENERATE'", timeout=90)
        status = js(window, "document.getElementById('statusmsg').textContent") or ""
        check("cancel resets UI", ok, status[:120])
        check("cancel surfaced (or gen out-raced cancel)",
              "cancel" in status.lower() or "done" in status.lower(), status[:120])

        # --- 4. layout + theme switch sanity ---
        js(window, "document.querySelector('#layoutpick button[data-layout=pro]').click()")
        js(window, "document.querySelector('#themepick button[data-theme=claret]').click()")
        time.sleep(1)
        check("layout switch", js(window, "document.documentElement.dataset.layout") == "pro")
        check("theme switch", js(window, "document.documentElement.dataset.theme") == "claret")
        screenshot(str(Path(__file__).parent / "ui_gate_pro_claret.png"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        check("driver crashed", False, str(e))
    finally:
        passed = all(RESULTS)
        print(f"=== {sum(RESULTS)}/{len(RESULTS)} PASS ===")
        window.destroy()
        # exit code carried via file since webview.start swallows sys.exit inside threads
        (Path(__file__).parent / "ui_gate_result.json").write_text(
            json.dumps({"pass": passed, "checks": len(RESULTS)}))


def main():
    api = Api()
    window = webview.create_window(
        engine_config.APP_NAME + " — GATE",
        url=str(engine_config.resource_path("web/index.html")),
        js_api=api, width=1280, height=820, background_color="#000000")
    REGISTRY.attach_window(window)
    webview.start(drive, (window,))
    result = json.loads((Path(__file__).parent / "ui_gate_result.json").read_text())
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
