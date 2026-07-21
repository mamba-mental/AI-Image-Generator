# Provider balance / credits APIs — live-verified (2026-07-21)

Agent C research task. Every row below is a **live probe against PRIME's real keys** (env var
first, then the repo `config.json` — the same resolution order the app uses), run 2026-07-21.
Key values are never printed; only HTTP status, response field names, and balances **redacted
to an order-of-magnitude bucket** (`<$1` / `$1-10` / `$10-100` / `$100-1,000` / `>$1,000`) are
recorded, per the task's redaction rule.

This answers PRIME's "why don't all services show up-to-date credit info" complaint directly:
**4 of 13 providers have a real, queryable $-balance API. The rest are portal-only or don't have
a balance concept at all** — no amount of engineering wires a balance panel that doesn't exist
upstream.

## Table

| Provider | Endpoint | Auth header | Response field | Units | Probe result | Verdict |
|---|---|---|---|---|---|---|
| **fal** | `GET api.fal.ai/v1/account/billing?expand=credits` | `Authorization: Key <FAL_KEY_ADMIN>` | `credits.current_balance` | USD | HTTP 200 · `$10-100` OK | **WIRE** (already wired in `dashboards_server.py`) |
| **novita** | `GET api.novita.ai/openapi/v1/billing/balance/detail` | `Bearer` | `availableBalance` (÷10000) | USD | HTTP 200 · `$10-100` OK | **WIRE** (already wired) |
| **runware** | `POST api.runware.ai/v1` body `[{"taskType":"accountManagement","operation":"getDetails","taskUUID":"<uuidv4>"}]` | `Bearer` | `data[0].balance` | USD | HTTP 200 · `$10-100` OK (matches the $20 top-up from today's Step 0.1) | **WIRE** — real endpoint, confirmed live, **not yet added** to the balance-out dict (P2 backlog item, not this batch) |
| **openrouter** | `GET openrouter.ai/api/v1/credits` | `Bearer` | `data.total_credits − data.total_usage` | USD | HTTP 200 · balance computed OK | **WIRE** (already wired, in the LLM-provider section of `dashboards_server.py`, not the media-provider section — same key resolution applies) |
| **together** | none found — tried `/v1/balance` (404), `/v1/account` (404, both return the marketing-site 404 page, i.e. not routed at all) | `Bearer` | — | — | `/v1/models` HTTP 200 confirms the key itself is valid | **PORTAL-ONLY** — no balance API exists; [docs](https://docs.together.ai/docs/billing-credits) describe prepaid credits with no corresponding read endpoint |
| **replicate** | `GET api.replicate.com/v1/account` | `Token` | none — response is `{type, username, name, avatar_url, github_url}`, no balance field | — | HTTP 200, key valid, no billing data | **PORTAL-ONLY** — [Replicate's own docs](https://replicate.com/docs/topics/billing) confirm balance is portal/dashboard-only; GitHub issue open requesting this API |
| **openai** | `GET api.openai.com/v1/dashboard/billing/credit_grants` (legacy endpoint) | `Bearer` | — | — | HTTP 403 (legacy dashboard endpoints are blocked for this key type — confirmed live, not a hypothetical); `/v1/models` HTTP 200 confirms the key itself is valid | **PORTAL-ONLY** — the legacy billing endpoints exist in old docs but this key can't reach them; no current replacement API for balance |
| **huggingface** | `GET huggingface.co/api/whoami-v2` | `Bearer` | `isPro` (account tier only — HF has no prepaid $-credit concept for the Hub API; paid compute is billed separately via Stripe/cloud, no balance endpoint) | — | **HTTP 401** `"Invalid username or password."` — **the configured token is currently rejected**, independent of the balance question | **PORTAL-ONLY** for balance (no $ concept via API even with a valid token) — **plus a live bug: flag the stored `huggingface_token` as expired/revoked, needs reissue in Settings** (not fixed here — outside this task's one named fix) |
| **nvidia** | none documented | `Bearer` | — | — | `/v1/models` HTTP 200 confirms key valid; no credits/balance endpoint exists on `integrate.api.nvidia.com` | **PORTAL-ONLY** — credits tracked only at build.nvidia.com |
| **gemini** | none documented (billing lives in GCP Billing console, separate product) | `?key=` query param | — | — | `ListModels` HTTP 200 confirms key valid; no balance endpoint | **N/A** — Gemini API keys aren't tied to a queryable prepaid balance; cost is GCP-invoiced |
| **agnes** | none documented — tried `/v1/user`, `/v1/account`, `/v1/balance` | `Bearer` | — | — | `/v1/models` HTTP 200 (key valid, free-tier inference works); all 3 balance guesses HTTP 404 | **N/A** — free-tier gateway with a default allocation shown only in their web console; no balance endpoint in their docs or via probing |
| **ideogram (public API)** | none documented | `Api-Key` | — | — | **HTTP 401** `"Access denied. Please verify your API Token is valid."` on a real multipart generate call (matches the app's own `ideogram_api.py` request shape exactly) | **PORTAL-ONLY** for balance, **plus the key itself is currently broken** — project history ([[reference_ideogram-web-session-backend]]) recorded a 402 (valid key, empty balance) previously; it's now 401 (rejected), suggesting the key was rotated/revoked since. Not fixed here. |
| **ideogram (web/subscription)** | n/a — spends the logged-in Plus subscription via the Firebase web session, not a metered wallet | Firebase session token | — | — | not applicable | **N/A** — no $-balance concept; it's a subscription, not prepaid credits |
| **cliproxy** | `remote-management:` block confirmed present in the live HP2 config (`~/cliproxyapi-stack/config.local.yaml`, port 8317) but gated by a separate bcrypt-hashed `secret-key` that isn't in the app's key store | unknown (separate secret) | — | — | 4 guessed paths (`/api/usage`, `/api/stats`, `/v1/usage`, `/api/providers`) on the inference port all HTTP 404 | **N/A** — cliproxy is PRIME's own self-hosted router, not a billed service; it has no spend ledger of its own (the providers *behind* it have theirs, already covered above/elsewhere). Its management API is a config-admin surface, not a balance API. |

## Bottom line for the credit dashboard

- **Already correctly wired:** fal, novita, openrouter (LLM section) — 3 real $-balances.
- **Can be wired now, isn't yet:** **runware** — the account-management endpoint is real, documented, and just returned a live balance. This is a clean P2 pickup (same shape as novita's wiring, ~15 lines).
- **Genuinely can't show a $-balance, ever, via API** (not an engineering gap — the upstream API doesn't exist): together, replicate, openai, huggingface, nvidia (all portal-only), gemini, agnes, ideogram-web, cliproxy (all N/A — no metered-balance concept applies). For these, the honest UI is a "portal-only" chip linking to the provider's billing page, not a spinner that never resolves.
- **Two providers have a broken/rejected key independent of the API question:** huggingface (401) and ideogram public API (401). Flagged for PRIME to reissue; not touched by this research pass.

## Config-path bug fixed (Agent C's one named fix)

`dashboards_server.py`'s `_app_key()` helper (used by novita/runware/agnes/ideogram/cliproxy key
resolution) only ever read `%APPDATA%\AI Studio Void\config.json`. That file is a **stale
snapshot from a prior packaged run** — 21 hours older than the repo's `config.json`, missing
`runware_api_key` entirely (today's Step 0.1 addition), and generally behind. The app currently
runs from source (dev mode), which reads/writes `C:\GitHub_Projects\2026.0226 -
AI-Image-Generator\config.json` — that's the live file, not the `%APPDATA%` copy.

Fixed to check, in order: the repo config.json → `%APPDATA%\Omni-Image\config.json` (current app
name, for a future packaged build) → `%APPDATA%\AI Studio Void\config.json` (legacy name, for an
existing packaged install). First candidate with a non-empty value for the requested field wins.
Verified standalone (outside the running server, per the task's no-restart constraint): all 5
media-provider key fields now resolve correctly from the repo config, including `runware_api_key`
which the old code silently missed.

Backup: `B:\AI-CoWork-Archive\config-backups\2026-07-21\dashboards_server.py.10-32.bak`.
