# Spec D — Product identity / naming (#7)

**Cluster:** #7 · **Type:** branding / positioning brief · **Blocking:** nothing (independent of A/B/C)
**Refined:** 2026-07-21 via refine-to-spec (judge gpt-5.2, pinned) — baseline 28 (outline). This version is the execution-ready brief.

## Problem (PRIME's words)
> "Where did the name 'AI STUDIO VOID' come from? Is this the most appropriate name for this app… we need a better more marketable name if we intend to sell this product."

## Current state (verified)
- **"AI Studio Void"** predates this workstream; **no recorded origin** in the repo (no README rationale, no ADR, no brand doc). It appears only as `engine_config.APP_NAME`, the window title, the desktop shortcut, and `ai-studio-void.ico`.
- Rename cost today is **low and mechanical** (no public traction yet) — see §9.

## What the product actually is (grounding — names aren't generated in a vacuum)
A **desktop** (pywebview) app unifying **many AI image/video providers** (fal, Novita, Together, Runware, Replicate, OpenAI, NVIDIA, Gemini, Ideogram, AGNES…) behind one composer, with a **local 5k+ library**, saveable **presets**, **content-mode** control (incl. uncensored/fine-art), and evidence-backed per-model capability. Wedge candidates from what's built: (a) **multi-provider in one surface**, (b) **desktop-local + private**, (c) **power-user control (models/params/LoRAs/content-mode)**, (d) **permissive/uncensored** generation.

## §1 — Audience + buyer context (decidable)
- **Primary:** independent AI-image power users & solo creators (artists, designers, NSFW-comfortable creators, prompt tinkerers) juggling 3+ provider tabs who want one local desktop hub with full control.
- **Secondary:** small studios/freelancers producing client visuals who need reproducibility (recipes) + a searchable library.
- **Buyer = user** (prosumer self-serve), English-first, global. **GTM:** one-time license or low-tier prosumer SaaS, bring-your-own provider keys.
- **AC-D1:** the picker page header restates the primary audience + JTBD ("bring every AI image provider into one private desktop studio I fully control") so names are judged against a real user.

## §2 — Category + positioning (filled template, not blank)
- **Category:** "multi-provider AI image/video studio (desktop)."
- **Competitive set (naming space each occupies):** Midjourney (mythic/playful), Leonardo.ai (techy), NightCafe (friendly), InvokeAI (pro/technical), ComfyUI (engineer), Draw Things (Apple-local), Krea (modern-minimal).
- **Positioning statement (locked template, filled):** *For independent AI creators who juggle many image providers, **[NAME]** is a desktop AI-image studio that unifies every provider behind one composer with a searchable library and full creative control. Unlike single-provider web tools, it runs locally, keeps your work private, and never limits what you can make.*
- **AC-D2:** the brief carries this statement verbatim; every candidate is scored on fit to it (§5).

## §3 — Name constraints checklist (the "marketable" test — accept/reject without debate)
- **Must:** ≤ 3 syllables; trivially spellable on hearing; evokes *studio / craft / breadth / control or light*; works as a wordmark; not locale-offensive (quick EN/ES/PT/FR check).
- **Should:** hint at "many-in-one / make anything"; ownable/distinctive in the category.
- **Forbidden:** literal "AI" in the name; dictionary-generic-only; > 12 chars; negative/empty connotations (**"Void" is disqualified** — reads as absence/deletion); near-collision with the competitive set or a major brand.
- **AC-D3:** permissive positioning is fine but the name must **not** be adult-explicit (payment-processor- and app-store-safe). Any finalist failing a **Must** or **Forbidden** item is eliminated **before** scoring.

## §4 — Name-generation method (counts, not "brainstorm")
Explore these families, min candidates each, then prune:
- Descriptive compounds (studio/forge/loom/atlas/prism + modifier) — ≥ 8
- Invented / portmanteau — ≥ 8
- Metaphor (light, craft, forge, constellation, aperture, canvas) — ≥ 8
- Latin/Greek roots (readable only) — ≥ 6
- **Pipeline:** ≥ **30 raw** → screen against §3 → **12 screened** → availability (§6) → **5–8 finalists**.
- **AC-D4:** the run records the funnel counts (30→12→5–8) in the deliverable.

