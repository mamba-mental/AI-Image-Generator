/* Presets — Style/Recipe apply logic (Spec C AC-4.1..4.4). Pure functions, no DOM — same
   dual-consumption pattern as content_mode.js: node (scripts/verify_presets_apply.js) AND
   browser globals for app.js.

   Two distinct objects, never conflated (CONTEXT.md glossary + research/2026-07-21_preset-
   tagging-output-modeling.md): a Style is reusable/prompt-optional; a Recipe reproduces ONE
   exact image and is provider-pinned. */
(function (root) {
  // {prompt} substitution (AC-4.3): 0 occurrences -> append the user prompt to the template;
  // 1 -> replace the token; N -> replace ALL occurrences (A1111 #14005 — must be defined for all 3).
  function substitutePrompt(template, userPrompt) {
    const tpl = template || "";
    const up = userPrompt || "";
    if (!tpl.includes("{prompt}")) {
      if (!tpl) return up;
      if (!up) return tpl;
      return `${tpl}, ${up}`;
    }
    return tpl.split("{prompt}").join(up);  // replaces every occurrence (1 or N) identically
  }

  // Canonical param vocabulary this app already uses across providers (AC-4.4). A key already
  // matching the target model's own param names passes through untouched; otherwise it's mapped
  // via this table; anything left over is DROPPED with a logged warning, never an error.
  const PARAM_MAP = {
    width: ["width"],
    height: ["height"],
    steps: ["num_inference_steps", "steps"],
    guidance: ["guidance_scale", "cfg", "guidance"],
    negative: ["negative_prompt"],
    seed: ["seed"],
  };

  function mapParamsToProvider(params, targetParamNames) {
    const known = new Set(targetParamNames || []);
    const out = {}, dropped = [], warnings = [];
    for (const [k, v] of Object.entries(params || {})) {
      if (known.has(k)) { out[k] = v; continue; }
      const canon = Object.entries(PARAM_MAP).find(([, names]) => names.includes(k));
      const target = canon && canon[1].find(n => known.has(n));
      if (target) { out[target] = v; continue; }
      dropped.push(k);
    }
    if (dropped.length) warnings.push(`dropped unmapped params for this provider: ${dropped.join(", ")}`);
    return { params: out, dropped, warnings };
  }

  // Explicit + idempotent + non-destructive apply (AC-4.3). `kind` = "Style" | "Recipe".
  // Idempotency: re-applying the SAME preset (same id + updated timestamp) with no intervening
  // change is a true no-op — this is the fix for the classic "apply appends the style text
  // twice" bug (A1111 #1383/#559): re-substituting {prompt} into an ALREADY-styled prompt would
  // otherwise compound. A blank/undefined preset field never overwrites a hand-edited one.
  function computeApply(kind, preset, composer, opts) {
    const idKey = `_applied${kind}Id`, updKey = `_applied${kind}Updated`;
    const already = composer[idKey] === preset.id && composer[updKey] === preset.updated;
    const warnings = [];
    const targetProvider = (opts && opts.targetProvider) || composer.provider;
    if (kind === "Recipe" && preset.provider && targetProvider && preset.provider !== targetProvider) {
      warnings.push(`this Recipe is pinned to ${preset.provider} — applying on ${targetProvider} is not `
        + `guaranteed to reproduce the exact image. Switch provider first for a guaranteed match.`);
    }
    let mappedParams = preset.params || {};
    if (opts && opts.targetParamNames) {
      const mapped = mapParamsToProvider(mappedParams, opts.targetParamNames);
      mappedParams = mapped.params;
      warnings.push(...mapped.warnings);
    }
    const nextPrompt = already ? composer.prompt
      : kind === "Style"
        ? (preset.prompt_template ? substitutePrompt(preset.prompt_template, composer.prompt) : composer.prompt)
        : (preset.prompt ? preset.prompt : composer.prompt);
    const nextNegative = (!already && preset.negative) ? preset.negative : composer.negative_prompt;
    const nextModel = (!already && preset.model) ? preset.model : composer.model;
    const nextParams = already ? composer.params
      : Object.assign({}, composer.params, mappedParams,
          (kind === "Recipe" && preset.seed !== undefined && preset.seed !== "") ? { seed: preset.seed } : {});
    const next = Object.assign({}, composer, {
      prompt: nextPrompt, negative_prompt: nextNegative, model: nextModel, params: nextParams,
      [idKey]: preset.id, [updKey]: preset.updated,
    });
    const diffs = [];
    const add = (field, before, after) => {
      if (after !== undefined && after !== "" && after !== before) diffs.push({ field, before, after });
    };
    if (!already) {
      add("prompt", composer.prompt, next.prompt);
      add("negative_prompt", composer.negative_prompt, next.negative_prompt);
      add("model", composer.model, next.model);
      for (const k of Object.keys(next.params || {})) add(`param:${k}`, (composer.params || {})[k], next.params[k]);
    }
    return { composer: next, diffs, warnings };
  }

  function previewApply(kind, preset, composer, opts) {
    const r = computeApply(kind, preset, composer, opts);
    return { diffs: r.diffs, warnings: r.warnings };
  }
  function applyPreset(kind, preset, composer, opts) {
    return computeApply(kind, preset, composer, opts).composer;
  }

  const API = { substitutePrompt, mapParamsToProvider, PARAM_MAP, computeApply, previewApply, applyPreset };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else Object.assign(root, API);
})(typeof window !== "undefined" ? window : this);
