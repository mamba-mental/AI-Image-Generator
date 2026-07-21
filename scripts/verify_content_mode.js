/* Acceptance verifier for Job 2 (.dd/content-mode-toggle-contract.md).
   Exercises the SHIPPED web/content_mode.js against real catalog models. Node: `node scripts/verify_content_mode.js` */
const fs = require("fs");
const path = require("path");
const { applyContentMode, isRelaxable, CONTENT_MODES, modelMaxTolerance,
        gradeInfo, isVerifiedGraded, isExcludedGraded } =
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
chk("content_capability=permissive -> relaxable", isRelaxable({ id: "z", params: [], content_capability: "permissive" }, "fal") === true);
chk("content_capability=upstream_moderated -> NOT relaxable", isRelaxable({ id: "fal-ai/nano-banana", params: [], content_capability: "upstream_moderated" }, "fal") === false);
chk("all 4 modes exist", ["safe", "editorial", "fashion", "nsfw"].every((k) => CONTENT_MODES[k]));

// Phase 3 — per-provider disable-safety polarity (research §Providers)
const bare = { id: "x", params: [] };
chk("together NSFW -> disable_safety_checker=true", applyContentMode({}, bare, "nsfw", "together").disable_safety_checker === true);
chk("together safe -> disable_safety_checker=false", applyContentMode({}, bare, "safe", "together").disable_safety_checker === false);
chk("runware NSFW -> checkNSFW=false (allow)", applyContentMode({}, bare, "nsfw", "runware").checkNSFW === false);
chk("runware safe -> checkNSFW=true (moderate)", applyContentMode({}, bare, "safe", "runware").checkNSFW === true);
chk("novita NSFW -> enable_nsfw_detection=false (allow)", applyContentMode({}, bare, "nsfw", "novita").enable_nsfw_detection === false);
chk("novita safe -> enable_nsfw_detection=true (moderate)", applyContentMode({}, bare, "safe", "novita").enable_nsfw_detection === true);
chk("runware is relaxable", isRelaxable(bare, "runware") === true);
chk("novita is relaxable", isRelaxable(bare, "novita") === true);

// Spec B §3 — evidence-graded per-model content grading, EVERY provider
const grades = {
  models: {
    "together:verified-model": { grade: "verified", nsfw_votes: "3/3" },
    "novita:tested-negative": { grade: "refused", nsfw_votes: "0/3" },
  },
  exclusion_rules: [{ id_pattern: "kontext", reason: "BFL-proprietary", policy_source_url: "https://docs.bfl.ai/" }],
};
chk("gradeInfo: excluded-by-rule wins over evidence",
  gradeInfo({ id: "fal-ai/flux-pro/kontext" }, "fal", grades).state === "excluded");
chk("isExcludedGraded true for a rule match", isExcludedGraded({ id: "x/kontext/y" }, "fal", grades) === true);
chk("gradeInfo: verified from evidence (non-fal)",
  gradeInfo({ id: "verified-model" }, "together", grades).state === "verified");
chk("isVerifiedGraded true for that evidence row", isVerifiedGraded({ id: "verified-model" }, "together", grades) === true);
chk("gradeInfo: tested-but-not-confirmed -> untested (never assumed permissive, AC-3.1)",
  gradeInfo({ id: "tested-negative" }, "novita", grades).state === "untested");
chk("gradeInfo: zero evidence -> untested",
  gradeInfo({ id: "never-swept" }, "runware", grades).state === "untested");
chk("gradeInfo: same id on a DIFFERENT (unswept) provider is untested, not verified",
  gradeInfo({ id: "verified-model" }, "novita", grades).state === "untested");

console.log(`\n${fail ? "FAILED " + fail : "ALL PASS"} (${pass} passed)`);
process.exit(fail ? 1 : 0);
