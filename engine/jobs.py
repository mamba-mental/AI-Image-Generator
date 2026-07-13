"""Job registry: one generation job at a time, daemon worker threads, cooperative
cancel, progress pushed to the UI via window.evaluate_js -> window.onEngineEvent(evt).
"""
import json
import threading
import traceback
import uuid

from . import history, keypool, logbuf, save
from .backends import BACKENDS

_RATE_LIMIT_MARKERS = ("401", "403", "429", "rate limit", "rate-limit",
                       "quota", "exhaust", "insufficient", "too many requests")


def _looks_rate_limited(results) -> bool:
    """A single error-string result that reads like an auth/rate-limit failure (#13 auto-swap trigger)."""
    if len(results) == 1 and isinstance(results[0], str) and "Error" in results[0]:
        low = results[0].lower()
        return any(m in low for m in _RATE_LIMIT_MARKERS)
    return False


class JobRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = None          # {"id", "cancel": Event, "thread": Thread}
        self._window = None          # pywebview window, set by the shell after creation

    def attach_window(self, window):
        self._window = window

    def emit(self, payload: dict):
        # #14 — every engine event lands in the searchable ring buffer
        try:
            lvl = "error" if payload.get("type") == "job_error" else "info"
            msg = payload.get("message") or payload.get("error") or payload.get("type", "")
            logbuf.append(lvl, payload.get("type", ""), msg, payload.get("detail", ""))
        except Exception:
            pass
        if self._window is not None:
            try:
                self._window.evaluate_js(f"window.onEngineEvent({json.dumps(payload)})")
            except Exception as e:
                print(f"emit failed: {e}")
        else:  # --smoke / tests: no window
            print(f"[event] {payload}")

    def is_busy(self) -> bool:
        with self._lock:
            return self._active is not None

    def start(self, service: str, model_id: str, params: dict, output_dir: str) -> dict:
        with self._lock:
            if self._active is not None:
                return {"error": "busy"}
            job_id = uuid.uuid4().hex[:12]
            cancel = threading.Event()
            thread = threading.Thread(
                target=self._run, args=(job_id, service, model_id, params, output_dir, cancel),
                daemon=True)
            self._active = {"id": job_id, "cancel": cancel, "thread": thread}
        self.emit({"type": "job_queued", "job_id": job_id, "service": service, "model": model_id})
        thread.start()
        return {"job_id": job_id}

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            if self._active and self._active["id"] == job_id:
                self._active["cancel"].set()
                return {"ok": True}
        return {"ok": False, "error": "no such active job"}

    def _finish(self):
        with self._lock:
            self._active = None

    def _run(self, job_id, service, model_id, params, output_dir, cancel):
        try:
            backend = BACKENDS.get(service)
            if backend is None:
                self.emit({"type": "job_error", "job_id": job_id,
                           "error": f"Unknown service: {service}"})
                return

            def progress(message, pct=None):
                self.emit({"type": "job_progress", "job_id": job_id,
                           "message": str(message), "pct": pct})

            # #13 — on a rate-limit/auth failure, rotate to the next pooled key and retry
            results = []
            attempts = max(1, keypool.size(service))
            for attempt in range(attempts):
                results = backend(model_id, params, progress=progress, cancel_event=cancel)
                if cancel.is_set():
                    self.emit({"type": "job_error", "job_id": job_id, "error": "Cancelled."})
                    return
                if attempt < attempts - 1 and _looks_rate_limited(results) and keypool.rotate(service):
                    progress(f"key rate-limited — switching to key {attempt + 2}/{attempts}…")
                    continue
                break

            progress("saving…")  # #15 — explicit save stage: queued -> running -> saving -> done
            paths = save.make_output_paths(output_dir, len(results))
            saved, errors = save.persist_results(results, paths)
            if saved:
                meta = {"service": service, "model": model_id,
                        "prompt": params.get("prompt", ""), "seed": params.get("seed")}
                clean_params = {k: v for k, v in params.items()
                                if k not in ("prompt", "_inputs", "image",
                                             "enabled_loras", "category")}
                history.record(output_dir, {**meta, "files": saved, "params": clean_params})
                for f in saved:  # #9: per-image sidecar mirrors history so LIBRARY view has meta too
                    save.write_sidecar(f, {**meta, "params": clean_params})
                self.emit({"type": "job_done", "job_id": job_id, "files": saved,
                           "errors": errors, "meta": meta})
            else:
                self.emit({"type": "job_error", "job_id": job_id,
                           "error": (errors[0] if errors else "No results returned.")})
        except Exception as e:
            tb = traceback.format_exc()  # #15 — full trace travels to the copyable error popup
            self.emit({"type": "job_error", "job_id": job_id, "error": str(e), "detail": tb})
        finally:
            self._finish()


REGISTRY = JobRegistry()
