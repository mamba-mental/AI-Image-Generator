"""Job registry: one generation job at a time, daemon worker threads, cooperative
cancel, progress pushed to the UI via window.evaluate_js -> window.onEngineEvent(evt).
"""
import json
import threading
import traceback
import uuid

from . import save
from .backends import BACKENDS


class JobRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._active = None          # {"id", "cancel": Event, "thread": Thread}
        self._window = None          # pywebview window, set by the shell after creation

    def attach_window(self, window):
        self._window = window

    def emit(self, payload: dict):
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

            results = backend(model_id, params, progress=progress, cancel_event=cancel)
            if cancel.is_set():
                self.emit({"type": "job_error", "job_id": job_id, "error": "Cancelled."})
                return

            paths = save.make_output_paths(output_dir, len(results))
            saved, errors = save.persist_results(results, paths)
            if saved:
                self.emit({"type": "job_done", "job_id": job_id, "files": saved,
                           "errors": errors,
                           "meta": {"service": service, "model": model_id,
                                    "prompt": params.get("prompt", ""),
                                    "seed": params.get("seed")}})
            else:
                self.emit({"type": "job_error", "job_id": job_id,
                           "error": (errors[0] if errors else "No results returned.")})
        except Exception as e:
            traceback.print_exc()
            self.emit({"type": "job_error", "job_id": job_id, "error": str(e)})
        finally:
            self._finish()


REGISTRY = JobRegistry()
