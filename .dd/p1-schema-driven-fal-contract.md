# *DD Contract: P1 — Adapter core + fal live catalog + schema-driven forms

Build type: Web app + backend adapter (union) — methods: story-tdd (outer) · sbe (spec/examples) · tdd (inner)
Stack: Python 3.13 (providers/, schema.py) + JS (webui/form.js) · harness `.dd/verify_p1.py` binary PASS/FAIL
Approved plan: C:/Users/tiran/.claude/plans/sharded-floating-nebula.md (P1)

## Acceptance (done-gate)
- AC-1  providers/base.py defines Provider with list_models / form_spec / submit; fal registered. -> ::ac1 [RED]
- AC-2  FalProvider.list_models() returns >=100 models (live fal catalog, disk-cached), each {id,label,kind in (image,video)}. -> ::ac2 [RED]
- AC-3  FalProvider.form_spec("fal-ai/flux-2/turbo") is a live-schema FormSpec: a list of fields, each {name,widget,label,default?} with widget in (select,slider,number,toggle,text); includes image_size(select) + num_images + guidance. NO hand-coded param list. -> ::ac3 [RED]
- AC-4  Schema→widget mapping (schema.py, pattern from app.py:2891 _create_param_widget): enum→select, boolean→toggle, number w/ min&max→slider, number w/o range→number, string→text; a `loras` array field → widget "loras"; image_url/image_urls → widget "image". -> ::ac4 [RED]
- AC-5  LoRA conditionality: form_spec for a LoRA model (fal-ai/flux-2/lora) contains a widget=="loras" field; form_spec for a non-LoRA model (fal-ai/flux-2/turbo) contains NONE. -> ::ac5 [RED]
- AC-6  bridge.py exposes catalog(provider,kind) + form_spec(model_id) + generate(model_id, params_dict); generate routes fal through FalProvider.submit. Non-fal providers still function (legacy path). -> ::ac6 [RED]
- AC-7  webui/form.js: renderForm(spec) builds one DOM control per field by widget type; collectParams() reads them back to a dict. Pure-function unit self-check passes (node). -> ::ac7 [RED]
- AC-8  Smoke: `python app_web.py --smoke` still exits 0 / SMOKE OK. -> ::ac8 [RED]
- AC-9  LIVE story gate: FalProvider.submit("fal-ai/flux-2/turbo", {prompt,...}) lands a real image; and one schema-driven param (output_format=jpeg from the form) is honored. -> ::ac9 [RED, --live]

## Examples (SBE)
- fal flux-2/turbo schema → FormSpec must contain field name "image_size" widget "select" with enum incl "portrait_3_4"; field "num_images"; field "output_format" enum [jpeg,png].
- flux-2/lora schema → FormSpec contains a field widget "loras".

## Inner (TDD)
- first failing unit: verify_p1.py::ac3 (form_spec is live, not hardcoded).

## Non-goals (P1)
- cliproxy (P3), settings panel (P2), porting non-fal providers to adapters (P4).
- Enumerating all 1399 fal models in UI at once — paginate/search; cache to disk; refresh button.

Status: CONTRACT SET (harness RED) -> build may proceed