## §5 — Shortlisting rubric (scored, not vibes)
0–5 per axis × weight, per finalist:
| Axis | Weight |
|---|---|
| Memorability | 20 |
| Pronounceability / spellability | 15 |
| Fit to positioning (§2) | 20 |
| Distinctiveness in category | 15 |
| Availability (domain/handles) | 20 |
| Legal-risk quick screen | 10 |
- **Elimination gates:** any name failing pronounceability **or** flagged high legal-risk is dropped regardless of total.
- **AC-D5:** a filled scoring table for every finalist ships in the deliverable, with a one-line "why the top pick wins."

## §6 — Availability-check procedure (tools + scope + evidence)
- **Domains:** `.com` strongly preferred; fallback `.app`/`.io`; `get<name>.com` allowed as a note, not a pass. Via registrar/WHOIS lookup.
- **Handles:** X, GitHub, YouTube, Instagram, TikTok, Product Hunt.
- **Trademark pre-screen:** USPTO TESS quick search (class 9 software); "conflict" = a live mark in the same class with a confusingly-similar name. Flagged as a **sanity check, not legal advice.**
- **AC-D6:** a per-finalist table with **timestamped** results + links and a clear **pass/fail**; unavailable-`.com` is a scoring penalty (§5), not an auto-kill unless a strong fallback also fails. Checks are **actually queried**, never asserted.

## §7 — Rendered picker deliverable (PRIME's standing rule: rendered, never a text list)
- **Artifact:** a self-contained **HTML picker page** at `dashboards/product-name-picker.html`, served over `dashboards_server` (`:31960`), theme-aware, mandatory credit footer.
- **Per-name card:** name + pronunciation + rationale; the positioning line it enables; **wordmark treatments in-situ** (window title bar + icon tile + one-line tagline); domain/handle status **badges**; the §5 score summary + top risk; "why this beats the others."
- **Selection:** a "pick top 3" affordance + a free-text note field (mirrors the AskUserQuestion-cards preference for interactive choices).
- **AC-D7:** the page renders 5–8 finalist cards from a data array; verify confirms it opens 200 over `:31960` and shows all cards with availability badges (eyeball + DOM count).

## §8 — Decision + sign-off (keep-the-name is a legitimate outcome)
- **AC-D8a — Anti-rename bias.** The deliverable must include an **honest argument *for* keeping "AI Studio Void"** so the recommendation isn't rename-biased. Rename only if a candidate clearly beats it on §3+§5+§6.
- **AC-D8b — Sign-off + package.** PRIME selects top 1–3 → deeper checks (expanded trademark + broader handles) → a **final name package**: chosen name, 5–10 taglines, a one-sentence elevator pitch, and a fresh "naming story" origin (replacing the unknown "Void" origin). Explicit sign-off; if **no** candidate clears §3+§6, the exit is an **iteration plan** (new families, loosen a Should), never shipping a failing name.

## §9 — Safe-rename plan (mechanical, reversible)
- **AC-D9 — Rename-risk + migration.** State whether the rename is **soft** (alias/umbrella over "AI Studio Void", keep repo/dir) or **hard** (breaking). Given **no public traction yet**, default expectation = **soft** (low cost) — stated, not assumed. If a new name wins, ship a mechanical checklist covering: `engine_config.APP_NAME`, window title, `ai-studio-void.ico`, **both** Desktop shortcut locations, repo/folder, and a **config-directory migration** from `%APPDATA%\AI Studio Void\` that preserves **keys, presets, and library paths** — with a rollback. *Check:* after rename, the app launches under the new name with existing config/keys/library paths intact (smoke + key-resolution check); old `%APPDATA%` config is migrated, not abandoned.

## Non-goals
- Full brand/visual-identity system (logo suite, type system) beyond wordmark-casing hints. The marketing site / pricing page.

## Verification
- The run produces: the filled positioning statement (§2), funnel counts (§4), a scoring table per finalist (§5), a timestamped availability table (§6), and the rendered picker page (§7).
- `.dd/verify_naming.py` — asserts `product-name-picker.html` exists, serves 200 over `:31960`, and its finalist data array has 5–8 entries each carrying `{name, rationale, scores, availability}`. If renamed: smoke asserts launch + key-resolution under the new name with config migrated. `python main.py --smoke` unaffected (branding assets, not the engine).
