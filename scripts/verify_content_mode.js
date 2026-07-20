/* Acceptance verifier for Job 2 (.dd/content-mode-toggle-contract.md).
   Exercises the SHIPPED web/content_mode.js against real catalog models. Node: `node scripts/verify_content_mode.js` */
const fs = require("fs");
const path = require("path");
const { applyContentMode, isRelaxable, CONTENT_MODES, modelMaxTolerance } =
  require(path.join(__dirname, "..", "web", "content_mode.js"));

const cat = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "engine", "fal_models.json"), "utf8"));
const names = (m) => new Set((m.params || []).map((p) => p.name));

const tolModel = cat.models.find((m) => names(m).has("safety_tolerance") && !names(m).has("enable_safety_checker"));
const chkModel = cat.models.find((m) => names(m).has("enable_safety_checker") && !names(m).has("safety_tolerance"));
const bothModel = cat.models.find((m) => names(m).has("safety_tolerance") && names(m).has("enable_safety_checker"));
const noSafety = cat.models.find((m) => !names(m).has("safety_tolerance") && !names(m).has("enable_safety_checker") && (m.params || []).length > 0);

let pass = 0, fail = 0;
const chk = (name, cond) => { cond ? pass++ : fail++; console.log((cond ? "[PASS] " : "[FAIL] ") + name); };

// AC-2 / AC-7 — tolerance clamp to the model's own max + Safe restore
const tolMax = modelMaxTolerance(tolModel);
chk(`NSFW clamps safety_tolerance to model max (${tolMax}) on ${tolModel.id}`,
  applyContentMode({}, tolModel, "nsfw", "fal").safety_tolerance === tolMax);
chk('Safe sets safety_tolerance="2"', applyContentMode({}, tolModel, "safe", "fal").safety_tolerance === "2");
chk('Editorial sets safety_tolerance="4" (or model max if lower)',
  applyContentMode({}, tolModel, "editorial", "fal").safety_tolerance === String(Math.min(4, Number(tolMax))));

// enable_safety_checker family
chk("NSFW -> enable_safety_checker=false", applyContentMode({}, chkModel, "nsfw", "fal").enable_safety_checker === false);
chk("Safe -> enable_safety_checker=true", applyContentMode({}, chkModel, "safe", "fal").enable_safety_checker === true);
chk("Editorial -> enable_safety_checker=false", applyContentMode({}, chkModel, "editorial", "fal").enable_safety_checker === false);

// dual-gated model — both relaxed together
if (bothModel) {
  const b = applyContentMode({}, bothModel, "nsfw", "fal");
  chk(`dual-gated NSFW sets checker=false AND tolerance=max on ${bothModel.id}`,
    b.enable_safety_checker === false && b.safety_tolerance === modelMaxTolerance(bothModel));
}

// hard-filter fal model (no safety params) — nothing injected, not relaxable
const hf = applyContentMode({}, noSafety, "nsfw", "fal");
chk("no-safety fal model: no safety params injected", !("enable_safety_checker" in hf) && !("safety_tolerance" in hf));
chk("no-safety fal model not relaxable", isRelaxable(noSafety, "fal") === false);

// AC-6 — non-fal service (replicate) honors the mode
const rep = { id: "owner/model", params: [] };
chk("replicate NSFW -> disable_safety_checker=true", applyContentMode({}, rep, "nsfw", "replicate").disable_safety_checker === true);
chk("replicate Safe -> disable_safety_checker=false", applyContentMode({}, rep, "safe", "replicate").disable_safety_checker === false);
chk("replicate is relaxable", isRelaxable(rep, "replicate") === true);

// openai hard filter — no flag, not relaxable
const oai = { id: "gpt-image-2", params: [] };
chk("openai NSFW injects no safety flag", Object.keys(applyContentMode({}, oai, "nsfw", "openai")).length === 0);
chk("openai not relaxable", isRelaxable(oai, "openai") === false);

// AC-3 filter predicate — supports_relaxed_safety respected
chk("supports_relaxed_safety=true -> relaxable", isRelaxable({ id: "z", params: [], supports_relaxed_safety: true }, "fal") === true);
chk("all 4 modes exist", ["safe", "editorial", "fashion", "nsfw"].every((k) => CONTENT_MODES[k]));

console.log(`\n${fail ? "FAILED " + fail : "ALL PASS"} (${pass} passed)`);
process.exit(fail ? 1 : 0);
