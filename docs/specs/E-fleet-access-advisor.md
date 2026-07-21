# Spec E — LLM/model fleet-access advisor dashboard (#new, PRIME-requested)

**Cluster:** model-fleet discoverability · **Type:** dashboard (separate surface from the AI Studio Void app)
**Deliverable:** `C:/AI CoWork/dashboards/model-fleet-router.html`, served by `dashboards_server.py` on `:31960` — **not** inside the pywebview app.
**Pattern source:** `dashboards/session-command-router.html` (the Ask-AI query-box UX) + `dashboards/_components/picker-inline.js` + the `dashboards_server.py` `/api/route` · `/api/chat` endpoints.
**Refined:** 2026-07-21 via refine-to-spec (judge gpt-5.2, pinned) — baseline 86, this version closes the flagged gaps with real repo wiring.

## Problem (PRIME's words)
> "the AI model suggestions … needs to be designed like the query boxes on pages like [session-command-router.html] … configured and wired to answer questions about the llm model fleet access."

## What it is
A single-purpose page that answers **"which models can I access, and which should I use?"** across PRIME's model fleet — the cliproxy 600+ catalog + every keyed provider — via the same instant-routing + Ask-AI box the router pages use. Fleet-wide sibling of the in-app suggestion box (Spec B §4): shared box pattern, but its data is the **LLM/model fleet**, not the image app's providers.

## Data sources + the merge/precedence rule (deterministic — so it can never "invent" access)
- **cliproxy live catalog** — `GET {cliproxy}/v1/models` (600+ live models; base URL + client key from config — the `OPENAI_BASE_URL`/cliproxy-key lever).
- **Fleet catalog** — `dashboards/fleet-catalog.json` (verified model facts; model-ID claims come from this / `/fleet-model-verifier`, **never memory** — standing fleet rule).
- **Provider key-status** — reachable-with-a-live-key probe (reuse the credit-dashboard probe).
- **Precedence (AC-E0):** `allowed_ids` = **verified in `fleet-catalog.json` ∩ present in live `/v1/models`** (if the live fetch fails → **verified-only mode**, flagged in the UI). `accessible_now` = `allowed_ids` filtered by **key-status success** for that provider/access-path. The box only ever suggests `accessible_now`; anything `allowed` but not `accessible_now` is shown as "known but not reachable with current keys." No model outside `allowed_ids` is ever named.

## Server data contract (so instant routing has a dataset without per-keystroke calls)
- **AC-E-DATA — one load endpoint.** `dashboards_server.py` gains `GET /api/fleet-catalog` returning `{fetched_at, live_ok, models:[{id, provider, access_path, capability, price, accessible}]}` (the merged/precedence-applied set from above). The page fetches this **once on load** into memory; instant keyword routing (AC-E1) runs purely over that in-memory array — **no network call per keystroke.**

## Acceptance criteria (RED → GREEN)
- **AC-E1 — The box, router-styled + instant local routing.** A `.pinput` + "Ask AI" box matching `session-command-router.html` (theme-aware, mono input, gold accent, sample-intent chips). Typing does **instant keyword routing over the in-memory `/api/fleet-catalog` array** (provider/model/capability/price) with **no network call** — the `picker-inline.js` `classify()` pass. Enter / "Ask AI" fires the model-answered reply.
- **AC-E2 — Ask-AI wired to a REGISTERED `fleet` PROSE scope (exact repo wiring).** Enter / "Ask AI" calls `/api/route` with `scope:"fleet"`. Register it concretely: add `_SYSTEM_FLEET` to the `SYSTEM_PROMPTS` dict (`dashboards_server.py` ~L581) **and** add `"fleet"` to `PROSE_SCOPES` (~L612) so it returns an advisory prose answer, not routing JSON; **plus** a grounded-injection catalog at `dashboards/data/routing-catalog/scopes/fleet.json` (the 2026-07-20 auto-register pipeline injects it live per request). Note: `/api/route` now **400s on an unregistered scope** (the old silent code-prompt fallback was fixed 2026-07-20), so registration is mandatory — a 400 is the failing signal. `scripts/check_router_vocab.py` must pass for the new page vocab.
- **AC-E3 — Grounded answers with a citation line.** The `fleet` prompt is primed (via the grounded-injection file + request context) with the `accessible_now` set + `fetched_at`, so answers name **real, currently-accessible** models as **`id · provider · access-path · why`** and say plainly when a model is **not** reachable. Every Ask-AI reply ends with a source line: `Source: fleet-catalog.json @ <ts> · cliproxy @ <ts>`.
- **AC-E4 — Freshness + honesty.** The page shows `fetched_at`; a **stale badge** if older than TTL; a **verified-only badge** when the live cliproxy fetch failed. The page states it does not invent model IDs.
- **AC-E5 — Registered + footered.** A nav card/link is added to `dashboards/command-center.html` (matching its existing card pattern, label "Model Fleet Router"); the page carries the mandatory dashboard credit footer (skill/date/regen note) + freshness badge; served over `:31960` (not `file://`).

## Non-goals
- Changing model routing / fleet configs (read-only advisor; config changes still go through `/fleet-model-verifier` → `fleet-model-advisor`). Duplicating the credit dashboard (this is access advice, not balances).

## Verification
- `.dd/verify_fleet_router.py` — asserts: `model-fleet-router.html` serves **200** over `:31960`; `GET /api/fleet-catalog` returns the schema above with ≥1 model and `accessible` flags; `"fleet"` is registered in **both** `SYSTEM_PROMPTS` and `PROSE_SCOPES` (grep the server source) so `/api/route scope=fleet` does **not** 400/fall back; an Ask-AI fleet call returns a **fleet-scoped answer** = response contains **≥1 model id exactly in `allowed_ids`** + its `provider` + `access-path` + the `Source: …` citation line; `check_router_vocab.py` green.
- Eyeball: box renders router-style, instant routing filters as you type, an Ask-AI reply cites accessible models and refuses to name an unreachable one.
