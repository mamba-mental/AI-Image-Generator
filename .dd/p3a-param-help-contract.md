# *DD Contract: P3-A — param help tooltips (#6) + safety-tolerance labels (#5)
Build type: web UI · atdd/edd/tdd. Harness: DOM check via served web/.
## Acceptance
- AC-1 (#6): web/app.js has PARAM_HELP map; renderParams puts help text in a title= tooltip on each param label. [RED]
- AC-2 (#5): safety_tolerance renders as a labeled select (SAFETY_LABELS) — each level 1-6 has human copy, not a bare number. [RED]
- AC-3: DOM proof — served page, a model with safety_tolerance shows labeled options; a param row has a non-empty title. [RED]
Status: CONTRACT SET
