# Batch C — Logs + Status (items #14, #15) — dd-router contract

Status: RED (author before build; verify_pC.py RED→GREEN)

## #14 — Portainer-style ring-buffer error log + searchable Logs panel
- AC-14.1: `engine/logbuf.py` — thread-safe bounded ring buffer (deque maxlen) with `append(level,type,message,detail)` + `read(query,level,limit)` + `clear()`.
- AC-14.2: `jobs.py` `emit()` logs EVERY event; the `_run` except captures the FULL traceback (`traceback.format_exc()`) into the buffer at level=error.
- AC-14.3: `bridge.py` `get_logs(query, level)` returns filtered entries; `clear_logs()` empties.
- AC-14.4: `index.html` viewtoggle has a LOGS button; `app.js` `renderLogs()` shows timestamped, level-colored rows with a search box + Copy-all + Clear.
- Runtime: force a backend error → a level=error row with the full traceback appears; search filters rows; copy puts text on clipboard.

## #15 — Staged status line + copyable error popup
- AC-15.1: `jobs.py` emits a "saving…" progress stage before `persist_results` (so status walks queued→running→saving→done).
- AC-15.2: job_error event carries `detail` (full traceback) in addition to `error`.
- AC-15.3: `app.js` `onEngineEvent` shows staged status in `#statusmsg`; on job_error opens an error popup (`#errpop`) with the full text + a Copy button.
- AC-15.4: popup close + copy work.
- Runtime: trigger a real error → popup shows full detail, Copy writes it to clipboard; status line shows the stages on a success run.

## Evidence rule
Each AC: file:line + code snippet + runtime receipt (functional Python for backend, DOM for UI). Ledger GREEN only on observed evidence.
