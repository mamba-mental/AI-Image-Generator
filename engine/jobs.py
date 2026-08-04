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
                       "quota", "exhaust", "insufficient", "too many requests",
                       "authorization failed", "unauthorized")  # hf_api's friendly wrapper
                       # drops the raw HTTP code, so "401" alone never matches an HF auth
                       # failure — without this, HF's 6-key pool never rotates on a bad key.


def _looks_rate_limited(results) -> bool:
    """A single error-string result that reads like an auth/rate-limit failure (#13 auto-swap trigger)."""
    if len(results) == 1 and isinstance(results[0], str) and "Error" in results[0]:
        low = results[0].lower()
        return any(m in low for m in _RATE_LIMIT_MARKERS)
    return False


def _is_error_result(results) -> bool:
    """A backend returned a single ['... Error: ...'] element instead of image URLs."""
    return len(results) == 1 and isinstance(results[0], str) and "Error" in results[0]


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

            # loop-N: make `_n_images` images (one backend call each) so providers with no native
            # multi-output still batch; target=1 (the default) is a single call = unchanged behavior.
            results, cancelled = self._batch_generate(service, backend, model_id, params, progress, cancel)
            if cancelled:
                self.emit({"type": "job_error", "job_id": job_id, "error": "Cancelled."})
                return

            progress("saving…")  # #15 — explicit save stage: queued -> running -> saving -> done
            paths = save.make_output_paths(output_dir, len(results), seed=params.get("seed"))
            saved, errors = save.persist_results(results, paths)
            if saved:
                meta = {"service": service, "model": model_id,
                        "prompt": params.get("prompt", ""), "seed": params.get("seed"),
                        "category": params.get("category")}  # persist genre/type for the library filter
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

    def _batch_generate(self, service, backend, model_id, params, progress, cancel):
        """Generate `_n_images` results, one backend call per image (loop-N), so Replicate models with
        no native multi-output can still make N. target=1 -> a single call, params untouched (every
        other service's native batch is unaffected). Each pass past the first varies the seed (when one
        is set) so the images differ. The existing per-call key-rotation retry (#13) is preserved.
        Returns (results, cancelled)."""
        target = max(1, min(int(params.pop("_n_images", 1) or 1), 8))
        all_results = []
        for i in range(target):
            if cancel.is_set():
                return all_results, True
            cp = dict(params)
            if target > 1:
                cp["num_outputs"] = 1                      # one per call; the loop provides the count
                sd = str(cp.get("seed") or "").strip()
                if sd and sd != "0":
                    try:
                        cp["seed"] = int(float(sd)) + i    # distinct seed -> distinct image
                    except (TypeError, ValueError):
                        pass
                progress(f"image {i + 1} of {target}…")
            # #13 — per-call key rotation on a rate-limit/auth failure
            results = []
            attempts = max(1, keypool.size(service))
            for attempt in range(attempts):
                results = backend(model_id, cp, progress=progress, cancel_event=cancel)
                if cancel.is_set():
                    return all_results, True
                if attempt < attempts - 1 and _looks_rate_limited(results) and keypool.rotate(service):
                    progress(f"key rate-limited — switching to key {attempt + 2}/{attempts}…")
                    continue
                break
            if _is_error_result(results):
                if not all_results:
                    return results, False                  # first image failed → surface the error
                progress(f"stopped at {len(all_results)}/{target}: {results[0]}")
                break                                      # partial success → keep what we have
            all_results.extend(results)
        return all_results, False


REGISTRY = JobRegistry()
