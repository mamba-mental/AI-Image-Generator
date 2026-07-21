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
    editorial: "Shows models with an adjustable content filter, relaxed for tasteful nudity, mature themes, and stylized realism. Permissive is not a guarantee. Google/OpenAI-backed models (Gemini, gpt-image, nano-banana) are hidden here — they moderate upstream regardless of the toggle.",
    fashion: "Editorial permissiveness, plus surfaces virtual try-on and fashion models first.",
    nsfw: "Shows models whose content filter can be set fully permissive (at max). “Verified” models were confirmed to actually produce NSFW; the rest expose the toggle and are likely-capable but untested (use “Verified only” to narrow). Upstream-moderated providers are excluded — they refuse regardless of the toggle.",
  };
  // non-fal services whose backend accepts a permissive flag (per-provider research §4).
  // { param, allow } — `allow` is the value that PERMITS NSFW; polarity differs per provider:
  //   together/replicate disable_safety_checker=true allows; runware checkNSFW=false allows;
  //   novita enable_nsfw_detection=false allows. Safe mode sends the opposite (moderating) value.
  const SERVICE_SAFETY = {
    replicate: { param: "disable_safety_checker", allow: true },
    together:  { param: "disable_safety_checker", allow: true },
    runware:   { param: "checkNSFW", allow: false },
    novita:    { param: "enable_nsfw_detection", allow: false },
  };

  function modelMaxTolerance(model) {
    const p = ((model && model.params) || []).find(x => x.name === "safety_tolerance");
    if (!p || !p.values || !p.values.length) return "6";
    return p.values.map(String).sort((a, b) => Number(a) - Number(b)).slice(-1)[0];  // enum max ("6", or "5")
  }
  // graded capability from the catalog (upstream_moderated | permissive | verified | filtered).
  // non-fal models carry no grade -> permissive iff the service has a single permissive flag.
  function contentCapability(model, service) {
    if (model && model.content_capability) return model.content_capability;
    return SERVICE_SAFETY[service] ? "permissive" : "filtered";
  }
  function isRelaxable(model, service) {
    const c = contentCapability(model, service);
    return c === "permissive" || c === "verified";  // shown in Editorial/Fashion/NSFW
  }
  function isVerified(model, service) {
    return contentCapability(model, service) === "verified";  // empirically/curated confirmed NSFW
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
    const svc = SERVICE_SAFETY[service];  // non-fal single-flag services (polarity per provider)
    if (svc) out[svc.param] = (mode !== "safe") ? svc.allow : !svc.allow;
    return out;
  }

  const API = { CONTENT_MODES, CONTENT_MODE_HELP, SERVICE_SAFETY, modelMaxTolerance,
                contentCapability, isRelaxable, isVerified, isFashionModel, applyContentMode };
  if (typeof module !== "undefined" && module.exports) module.exports = API;  // node (verify script)
  else Object.assign(root, API);                                             // browser globals for app.js
})(typeof window !== "undefined" ? window : this);
