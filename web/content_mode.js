/* Content Mode (Safe / Editorial / Fashion / NSFW) — pure logic, plan doc §3.
   Loaded before app.js (browser globals) and require()'d by scripts/verify_content_mode.js (node). */
(function (root) {
  // Each mode = a safety-param profile applied per-request + a model-list filter predicate.
  const CONTENT_MODES = {
    safe:      { label: "Safe",      checker: true,  outChecker: true,  raw: false, tol: "2",   filter: false },
    editorial: { label: "Editorial", checker: false, outChecker: false, raw: true,  tol: "4",   filter: true },
    fashion:   { label: "Fashion",   checker: false, outChecker: false, raw: true,  tol: "4",   filter: true, fashionFirst: true },
    nsfw:      { label: "NSFW",      checker: false, outChecker: false, raw: true,  tol: "MAX", filter: true },
  };
  const CONTENT_MODE_HELP = {
    safe: "Default moderation on every model. Best for shared work or client previews.",
    editorial: "Relaxes each model's built-in filter for tasteful nudity, mature themes, and stylized realism (film-grain “raw” mode where available). Not a guarantee — Google/OpenAI-backed models (Gemini, gpt-image) still moderate upstream.",
    fashion: "Editorial permissiveness, plus surfaces virtual try-on and fashion models first.",
    nsfw: "Maximum permissiveness on every model that exposes a safety toggle — sets it to its most-permissive value. Models with no safety parameter are hidden here since their behavior can't be controlled. Google/OpenAI-backed models still moderate upstream regardless.",
  };
  // non-fal services whose backend accepts a single permissive flag (per-service research §4)
  const SERVICE_SAFETY = { replicate: "disable_safety_checker", together: "disable_safety_checker" };

  function modelMaxTolerance(model) {
    const p = ((model && model.params) || []).find(x => x.name === "safety_tolerance");
    if (!p || !p.values || !p.values.length) return "6";
    return p.values.map(String).sort((a, b) => Number(a) - Number(b)).slice(-1)[0];  // enum max ("6", or "5")
  }
  function isRelaxable(model, service) {
    if (model && model.supports_relaxed_safety) return true;
    const n = new Set(((model && model.params) || []).map(p => p.name));
    if (n.has("enable_safety_checker") || n.has("safety_tolerance")) return true;
    return !!SERVICE_SAFETY[service];  // replicate/together can be relaxed even without a per-model flag
  }
  function isFashionModel(model) {
    const s = ((model && (model.id + " " + (model.label || "") + " " + (model.description || ""))) || "").toLowerCase();
    return /fashion|try.?on|virtual.?try|outfit|apparel|clothing|garment|wardrobe/.test(s);
  }
  // pure: collected params -> params with the mode's safety profile applied (only where the model declares it)
  function applyContentMode(params, model, mode, service) {
    const prof = CONTENT_MODES[mode] || CONTENT_MODES.safe;
    const n = new Set(((model && model.params) || []).map(p => p.name));
    const out = Object.assign({}, params);
    if (n.has("enable_safety_checker")) out.enable_safety_checker = prof.checker;
    if (n.has("enable_output_safety_checker")) out.enable_output_safety_checker = prof.outChecker;
    if (n.has("safety_tolerance")) {
      const max = Number(modelMaxTolerance(model));
      const want = prof.tol === "MAX" ? max : Number(prof.tol);
      out.safety_tolerance = String(Math.min(want, max));  // clamp to the model's own enum max
    }
    if (n.has("raw") && prof.raw) out.raw = true;
    const svcFlag = SERVICE_SAFETY[service];  // non-fal single-flag services (replicate/together)
    if (svcFlag) out[svcFlag] = mode !== "safe";
    return out;
  }

  const API = { CONTENT_MODES, CONTENT_MODE_HELP, SERVICE_SAFETY, modelMaxTolerance,
                isRelaxable, isFashionModel, applyContentMode };
  if (typeof module !== "undefined" && module.exports) module.exports = API;  // node (verify script)
  else Object.assign(root, API);                                             // browser globals for app.js
})(typeof window !== "undefined" ? window : this);
