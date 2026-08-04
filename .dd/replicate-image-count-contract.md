# *DD Contract: Replicate universal image count (loop-N)

Build type: Backend (job runner) + Web-frontend control · Methods: ATDD (done-gate) · SBE (worked call-count examples) · TDD (inner loop)
Stack: Python (engine/jobs.py `_batch_generate`) -> executable .dd harness with a mock backend; JS (a "# images" control) -> static harness.

## Why
No loop/count mechanism exists — the app relies on each model's NATIVE num_outputs. Replicate models
that don't expose it (qwen, flux-pro, seedream) are stuck at 1 image. Fix: a "# images" control for
Replicate + loop the backend N times in the job runner (fresh seed per pass) so N works on ANY model.

## Acceptance
- AC-1: `_batch_generate` calls the backend N times for `_n_images=N` and concatenates results. -> mock backend returns ["u{i}"] per call; N=3 -> 3 results, 3 calls. [RED]
- AC-2: each pass past the first gets a DISTINCT seed when a seed is set (so images differ). [RED]
- AC-3: while looping (target>1) each call forces `num_outputs=1` (no native N× multiply). [RED]
- AC-4: no `_n_images` / target=1 -> exactly ONE backend call, params untouched (other services unaffected). [RED]
- AC-5: first-call error -> returned as the error (job fails); error AFTER partial success -> keep the partial results. [RED]
- AC-6 (frontend): a "# images" control exists for Replicate, sends `_n_images`, and `num_outputs` is hidden from the Replicate param form (the count owns it). [RED]
- AC-7 (no regression): existing single-image gens + key-rotation retry still work; verify_library green.

## Non-goals
- Looping for providers with native batch (fal/openai) — they keep native num_outputs; the control is Replicate-only.
- Parallel generation (loop is sequential — one job at a time is the app's model).

Status: CONTRACT SET (acceptance RED) -> build may proceed
