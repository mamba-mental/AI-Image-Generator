/* Acceptance verifier for the pure apply logic in web/presets.js (Spec C AC-4.1..4.4).
   Node: `node scripts/verify_presets_apply.js` */
const path = require("path");
const { substitutePrompt, mapParamsToProvider, computeApply, previewApply, applyPreset } =
  require(path.join(__dirname, "..", "web", "presets.js"));

let pass = 0, fail = 0;
const chk = (name, cond) => { cond ? pass++ : fail++; console.log((cond ? "[PASS] " : "[FAIL] ") + name); };

// AC-4.3 — {prompt} substitution defined for 0 / 1 / N occurrences
chk("0 occurrences -> append", substitutePrompt("epic fantasy art", "a red dragon") === "epic fantasy art, a red dragon");
chk("0 occurrences, no template -> just the user prompt", substitutePrompt("", "a cat") === "a cat");
chk("0 occurrences, no user prompt -> just the template", substitutePrompt("epic fantasy art", "") === "epic fantasy art");
chk("1 occurrence -> replaces the token", substitutePrompt("epic, {prompt}, 8k", "a cat") === "epic, a cat, 8k");
chk("N occurrences -> replaces ALL", substitutePrompt("{prompt} vs {prompt}", "cat") === "cat vs cat");

// AC-4.4 — cross-provider param map: known keys map, unknown keys drop with a warning, no error
const mapped = mapParamsToProvider({ guidance_scale: 7, unknown_flag: true }, ["guidance", "seed"]);
chk("known param maps to the target's own name", mapped.params.guidance === 7);
chk("unmapped param dropped, not errored", !("unknown_flag" in mapped.params));
chk("drop is logged as a warning string", mapped.warnings.some(w => w.includes("unknown_flag")));
chk("mapParamsToProvider never throws on an empty target list", (() => {
  try { mapParamsToProvider({ x: 1 }, []); return true; } catch (e) { return false; }
})());

// AC-4.3 — apply is explicit + non-destructive: a hand-edited field survives a Style that omits it
const composer0 = { prompt: "a lighthouse", negative_prompt: "hand-edited negative", model: "hand-picked-model", params: { steps: 30 } };
const style = { id: 1, updated: 100, name: "Editorial", negative: "", prompt_template: "cinematic, {prompt}", params: {}, model: "" };
const applied = applyPreset("Style", style, composer0);
chk("prompt substituted from the template", applied.prompt === "cinematic, a lighthouse");
chk("blank preset field never blanks a hand-edited negative_prompt", applied.negative_prompt === "hand-edited negative");
chk("blank preset model never overwrites the hand-picked model", applied.model === "hand-picked-model");
chk("existing params preserved when the preset defines none", applied.params.steps === 30);

// AC-4.3 — preview shows a real diff before commit
const { diffs } = previewApply("Style", style, composer0);
chk("preview reports the prompt change", diffs.some(d => d.field === "prompt" && d.after === "cinematic, a lighthouse"));
chk("preview reports NO change for the untouched negative_prompt", !diffs.some(d => d.field === "negative_prompt"));

// AC-4.3 — idempotent: applying the SAME preset twice yields the SAME result (no compounding —
// the A1111 #1383/#559 "style text appended twice" bug this design specifically avoids)
const twice = applyPreset("Style", style, applied);
chk("re-applying the same style is a true no-op", twice.prompt === applied.prompt);
chk("re-apply produces zero diffs", previewApply("Style", style, applied).diffs.length === 0);
// a DIFFERENT (or updated) preset still applies normally afterward
const style2 = { id: 2, updated: 1, name: "Fashion", negative: "", prompt_template: "runway, {prompt}", params: {} };
const afterDifferent = applyPreset("Style", style2, applied);
chk("a different style id still applies after a no-op re-apply", afterDifferent.prompt === "runway, cinematic, a lighthouse");

// AC-4.4 — Recipe applied on a mismatched provider warns, never auto-switches
const recipe = { id: 9, updated: 5, name: "Exact shot", provider: "together", model: "flux-dev",
  seed: "12345", prompt: "a red dragon", negative: "", params: { guidance_scale: 7 } };
const composer1 = { prompt: "old", negative_prompt: "", model: "old-model", provider: "fal", params: {} };
const { composer: recApplied, warnings } = computeApply("Recipe", recipe, composer1, { targetProvider: "fal" });
chk("recipe warns on provider mismatch", warnings.some(w => w.includes("pinned to together")));
chk("recipe does NOT auto-switch the active provider", recApplied.provider === "fal");
chk("recipe still sets prompt/model/seed on the composer", recApplied.prompt === "a red dragon" && recApplied.model === "flux-dev" && recApplied.params.seed === "12345");
const sameProvider = computeApply("Recipe", recipe, Object.assign({}, composer1, { provider: "together" }));
chk("no warning when provider already matches", sameProvider.warnings.length === 0);

console.log(`\n${fail ? "FAILED " + fail : "ALL PASS"} (${pass} passed)`);
process.exit(fail ? 1 : 0);
