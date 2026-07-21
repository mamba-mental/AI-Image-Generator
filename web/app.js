/* AI Studio Void — front-end state + bridge wiring. No frameworks, no network. */
"use strict";

const $ = (id) => document.getElementById(id);

// category chips derive from the catalog; this is just the label map
const CAT_LABELS = {
  "text-to-image": "Image", "image-to-image": "Img→Img",
  "text-to-video": "Video", "image-to-video": "Img→Video",
  "video-to-video": "Vid→Vid", "audio-to-video": "Aud→Vid",
  "text-to-audio": "Audio", "audio-to-audio": "Aud→Aud", "video-to-audio": "Vid→Aud",
  "text-to-speech": "TTS", "speech-to-speech": "Voice→Voice",
  "speech-to-text": "STT", "audio-to-text": "Aud→Txt",
  "video-to-text": "Vid→Txt", "image-to-text": "Caption", "vision": "Vision",
  "text-to-3d": "3D", "image-to-3d": "Img→3D", "3d-to-3d": "3D→3D",
  "upscale": "Upscale", "bg-removal": "BG", "music": "Music", "tts": "TTS",
};
const CAT_ORDER = Object.keys(CAT_LABELS);
function catList() {
  const present = [...new Set(state.falModels.map(m => m.category))];
  present.sort((a, b) => (CAT_ORDER.indexOf(a) + 99 * (CAT_ORDER.indexOf(a) < 0)) -
                         (CAT_ORDER.indexOf(b) + 99 * (CAT_ORDER.indexOf(b) < 0)));
  return present.map(k => ({ key: k, label: CAT_LABELS[k] || k }));
}
const INPUT_KINDS = { needs_input_image: "image", needs_input_video: "video",
                      needs_input_audio: "audio", needs_input_mesh: "mesh" };
const SVC_LABELS = { fal: "Fal", openai: "OpenAI", nvidia: "NVIDIA", replicate: "Replicate", huggingface: "HF", gemini: "Gemini", openrouter: "OpenRouter", together: "Together", runware: "Runware", novita: "Novita", cliproxy: "CLIProxy", agnes: "AGNES-AI", civitai: "CivitAI", ideogram: "Ideogram", "ideogram-api": "Ideogram (API)", "ideogram-web": "Ideogram (Sub)" };

// legacy param set for replicate / hf / gemini (ported from the CTk panel)
const LEGACY_PARAMS = [
  { name: "width", type: "int", default: 1024, min: 256, max: 2048, step: 64 },
  { name: "height", type: "int", default: 1024, min: 256, max: 2048, step: 64 },
  { name: "num_inference_steps", type: "int", default: 28, min: 1, max: 100 },
  { name: "guidance_scale", type: "float", default: 7.5, min: 0, max: 20, step: 0.5 },
  { name: "num_outputs", type: "int", default: 1, min: 1, max: 4 },
  { name: "seed", type: "int", optional: true },
];

const state = {
  services: [], keys: {}, falModels: [], serviceParams: {}, recentModels: {}, novitaModelApis: [], lastUsed: {}, modelSchemas: {},
  service: "fal", category: "text-to-image", model: null,
  inputFiles: {}, job: null, gallery: [], selected: null,
  genCount: 0, loras: {}, mediaBase: "", outDirName: "generated_images",
  view: "session", grid: "m", lbFile: null, lbDir: "", lbTags: [], lbList: null, lbIndex: -1, contentMode: "safe", verifiedOnly: false,
  contentGrades: {}, aspectPreset: "Custom", modelMeta: {},
  novitaCovers: {}, openrouterDescriptions: {}, sweepThumbs: {},
  libRecords: [], libFiltered: [], libraryDirs: [], libFilter: { folder: "", service: "", type: "", q: "", tags: [] },
  libTileEls: null,   // Map<rkey, tileEl> for the library grid — built ONCE per record set, never
                       // rebuilt on filter (perf fix, see buildLibTiles/syncLibTileVisibility below)
};

/* ---------- bridge helpers ---------- */
const api = () => window.pywebview.api;

async function boot() {
  const s = await api().get_state();
  state.services = s.services;
  state.keys = s.keys_status;
  state.keyPools = s.key_pools || {};
  state.falModels = s.fal_models;
  state.serviceParams = s.service_params || {};
  state.contentGrades = s.content_grades || {};  // Spec B §3 sweep evidence — every provider
  state.recentModels = s.recent_models;
  state.novitaModelApis = s.novita_model_apis || [];  // E2 — Novita's second catalog (offline seed)
  state.sweepThumbs = s.sweep_thumbs || {};  // gap-report — real sample renders, card-grid fallback #2
  state.loras = s.loras || {};
  state.mediaBase = s.media_base || "";
  state.outDirName = s.output_dir_name || "generated_images";
  state.outDir = s.output_dir || "";
  state.libraryDirs = s.library_dirs || [];
  state.defaultSize = (s.config || {}).default_image_size || "";
  state.service = s.active_service || "fal";
  const cfg = s.config || {};
  state.lastUsed = {
    fal: cfg.last_used_model_fal, replicate: cfg.last_used_model_replicate,
    huggingface: cfg.last_used_model_hf, gemini: cfg.last_used_model_gemini,
  };
  // start on the category of the last-used fal model so the select matches
  const lastFal = state.falModels.find(m => m.id === state.lastUsed.fal);
  if (state.service === "fal" && lastFal) state.category = lastFal.category;
  if (cfg.ui_theme) setTheme(cfg.ui_theme, false);
  if (cfg.ui_layout) setLayout(cfg.ui_layout, false);
  if (cfg.ui_grid) setGrid(cfg.ui_grid, false);
  // content mode: new key wins; migrate the legacy binary (ui_nsfw true -> editorial, false -> safe)
  state.contentMode = cfg.ui_content_mode ||
    (cfg.ui_nsfw === false ? "safe" : cfg.ui_nsfw === true ? "editorial" : "safe");
  state.verifiedOnly = !!cfg.ui_verified_only;
  if (cfg.parameters && cfg.parameters.negative_prompt) $("negprompt").value = cfg.parameters.negative_prompt;
  $("conn").classList.remove("off");
  $("connlabel").textContent = Object.entries(state.keys)
    .map(([k, ok]) => `${k}:${ok ? "✓" : "✗"}`).join(" ");
  // version badge — always know WHICH build is running (kills stale-exe confusion)
  const vb = $("verbadge"); if (vb && s.version) vb.textContent = s.version;
  // drive-fallback banner — never silently write to a dead drive
  const bnr = $("drivebanner");
  if (bnr) {
    if (s.drive_fallback) {
      bnr.textContent = `⚠ Image drive ${s.drive_fallback.wanted} is not mounted — saving to ${s.drive_fallback.using} for now. Mount the drive and restart to use it.`;
      bnr.style.display = "block";
    } else { bnr.style.display = "none"; }
  }
  renderService();
  render();
  refreshBalance();
  await loadPresets(true);   // Presets (#4) — load + apply any launch defaults (AC-4.2)
}

/* ---------- pickers (layout + theme) ---------- */
function setLayout(name, persist = true) {
  document.documentElement.dataset.layout = name;
  document.querySelectorAll("#layoutpick button").forEach(b => b.classList.toggle("on", b.dataset.layout === name));
  if (persist) api().set_config({ ui_layout: name });
}
function setTheme(name, persist = true) {
  document.documentElement.dataset.theme = name;
  document.querySelectorAll("#themepick button").forEach(b => b.classList.toggle("on", b.dataset.theme === name));
  if (persist) api().set_config({ ui_theme: name });
}
$("layoutpick").addEventListener("click", e => { const b = e.target.closest("button"); if (b) setLayout(b.dataset.layout); });
$("themepick").addEventListener("click", e => { const b = e.target.closest("button"); if (b) setTheme(b.dataset.theme); });

/* ---------- #2 grid size (S/M/L, persisted) ---------- */
function applyGrid() {
  ["gallery", "library", "libmason"].forEach(id => { const el = $(id); if (el) el.dataset.grid = state.grid; });
  document.querySelectorAll(".wmason, .mstrip").forEach(el => { el.dataset.grid = state.grid; });
}
function setGrid(name, persist = true) {
  state.grid = name;
  document.querySelectorAll("#gridpick button").forEach(b => b.classList.toggle("on", b.dataset.grid === name));
  applyGrid();
  if (persist) api().set_config({ ui_grid: name });
}
$("gridpick").addEventListener("click", e => { const b = e.target.closest("button"); if (b) setGrid(b.dataset.grid); });

// #3 — hand the current prompt off to the existing Prompt Refinery (clipboard + open)
$("refinerybtn").addEventListener("click", async () => {
  const p = $("prompt").value.trim();
  if (p) { try { await navigator.clipboard.writeText(p); } catch (e) { /* clipboard may be blocked */ } }
  api().open_prompt_refinery(p);
  $("statusmsg").textContent = p ? "prompt copied — paste into Prompt Refinery" : "opening Prompt Refinery…";
});

/* ---------- settings modal (API keys) ---------- */
const KEY_HINTS = {
  fal: "FAL_KEY · fal.ai/dashboard/keys",
  together: "TOGETHER_API_KEY · api.together.xyz/settings/api-keys (uncensored open models)",
  runware: "RUNWARE_API_KEY · runware.ai → dashboard → API keys (uncensored + CivitAI)",
  novita: "NOVITA_API_KEY · novita.ai/settings/key-management (uncensored, opt-in NSFW)",
  replicate: "REPLICATE_API_TOKEN · replicate.com/account/api-tokens",
  openai: "OPENAI_API_KEY · platform.openai.com/api-keys",
  nvidia: "NVIDIA_API_KEY · build.nvidia.com (nvapi-…)",
  huggingface: "HUGGINGFACE_TOKEN · huggingface.co/settings/tokens",
  gemini: "GEMINI_API_KEY · aistudio.google.com/apikey (free)",
  cliproxy: "CLIPROXY_API_KEY · your cliproxy gateway",
  agnes: "AGNES_API_KEY · platform.agnes-ai.com/settings/profile",
  ideogram: "IDEOGRAM_WEB_REFRESH_TOKEN · ideogram.ai subscription session",
  "ideogram-api": "IDEOGRAM_API_KEY · ideogram.ai/manage-api (Api-Key)",
  civitai: "CIVITAI_API_KEY · civitai.com/user/account (LoRA browse)",
  openrouter: "OPENROUTER_API_KEY · openrouter.ai/keys (sk-or-v1-…)",
};
// media-first order; every KEY_FIELDS provider from get_state().keys_status is shown
const KEY_ORDER = ["fal", "together", "runware", "novita", "replicate", "openai", "nvidia",
                   "huggingface", "gemini", "cliproxy", "agnes", "ideogram", "ideogram-api", "civitai", "openrouter"];
function renderKeyRows() {
  const provs = Object.keys(state.keys || {}).sort((a, b) => {
    const ia = KEY_ORDER.indexOf(a), ib = KEY_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  $("keyrows").innerHTML = provs.map(s => `
    <div class="keyrow" data-svc="${s}">
      <div class="keyrow-head">
        <span class="svc-name">${SVC_LABELS[s] || s}</span>
        <span class="status ${state.keys[s] ? "set" : "unset"}" data-status>${state.keys[s] ? "key set" : "not set"}${(state.keyPools && state.keyPools[s] > 1) ? ` · ${state.keyPools[s]} keys (auto-swap)` : ""}</span>
      </div>
      <div class="keyrow-in">
        <input type="password" placeholder="paste new ${SVC_LABELS[s] || s} key to override…" data-keyin>
        <button data-save>Save &amp; Validate</button>
        <button data-check title="check the key already in use, without changing it">Check current</button>
      </div>
      <div class="hint">${KEY_HINTS[s] || ""}</div>
    </div>`).join("");

  $("keyrows").querySelectorAll(".keyrow").forEach(row => {
    const s = row.dataset.svc;
    const status = row.querySelector("[data-status]");
    const input = row.querySelector("[data-keyin]");
    const setStatus = (cls, txt) => { status.className = "status " + cls; status.textContent = txt; };

    // ONE save path — always persists then validates (no "validated but not saved" trap)
    row.querySelector("[data-save]").addEventListener("click", async () => {
      if (!input.value.trim()) { setStatus("invalid", "enter a key first"); return; }
      setStatus("checking", "saving…");
      const r = await api().save_and_validate_key(s, input.value);
      state.keys = r.keys_status;
      const v = r.validation;
      const cls = v.valid === true ? "valid" : v.valid === null ? "set" : "invalid";
      const txt = v.valid === true ? `saved · valid (${v.http})`
                : v.valid === null ? `saved · ${v.detail}`
                : `saved · ${v.detail} (${v.http})`;
      setStatus(cls, txt);
      input.value = "";
      renderService();            // reflect new key state in the dropdown immediately
      if (s === "novita") { state._novitaFetched = false; render(); }  // load the live Novita catalog now the key exists
      if (s === state.service) refreshBalance();
    });
    // read-only check of the key already in use (does not save)
    row.querySelector("[data-check]").addEventListener("click", async () => {
      setStatus("checking", "checking…");
      const r = await api().validate_key(s, "");
      setStatus(r.valid ? "valid" : "invalid", r.valid ? `valid (${r.http})` : `${r.detail} (${r.http})`);
    });
  });
}
function renderPrefs() {
  const od = $("pref-outdir"); if (od) od.value = state.outDir || "";
  const note = $("pref-outdir-note"); if (note) note.textContent = state.outDirName ? `current: ${state.outDir}` : "";
  const sz = $("pref-size"); if (sz) sz.value = state.defaultSize || "";
}
$("pref-outdir-save") && $("pref-outdir-save").addEventListener("click", async () => {
  const v = $("pref-outdir").value.trim();
  const note = $("pref-outdir-note");
  if (!v) { if (note) note.textContent = "enter a folder path first"; return; }
  if (note) note.textContent = "saving…";
  await api().set_config({ output_directory: v });
  const s = await api().get_state();   // re-read (media server repointed + fallback check)
  state.outDir = s.output_dir || v; state.outDirName = s.output_dir_name || "";
  if (note) note.textContent = s.drive_fallback
    ? `⚠ ${s.drive_fallback.wanted} unavailable — using ${s.drive_fallback.using}`
    : `saved · now saving to ${s.output_dir}`;
});
$("pref-size") && $("pref-size").addEventListener("change", async e => {
  state.defaultSize = e.target.value;
  await api().set_config({ default_image_size: e.target.value });
});
$("settingsbtn").addEventListener("click", () => { renderKeyRows(); renderPrefs(); $("settings").hidden = false; });
$("settingsclose").addEventListener("click", () => { $("settings").hidden = true; });
$("settings").addEventListener("click", e => { if (e.target.id === "settings") $("settings").hidden = true; });

/* ---------- model catalog ---------- */
// per-service param schema (retires LEGACY_PARAMS): a dynamically-fetched per-model schema wins,
// else the service's service_params.json entry (by_id_contains match, else default), else LEGACY_PARAMS.
// fetch a live per-model Input schema for services that expose one (replicate); cache + re-render once.
// P3 — the SAME call also carries description/cover_image_url for replicate/openrouter/novita
// (bridge.model_schema()), cached separately into state.modelMeta so it never fights the params cache.
async function maybeFetchSchema(service, id) {
  if (!["replicate", "openrouter", "novita"].includes(service) || !id) return;
  const wantParams = service === "replicate" && !(id in state.modelSchemas);
  const wantMeta = !(id in state.modelMeta);
  if (!wantParams && !wantMeta) return;  // both already fetched or in-flight
  if (wantParams) state.modelSchemas[id] = null;  // in-flight marker (falls back to service default meanwhile)
  if (wantMeta) state.modelMeta[id] = null;
  try {
    const r = await api().model_schema(service, id);
    if (wantParams && r && r.params && r.params.length) state.modelSchemas[id] = r.params;
    if (wantMeta) state.modelMeta[id] = (r && (r.description || r.cover_image_url))
      ? { description: r.description, cover_image_url: r.cover_image_url } : {};
    render();
  } catch (e) { /* fall back to the service default params / no meta */ }
}
// Live Novita checkpoint catalog -> the model dropdown (so exact names are never guessed).
// One-shot on success; retries while empty (e.g. before the key is added). No refetch loop.
async function maybeFetchNovitaModels() {
  if (state.service !== "novita" || state._novitaFetched || state._novitaFetching) return;
  state._novitaFetching = true;
  try {
    const names = await api().novita_models(100);
    if (names && names.length) { state._novitaFetched = true; state.recentModels.novita = names; render(); }
  } catch (e) { /* keep the seeded fallback */ }
  finally { state._novitaFetching = false; }
}
// Live catalogs for the OpenAI-compatible providers (issue #1 — dropdowns stop being guesses).
// One-shot per service on success; retries while empty (e.g. before a key is set); on failure the
// labelled offline seeds stay. Novita has its own shape → delegates above.
const CATALOG_SVCS = ["together", "agnes", "nvidia", "openai", "openrouter"];
// Card-grid metadata one-shots (finish of the gap-report card grid): novita cover images +
// openrouter descriptions load once per session when their service first renders.
async function maybeFetchCardMeta() {
  const svc = state.service;
  state._metaFetched = state._metaFetched || {};
  if (state._metaFetched[svc]) return;
  if (svc === "novita") {
    state._metaFetched[svc] = true;
    try { const r = await api().novita_covers(100); if (r && Object.keys(r).length) { state.novitaCovers = r; render(); } } catch (e) {}
  } else if (svc === "openrouter") {
    state._metaFetched[svc] = true;
    try { const r = await api().openrouter_descriptions(); if (r && Object.keys(r).length) { state.openrouterDescriptions = r; render(); } } catch (e) {}
  }
}
async function maybeFetchLiveModels() {
  const svc = state.service;
  maybeFetchCardMeta();  // covers/descriptions ride the same render tick, one-shot
  if (svc === "novita") return maybeFetchNovitaModels();
  if (!CATALOG_SVCS.includes(svc)) return;
  state._catFetched = state._catFetched || {};
  state._catFetching = state._catFetching || {};
  if (state._catFetched[svc] || state._catFetching[svc]) return;
  state._catFetching[svc] = true;
  try {
    const r = await api().provider_models(svc, 300);
    if (r && r.live && r.models && r.models.length) {
      state._catFetched[svc] = true;
      state.recentModels[svc] = r.models;
      render();
    }
  } catch (e) { /* keep the seeded fallback */ }
  finally { state._catFetching[svc] = false; }
}
function pickServiceParams(service, id, category) {
  if (state.modelSchemas[id]) return state.modelSchemas[id];
  const sp = state.serviceParams[service];
  if (!sp) return LEGACY_PARAMS;
  if (sp.by_id_contains) {
    const low = (id || "").toLowerCase();
    for (const sub in sp.by_id_contains) if (low.includes(sub)) return sp.by_id_contains[sub];
  }
  return sp.default || LEGACY_PARAMS;
}
// Card-grid enrichment (gap-report: "fal-style card grid for ALL providers"). Unified shape every
// non-fal model gets: {thumb?, description?, sample?}. Priority order, honest, never fabricated:
// 1) provider-native metadata (novita cover, replicate cover, openrouter description-only)
// 2) our own NSFW-sweep sample render (state.sweepThumbs — local copy preferred server-side,
//    already resolved to a ready-to-use URL; `sample:true` flags it for the card's corner tag)
// 3) a static per-service FAMILY_BLURBS one-liner for description when nothing else exists
// fal is untouched — fal_models.json already carries its own real thumb+description.
function cardMeta(service, id) {
  let thumb = null, description = null, sample = false;
  if (service === "novita" && state.novitaCovers[id]) thumb = state.novitaCovers[id];
  if (service === "replicate" && state.modelMeta[id]) {
    thumb = state.modelMeta[id].cover_image_url || null;
    description = state.modelMeta[id].description || null;
  }
  if (service === "openrouter" && state.openrouterDescriptions[id]) description = state.openrouterDescriptions[id];
  if (!thumb) {
    const sw = state.sweepThumbs[`${service}:${id}`];
    if (sw) { thumb = sw.url; sample = true; }
  }
  if (!description) description = FAMILY_BLURBS[service] || null;
  return { thumb, description, sample };
}
// E2 — Novita ships TWO catalogs (Spec B AC-1.2): legacy checkpoints (live-fetched) + the modern
// Model APIs (no list endpoint -> offline seed, engine/backends/novita_api.MODEL_APIS). Each model
// carries a `group` so the <select> renders them as two labelled optgroups (renderModelOptions).
function novitaModelsFor(category) {
  const checkpoints = (state.recentModels.novita || []).map(id =>
    ({ id, label: id, category: "text-to-image", group: "Novita · Checkpoints", params: pickServiceParams("novita", id, category), ...cardMeta("novita", id) }));
  const modelApis = (state.novitaModelApis || []).map(id =>
    ({ id, label: id, category: "text-to-image", group: "Novita · Model APIs", params: pickServiceParams("novita", id, category), ...cardMeta("novita", id) }));
  return checkpoints.concat(modelApis);
}
function modelsFor(service, category) {
  let models = service === "fal" ? state.falModels.filter(m => m.category === category)
    : service === "novita" ? novitaModelsFor(category)
    : (state.recentModels[service] || []).map(id => ({ id, label: id, category: "text-to-image", params: pickServiceParams(service, id, category), ...cardMeta(service, id) }));
  const prof = CONTENT_MODES[state.contentMode] || CONTENT_MODES.safe;
  if (prof.filter) {  // Editorial/Fashion/NSFW: evidence-graded per model, for EVERY provider (Spec B AC-3.1/3.2)
    const grades = state.contentGrades;
    models = models.filter(m => gradeInfo(m, service, grades).state !== "excluded");  // rule-excluded hidden always
    if (state.verifiedOnly) {
      models = models.filter(m => isVerifiedGraded(m, service, grades));              // "Verified only" narrows cross-provider
    } else if (service === "fal") {
      models = models.filter(m => isRelaxable(m, service));                          // fal keeps its richer legacy heuristic too
    }
    // non-fal, not verified-only: untested models still shown-with-caveat (AC-3.2 default)
  }
  if (prof.fashionFirst) {
    models = models.slice().sort((a, b) => (isFashionModel(b) ? 1 : 0) - (isFashionModel(a) ? 1 : 0));
  }
  return models;
}
function currentModel() {
  const models = modelsFor(state.service, state.category);
  return models.find(m => m.id === state.model)
      || models.find(m => m.id === state.lastUsed[state.service])
      || models[0] || null;
}

/* ---------- §4 model suggestion box (issue: "which model?") ---------- */
// Every model across the providers you can ACTUALLY access (keyed), from the loaded catalogs.
// Grows as you visit providers (each one-shot-fetches its live list). Never suggests a model
// behind a provider you have no key for.
function accessibleModels() {
  const out = [];
  for (const svc of state.services) {
    if (!state.keys[svc]) continue;               // only providers with a key = actually reachable
    const list = svc === "fal" ? state.falModels.filter(m => m.category === "text-to-image")
      : svc === "novita" ? (state.recentModels[svc] || []).concat(state.novitaModelApis || []).map(id => ({ id, label: id }))
      : (state.recentModels[svc] || []).map(id => ({ id, label: id }));
    for (const m of list) out.push({ id: m.id, label: m.label || m.id, service: svc });
  }
  return out;
}
function renderModelSuggest() {
  const box = $("modelsuggest");
  if (!box) return;
  const q = (($("modelquery") && $("modelquery").value) || "").trim().toLowerCase();
  if (!q) { box.innerHTML = ""; return; }
  const toks = q.split(/\s+/).filter(Boolean);
  const hits = accessibleModels().filter(m => {
    const hay = (m.service + " " + m.id + " " + m.label).toLowerCase();
    return toks.every(t => hay.includes(t));
  }).slice(0, 10);
  box.innerHTML = hits.length
    ? hits.map(m => `<button class="msuggest-chip" data-svc="${m.service}" data-id="${encodeURIComponent(m.id)}"><b>${m.label}</b><span>${m.service}</span></button>`).join("")
    : `<div class="msuggest-empty">no accessible model matches — try another word (or add that provider's key)</div>`;
}

/* ---------- renderers ---------- */
function renderService() {
  $("svc").innerHTML = state.services.map(s =>
    `<option value="${s}" ${s === state.service ? "selected" : ""}>${SVC_LABELS[s] || s}${state.keys[s] ? "" : " (no key)"}</option>`).join("");
}

async function refreshBalance() {
  const el = $("balance");
  el.textContent = "…";
  el.className = "";
  try {
    const b = await api().get_balance(state.service);
    el.textContent = `${SVC_LABELS[state.service] || state.service}: ${b.label}`;
    el.className = "bal-" + (b.kind || "none");
  } catch (e) {
    el.textContent = "";
  }
  refreshAllBalances();   // R3 #6-frontend — footer strip: every provider, not just the active one
}

// R3 #6-frontend — every provider's balance at once, not just the active service. get_balance()
// already dispatches to each backend's real/portal-only/n-a logic (bridge.py::_BALANCE_BACKENDS);
// this just fans that out over every configured service in parallel and renders one chip each.
// Reuses the existing bal-ok/bal-low/bal-info/bal-none color classes — no new CSS.
let _balanceAllInFlight = false;
async function refreshAllBalances() {
  const el = $("balanceall"); if (!el || _balanceAllInFlight) return;
  _balanceAllInFlight = true;
  try {
    const results = await Promise.all(state.services.map(async s => {
      try { return [s, await api().get_balance(s)]; } catch (e) { return [s, { label: "—", kind: "none" }]; }
    }));
    el.innerHTML = results.map(([s, b]) =>
      `<span class="bal-${b.kind || "none"}">${escapeHtml(SVC_LABELS[s] || s)}: ${escapeHtml(b.label)}</span>`
    ).join(" · ");
  } finally {
    _balanceAllInFlight = false;
  }
}
// E2 — <option> list for the model <select>, wrapping contiguous same-`group` runs in an
// <optgroup> (Novita's "Checkpoints" / "Model APIs"). No-op passthrough for ungrouped models.
function renderModelOptions(models, cur) {
  let html = "", curGroup = undefined, open = false;
  for (const m of models) {
    if (m.group !== curGroup) {
      if (open) html += `</optgroup>`;
      open = !!m.group;
      if (open) html += `<optgroup label="${escapeHtml(m.group)}">`;
      curGroup = m.group;
    }
    html += `<option value="${m.id}" ${cur && m.id === cur.id ? "selected" : ""}>${m.label}${m.price ? " — " + m.price : ""}</option>`;
  }
  if (open) html += `</optgroup>`;
  return html;
}

/* ---------- P1 — aspect-preset dropdown (research/2026-07-21_provider-params-matrix.md §15) ----------
   Fully data-driven off engine/service_params.json's per-service `aspect_presets{}` (precomputed by
   the §15 algorithm, one entry per preset key -> the exact value that service's size_mode wants:
   {width,height} for free_wh/fixed_wh_enum_independent, a "WxH" string for enum_wh_string, an
   "R:R"/"RxR" string for enum-native ratio families). No client-side re-derivation of the algorithm —
   the table already encodes it per provider. */
function servicePresetTable(service) {
  const sp = state.serviceParams[service];
  return (sp && sp.aspect_presets) || null;
}
function _parseRatioStr(s) {
  const m = String(s).match(/^(\d+(?:\.\d+)?)\s*[:x]\s*(\d+(?:\.\d+)?)$/i);
  return m ? parseFloat(m[1]) / parseFloat(m[2]) : null;
}
function achievedRatio(val) {
  if (val == null) return null;
  return typeof val === "object" ? val.width / val.height : _parseRatioStr(val);
}
function renderAspectPreset(model) {
  const wrap = $("aspectwrap"), sel = $("aspectpreset");
  if (!wrap || !sel) return;
  const table = servicePresetTable(state.service);
  wrap.style.display = table ? "" : "none";
  if (!table) return;
  const keys = Object.keys(table);
  if (!keys.includes(state.aspectPreset)) state.aspectPreset = "Custom";
  sel.innerHTML = keys.map(k => `<option value="${k}" ${k === state.aspectPreset ? "selected" : ""}>${k}</option>`).join("");
  updateAspectBadge(model);
}
// NEAREST-with-badge policy (§15): badge only when the sent value's true ratio differs from the
// preset's own — never for Custom/Auto (no comparison applies to either).
function updateAspectBadge(model) {
  const badge = $("aspectbadge");
  if (!badge) return;
  const table = servicePresetTable(state.service);
  const preset = state.aspectPreset;
  const want = table && preset !== "Custom" && preset !== "Auto" ? _parseRatioStr(preset) : null;
  const val = table ? table[preset] : null;
  if (want == null || val == null) { badge.textContent = ""; badge.title = ""; return; }
  const got = achievedRatio(val);
  const mismatch = got == null || Math.abs(got - want) > 0.02;
  const sentStr = typeof val === "object" ? `${val.width}×${val.height}` : val;
  badge.textContent = mismatch ? "≈" : "";
  badge.title = mismatch ? `requested ${preset} — this provider sends ${sentStr} (achieved ratio ${got ? got.toFixed(3) : "?"} vs true ${want.toFixed(3)})` : "";
}
function applyAspectPreset(key) {
  state.aspectPreset = key;
  const table = servicePresetTable(state.service);
  updateAspectBadge(currentModel());
  if (!table || key === "Custom") return;  // §15 step 2 — pass the user's own width/height through
  const val = table[key];
  if (key === "Auto") {  // §15 step 3 — a literal "auto" sentinel if the provider has one, else omit
    if (val === "auto") setComposerParam("size", "auto");
    return;
  }
  if (val == null) return;
  if (typeof val === "object") { setComposerParam("width", val.width); setComposerParam("height", val.height); }
  else if (/^\d+x\d+$/i.test(val)) setComposerParam("size", val);   // enum_wh_string (openai/cliproxy/agnes)
  else setComposerParam("aspect_ratio", val);                       // enum-native ratio (gemini/ideogram/openrouter)
}
$("aspectpreset") && $("aspectpreset").addEventListener("change", () => applyAspectPreset($("aspectpreset").value));

/* ---------- P3 — model-info panel (description + cover, where the provider's catalog has one) ---------- */
// One-line honest family blurbs for providers with no per-model description API (cites the matrix).
const FAMILY_BLURBS = {
  openai: "OpenAI gpt-image family — enum size (auto/1024²/1536×1024/1024×1536), quality + background control (params matrix §1).",
  cliproxy: "Self-hosted OpenAI-compat proxy to the same gpt-image family as OpenAI, one hop removed (params matrix §2).",
  gemini: "Gemini image models — closed 10-value aspect-ratio enum + a 1K/2K/4K resolution tier, no free width/height (params matrix §3).",
  together: "Together.ai FLUX family — free width/height, steps + guidance_scale, optional LoRA on FLUX.1-dev-lora/FLUX.2-dev (params matrix §5).",
  huggingface: "HF Inference — forwards to whichever provider backs the chosen model; ranges are genuinely per-model, not a fixed contract (params matrix §8).",
  ideogram: "Ideogram v3 — native aspect_ratio/resolution enum, rendering-speed + style-type controls, magic prompt (params matrix §9).",
  agnes: "AGNES-AI (Sapiens) — OpenAI-compatible image + async video, sparse public docs (params matrix §10).",
  nvidia: "NVIDIA NIM (FLUX.1-dev/schnell, SD3.5-large) — width/height locked to a shared 10-value enum, no negative_prompt field exists (params matrix §4).",
  runware: "Runware — single array-of-tasks POST, mixed-case fields (CFGScale/positivePrompt), model-dependent size bounds (params matrix §7).",
};
function renderModelInfo(model) {
  const box = $("modelinfo");
  if (!box) return;
  const meta = model && state.modelMeta[model.id];
  if (meta && (meta.description || meta.cover_image_url)) {
    box.innerHTML = (meta.cover_image_url ? `<img src="${meta.cover_image_url}" alt="" loading="lazy" style="max-width:100%;border-radius:4px;display:block;margin-bottom:6px">` : "")
      + (meta.description ? `<span>${escapeHtml(meta.description)}</span>` : "");
    box.hidden = false;
    return;
  }
  const blurb = FAMILY_BLURBS[state.service];
  if (blurb) { box.innerHTML = `<span>${escapeHtml(blurb)}</span>`; box.hidden = false; return; }
  box.hidden = true;
}

function render() {
  const isFal = state.service === "fal";
  // categories only meaningful for fal; legacy services are t2i (+img via uploader)
  $("cats").style.display = isFal ? "" : "none";
  if (!isFal) state.category = "text-to-image";
  else if (!state.falModels.some(m => m.category === state.category)) state.category = "text-to-image";
  $("cats").innerHTML = (isFal ? catList() : [])
    .map(c => `<button class="chip ${c.key === state.category ? "on" : ""}" data-c="${c.key}">${c.label}</button>`).join("");

  const models = modelsFor(state.service, state.category);
  const cur = currentModel();
  state.model = cur ? cur.id : null;
  if (cur) maybeFetchSchema(state.service, cur.id);  // live per-model schema for replicate (re-renders when it lands)
  maybeFetchLiveModels();  // live catalog into the dropdown (novita + openai-compat providers, one-shot)
  renderModelSuggest();    // keep the §4 suggestion results fresh as catalogs load
  $("model").innerHTML = renderModelOptions(models, cur);
  $("pricenote").textContent = cur && cur.price ? cur.price : "";
  $("estcost").textContent = cur && cur.price ? "est " + cur.price : "";
  $("modellabel").textContent = cur ? cur.label || cur.id : "";
  $("hdrinfo").textContent = `${state.service} · ${cur ? (cur.label || cur.id) : "—"}`;

  renderInputPickers(cur);
  renderPromptGuide(cur);
  renderModelInfo(cur);       // P3 — description/cover (dynamic) or a family blurb (static)
  // #12 — negative prompt only where the family actually uses it (FLUX/gpt-image/nano-banana hide it)
  const fam = PROMPT_GUIDE[modelFamily(cur && cur.id)] || PROMPT_GUIDE.generic;
  $("negwrap").style.display = fam.neg ? "" : "none";
  renderParams(cur);
  renderAspectPreset(cur);    // P1 — must run AFTER renderParams so its width/height/size controls exist
  renderNsfw(cur);
  renderLoras();
  if (state.view === "session") renderGallery();  // refresh stage (browse landing or session gallery)
}

// #6 param help (verbatim fal OpenAPI descriptions -> plain-English) + #5 safety-tolerance labels
const PARAM_HELP = {
  sync_mode: "Returns the image inline as a data URI instead of a hosted URL — displays instantly but is NOT saved to history. Leave off for normal saved generations.",
  acceleration: "How aggressively to speed up generation. none = best quality/slowest · regular = balanced · high = fastest/slightly lower quality.",
  guidance_scale: "How strictly the image follows your prompt (CFG). Low 1–3 = looser/more creative; high 7–12 = literal. FLUX defaults ~3.5.",
  num_inference_steps: "Denoising passes — more = more detail but slower. Schnell needs ~4; dev defaults to 28.",
  image_size: "Output dimensions. square_hd=1024², square=512², portrait/landscape 4:3 & 16:9 — or set custom width+height.",
  output_format: "File type. jpeg = smaller · png = lossless + transparency · webp = small + transparency (some models).",
  enable_prompt_expansion: "Runs an LLM to expand your prompt with extra detail while keeping its meaning. Off = your prompt verbatim.",
  num_images: "How many images to generate in one run.",
  seed: "Fixes the random seed for reproducible output. Blank = random each run.",
  enable_safety_checker: "ON blocks explicit/NSFW output. Turn OFF for artistic/editorial nudity on fal models that allow it.",
  safety_tolerance: "How permissive the content filter is (1 strictest … 6 most permissive). Higher allows more artistic/implied nudity.",
  negative_prompt: "What to avoid (SDXL/Seedream/Imagen). FLUX/gpt-image ignore this — put exclusions in the prompt instead.",
  width: "Custom output width in pixels (overrides the size preset when both width+height are set).",
  height: "Custom output height in pixels (overrides the size preset when both width+height are set).",
};
const SAFETY_LABELS = {
  "1": "1 — Strictest (blocks most; even mild artistic-nude framing rejected)",
  "2": "2 — Strict (FLUX Pro default; blocks nudity + most suggestive)",
  "3": "3 — Moderate (some suggestive allowed)",
  "4": "4 — Relaxed (implied/artistic nudity often allowed)",
  "5": "5 — Permissive (artistic nudity allowed)",
  "6": "6 — Most permissive (minimal filtering)",
};

// #1 — in-app content-policy reference (provider -> policy -> required config).
// Grounded in a provider-capability audit; hard-filter providers cannot be overridden.
const NSFW_POLICY = [
  { p: "fal", allow: "yes", policy: "Model-graded: open-weights bases (flux/SDXL/SD3.5/HiDream/…) are permissive; Google/OpenAI-backed (nano-banana, gemini, gpt-image) are excluded — they moderate upstream regardless.",
    config: "content_capability grades each model verified/permissive/upstream_moderated/filtered. Editorial/NSFW show permissive+verified; “Verified only” narrows to models empirically confirmed to produce NSFW." },
  { p: "huggingface", allow: "partial", policy: "Model-dependent; many SDXL/community checkpoints are uncensored.",
    config: "Steer with negative_prompt; safety governed per-request by the Content Mode where the model exposes a toggle." },
  { p: "replicate", allow: "yes", policy: "Most image models expose disable_safety_checker.",
    config: "disable_safety_checker=true sent by the replicate backend (permissive)." },
  { p: "gemini", allow: "no", policy: "Hard filter — nudity blocked, no override.", config: "n/a (provider-enforced)." },
  { p: "nvidia", allow: "no", policy: "Hard filter — no override.", config: "n/a (provider-enforced)." },
  { p: "openai", allow: "no", policy: "Hard no — gpt-image refuses explicit content.", config: "n/a (provider-enforced)." },
];
function modelSafetyParams(model) {
  const names = new Set(((model && model.params) || []).map(p => p.name));
  return { checker: names.has("enable_safety_checker"), tolerance: names.has("safety_tolerance") };
}

/* Content Mode logic (CONTENT_MODES / applyContentMode / isRelaxable / …) lives in
   web/content_mode.js — loaded before this file, exposed as window globals. */

// #12 — per-family canonical prompting guidance + negative-prompt gating (from a provider audit).
function modelFamily(id) {
  const s = (id || "").toLowerCase();
  if (s.includes("flux")) return "flux";
  if (s.includes("nano-banana")) return "nano-banana";
  if (s.includes("gpt-image") || s.includes("dall-e")) return "gpt-image";
  if (s.includes("imagen")) return "imagen";
  if (s.includes("seedream") || s.includes("seedance")) return "seedream";
  if (s.includes("kling") || s.includes("veo") || s.includes("wan") || s.includes("-video")) return "video";
  if (s.includes("sdxl") || s.includes("stable-diffusion")) return "sdxl";
  return "generic";
}
const PROMPT_GUIDE = {
  flux: { tip: "FLUX — natural descriptive sentences; no weight syntax, no negative prompt. Put exclusions IN the prompt (\"no text, no watermark\"). Strong on scene + style + lighting detail.", neg: false, src: "fal FLUX docs" },
  "nano-banana": { tip: "Nano-Banana (Gemini image) — conversational edit-style instructions; describe the change/scene plainly. No negative prompt.", neg: false, src: "fal nano-banana" },
  "gpt-image": { tip: "gpt-image — plain descriptive prompt; the model handles composition. No negative prompt: describe what you want, not what to avoid.", neg: false, src: "OpenAI Images" },
  imagen: { tip: "Imagen — descriptive prompt + optional negative_prompt to exclude elements; responds to style/quality descriptors.", neg: true, src: "Google Imagen" },
  seedream: { tip: "Seedream/Seedance — prompt + negative_prompt supported; responds well to cinematic + camera terms.", neg: true, src: "fal Seedream" },
  sdxl: { tip: "SDXL — prompt + strong negative_prompt (comma tags). Weighted terms (word:1.2) work; use negatives for quality (\"blurry, extra fingers\").", neg: true, src: "SDXL" },
  video: { tip: "Video (Kling/Veo/Wan) — describe motion + camera + subject; negative_prompt supported to suppress artifacts.", neg: true, src: "fal video" },
  generic: { tip: "Describe subject, style, composition, and lighting clearly.", neg: true, src: "" },
};
function renderPromptGuide(model) {
  const g = PROMPT_GUIDE[modelFamily(model && model.id)] || PROMPT_GUIDE.generic;
  $("promptguide").innerHTML = `<span class="pg-tip">${escapeHtml(g.tip)}</span>${g.src ? `<span class="pg-src">ref: ${g.src}</span>` : ""}`;
}

function paramControl(p) {
  const v = p.default !== undefined ? p.default : "";
  if (p.type === "enum") {
    const lbl = p.name === "safety_tolerance" ? SAFETY_LABELS : null;
    return `<select data-p="${p.name}">${p.values.map(x => `<option value="${x}" ${x === p.default ? "selected" : ""}>${lbl && lbl[String(x)] ? lbl[String(x)] : x}</option>`).join("")}</select>`;
  }
  if (p.type === "bool")
    return `<input type="checkbox" data-p="${p.name}" ${p.default ? "checked" : ""}>`;
  if (p.type === "int" || p.type === "float") {
    if (p.optional) return `<input type="number" data-p="${p.name}" placeholder="random">`;
    const min = p.min !== undefined ? p.min : 0, max = p.max !== undefined ? p.max : (p.type === "int" ? 100 : 20);
    const step = p.step !== undefined ? p.step : (p.type === "float" ? 0.1 : 1);
    return `<input type="range" data-p="${p.name}" min="${min}" max="${max}" step="${step}" value="${v}">
            <span class="val" data-v="${p.name}">${v}</span>`;
  }
  return `<input type="text" data-p="${p.name}" placeholder="${p.optional ? "optional" : ""}">`;
}
function renderParams(model) {
  const params = model && model.params ? model.params : LEGACY_PARAMS;
  $("params").innerHTML = params.map(p => {
    const help = p.description || PARAM_HELP[p.name] || "";  // schema-driven help; hand-authored fallback
    const info = help ? ` <span class="phelp" title="${help.replace(/"/g, "&quot;")}">&#9432;</span>` : "";
    return `<div class="prow"><span title="${help.replace(/"/g, "&quot;")}">${p.name.replace(/_/g, " ")}${info}</span>${paramControl(p)}</div>`;
  }).join("");
  // Settings → "Default image size" pref: pre-fill width/height/size when the model exposes them
  if (state.defaultSize && /^\d+x\d+$/.test(state.defaultSize)) {
    const [w, h] = state.defaultSize.split("x");
    const setP = (name, val) => {
      const el = $("params").querySelector(`[data-p="${name}"]`);
      if (el && val) { el.value = val; const vs = $("params").querySelector(`[data-v="${name}"]`); if (vs) vs.textContent = val; }
    };
    setP("width", w); setP("height", h);
    setP("size", state.defaultSize); setP("image_size", state.defaultSize);
  }
  $("params").querySelectorAll("input[type=range]").forEach(r =>
    r.addEventListener("input", () => {
      const out = $("params").querySelector(`[data-v="${r.dataset.p}"]`);
      if (out) out.textContent = r.value;
    }));
}
function collectParams(model) {
  const out = {};
  const defs = Object.fromEntries(((model && model.params) || LEGACY_PARAMS).map(p => [p.name, p]));
  $("params").querySelectorAll("[data-p]").forEach(el => {
    const def = defs[el.dataset.p] || {};
    let v;
    if (el.type === "checkbox") v = el.checked;
    else if (el.value === "") return;
    else if (def.type === "int") v = parseInt(el.value, 10);
    else if (def.type === "float") v = parseFloat(el.value);
    else v = el.value;
    out[el.dataset.p] = v;
  });
  const neg = $("negprompt").value.trim();
  if (neg && $("negwrap").style.display !== "none") out.negative_prompt = neg;
  return out;
}

/* ---------- #1 NSFW / content-policy toggle + reference ---------- */
function syncSafetyControls() {
  // mirror the active mode's safety values into the visible param controls so the form reflects it
  const applied = applyContentMode({}, currentModel(), state.contentMode, state.service);
  const set = (name, val) => {
    const el = $("params").querySelector(`[data-p="${name}"]`);
    if (!el) return;
    if (el.type === "checkbox") el.checked = !!val; else el.value = String(val);
    const vs = $("params").querySelector(`[data-v="${name}"]`); if (vs) vs.textContent = String(val);
  };
  ["enable_safety_checker", "enable_output_safety_checker", "safety_tolerance", "raw"].forEach(k => {
    if (k in applied) set(k, applied[k]);
  });
}
function nsfwNote() {
  $("nsfwnote").textContent = CONTENT_MODE_HELP[state.contentMode] || "";
}
function renderContentMode() {
  $("nsfwwrap").style.display = "";                    // shown for every service
  const seg = $("cmodeseg");
  if (seg) seg.querySelectorAll("button").forEach(b =>
    b.classList.toggle("active", b.dataset.mode === state.contentMode));
  const prof = CONTENT_MODES[state.contentMode] || CONTENT_MODES.safe;
  const vw = $("verifiedwrap");
  if (vw) vw.style.display = prof.filter ? "" : "none";   // "verified only" only in Editorial/Fashion/NSFW
  const vo = $("verifiedonly"); if (vo) vo.checked = state.verifiedOnly;
  const cc = $("cmodecount");
  if (cc) {
    if (prof.filter) {
      const svc = state.service;
      const all = svc === "fal"
        ? state.falModels.filter(m => m.category === state.category)
        : (state.recentModels[svc] || []).map(id => ({ id }));
      const verified = all.filter(m => isVerifiedGraded(m, svc, state.contentGrades)).length;
      const shown = modelsFor(svc, state.category).length;
      cc.textContent = `${verified} verified · ${shown} shown`;
    } else cc.textContent = "";
  }
  syncSafetyControls();
  nsfwNote();
}
function renderNsfw(model) { renderContentMode(); }    // back-compat: render() still calls renderNsfw(cur)
$("cmodeseg").addEventListener("click", e => {
  const btn = e.target.closest("button[data-mode]");
  if (!btn || !CONTENT_MODES[btn.dataset.mode]) return;
  state.contentMode = btn.dataset.mode;
  api().set_config({ ui_content_mode: state.contentMode });
  render();   // re-filter the model list + re-render params + mode note
});
$("verifiedonly").addEventListener("change", () => {
  state.verifiedOnly = $("verifiedonly").checked;
  api().set_config({ ui_verified_only: state.verifiedOnly });
  render();
});
$("nsfwinfo").addEventListener("click", () => {
  const modeRows = Object.keys(CONTENT_MODES).map(k =>
    `<div class="nsfw-row allow-${k === "safe" ? "no" : "yes"}">
       <div class="nsfw-head"><b>${CONTENT_MODES[k].label}</b></div>
       <div class="nsfw-pol">${escapeHtml(CONTENT_MODE_HELP[k])}</div>
     </div>`).join("");
  const svcRows = NSFW_POLICY.map(r => `
    <div class="nsfw-row allow-${r.allow}">
      <div class="nsfw-head"><b>${SVC_LABELS[r.p] || r.p}</b><span class="nsfw-badge">${r.allow === "yes" ? "permitted" : r.allow === "partial" ? "model-dependent" : "hard filter"}</span></div>
      <div class="nsfw-pol">${r.policy}</div>
      <div class="nsfw-cfg"><span>config</span> ${escapeHtml(r.config)}</div>
    </div>`).join("");
  $("nsfwrows").innerHTML = `<div class="nsfw-sub">Content modes — how each relaxes safety</div>${modeRows}<div class="nsfw-sub">Per-provider policy</div>${svcRows}`;
  $("nsfwpanel").hidden = false;
});
$("nsfwpanelclose").addEventListener("click", () => { $("nsfwpanel").hidden = true; });
$("nsfwpanel").addEventListener("click", e => { if (e.target.id === "nsfwpanel") $("nsfwpanel").hidden = true; });

const LORA_SERVICES = ["huggingface", "replicate", "fal", "together", "runware", "novita"];
function falModelSupportsLora(id) {
  const m = (id || "").toLowerCase();
  return ["flux-lora", "flux-general", "lora-gallery", "/lora"].some(p => m.includes(p));
}
function renderLoras() {
  let svc = LORA_SERVICES.includes(state.service) ? state.service : null;
  // fal accepts LoRAs only on its LoRA endpoints — hide the panel for base fal models
  if (svc === "fal" && !falModelSupportsLora(state.model)) svc = null;
  $("lorawrap").style.display = svc ? "" : "none";
  if (!svc) return;
  const loras = state.loras[svc] || [];
  $("loracount").textContent = `${loras.filter(l => l.enabled).length}/${loras.length} on`;
  $("loras").innerHTML = loras.map((l, i) => `
    <div class="lora-row">
      <input type="checkbox" data-li="${i}" ${l.enabled ? "checked" : ""}>
      <span class="name" title="${l.url}">${l.url.split("/").pop()}</span>
      <input type="range" data-ls="${i}" min="0" max="1.5" step="0.05" value="${l.scale}">
      <button class="x" data-lx="${i}">✕</button>
    </div>`).join("") + `
    <div class="lora-add">
      <input id="loraurl" placeholder="LoRA URL / HF repo / civitai:id@ver" spellcheck="false">
      <button id="loraaddbtn" title="Add this LoRA">add</button>
      <button id="loracivbtn" title="Search CivitAI LoRAs">🔍 Civitai</button>
    </div>
    <div class="civ-search" id="civsearch" hidden></div>
    <div class="lora-import">
      <input id="loraimportref" placeholder="import to ALL providers — HF repo (user/repo) or .safetensors URL" spellcheck="false">
      <input id="loraimportscale" type="number" step="0.05" min="0" max="1.5" value="0.8" title="scale">
      <button id="loraimportbtn" title="Resolve this HF repo once and add it to every URL-capable provider (fal/together/replicate/HF) in one shot">⇉ import to all</button>
    </div>`;
  $("loras").querySelectorAll("[data-li]").forEach(el => el.addEventListener("change", async () => {
    state.loras[svc] = await api().lora_set(svc, +el.dataset.li, { enabled: el.checked }); renderLoras();
  }));
  $("loras").querySelectorAll("[data-ls]").forEach(el => el.addEventListener("change", async () => {
    state.loras[svc] = await api().lora_set(svc, +el.dataset.ls, { scale: +el.value });
  }));
  $("loras").querySelectorAll("[data-lx]").forEach(el => el.addEventListener("click", async () => {
    state.loras[svc] = await api().lora_remove(svc, +el.dataset.lx); renderLoras();
  }));
  $("loraaddbtn").addEventListener("click", async () => {
    const u = $("loraurl").value.trim(); if (!u) return;
    state.loras[svc] = await api().lora_add(svc, u); renderLoras();
  });
  $("loracivbtn").addEventListener("click", () => {
    const box = $("civsearch"); box.hidden = !box.hidden;
    if (!box.hidden) renderCivitai(svc);
  });
  // E3 — one paste fans out to every URL-capable provider (bridge.import_lora), not just `svc`.
  $("loraimportbtn").addEventListener("click", async () => {
    const ref = $("loraimportref").value.trim();
    const scale = parseFloat($("loraimportscale").value) || 0.8;
    if (!ref) { $("statusmsg").textContent = "paste a HF repo (user/repo) or .safetensors URL first"; return; }
    const btn = $("loraimportbtn"), orig = btn.textContent;
    btn.disabled = true; btn.textContent = "resolving…";
    try {
      const r = await api().import_lora(ref, scale);
      if (r && r.ok) {
        $("statusmsg").textContent = `LoRA added to: ${r.added_to.join(", ") || "none"} — ${r.note}`;
        for (const s of r.added_to) state.loras[s] = await api().lora_list(s);
        renderLoras();
      } else {
        $("statusmsg").textContent = `LoRA import failed: ${(r && r.error) || "unknown error"}`;
      }
    } catch (e) {
      $("statusmsg").textContent = `LoRA import failed: ${e}`;
    } finally {
      btn.disabled = false; btn.textContent = orig;
    }
  });
}

/* ---------- CivitAI LoRA browse-and-add (Phase 4) ---------- */
async function renderCivitai(svc) {
  const box = $("civsearch");
  box.innerHTML = `
    <div class="civ-bar">
      <input id="civq" placeholder="search LoRAs… (e.g. pony, realistic, anime)" spellcheck="false">
      <button id="civgo">search</button>
    </div>
    <div class="civ-results" id="civresults"><div class="civ-hint">Search CivitAI for a LoRA to add to ${SVC_LABELS[svc] || svc}.</div></div>`;
  const run = async () => {
    $("civresults").innerHTML = `<div class="civ-hint">searching…</div>`;
    let res; try { res = await api().civitai_search($("civq").value.trim(), ""); } catch (e) { res = { ok: false, error: String(e) }; }
    if (!res.ok) { $("civresults").innerHTML = `<div class="civ-hint">error: ${escapeHtml(res.error || "search failed")}</div>`; return; }
    if (!res.items.length) { $("civresults").innerHTML = `<div class="civ-hint">no results</div>`; return; }
    $("civresults").innerHTML = res.items.map(it => `
      <div class="civ-card">
        ${it.thumb ? `<img src="${it.thumb}" loading="lazy" alt="">` : `<div class="civ-noimg">no preview</div>`}
        <div class="civ-meta"><b title="${escapeHtml(it.name || "")}">${escapeHtml(it.name || "")}</b>
          <span>${escapeHtml(it.baseModel || "")}${it.nsfw ? " · NSFW" : ""}</span></div>
        <button class="civ-add" data-mid="${it.modelId}" data-vid="${it.versionId}">+ add</button>
      </div>`).join("");
    $("civresults").querySelectorAll(".civ-add").forEach(b => b.addEventListener("click", async () => {
      b.disabled = true; b.textContent = "…";
      const r = await api().civitai_add_lora(svc, +b.dataset.mid, +b.dataset.vid);
      if (r && r.ok && r.loras) { state.loras[svc] = r.loras; renderLoras(); }
      else { b.textContent = "✕"; b.title = (r && r.error) || "add failed"; }
    }));
  };
  $("civgo").addEventListener("click", run);
  $("civq").addEventListener("keydown", e => { if (e.key === "Enter") run(); });
  $("civq").focus();
}

/* ---------- Presets: Style / Recipe (Spec C #4) ---------- */
// render() calls renderPresetSelects() so the dropdowns stay in sync with the composer.
async function loadPresets(applyDefaults) {
  try { state.styles = await api().list_styles(); } catch (e) { state.styles = []; }
  try { state.recipes = await api().list_recipes(); } catch (e) { state.recipes = []; }
  renderPresetSelects();
  if (applyDefaults) {
    const s = state.styles.find(x => x.is_default);
    const r = state.recipes.find(x => x.is_default);
    if (s) applyPresetToComposer("Style", s);
    if (r) applyPresetToComposer("Recipe", r);
  }
}
function renderPresetSelects() {
  const ss = $("styleSel"), rs = $("recipeSel");
  if (ss) ss.innerHTML = `<option value="">— no style —</option>` +
    (state.styles || []).map(s => `<option value="${s.id}">${escapeHtml(s.name)}${s.is_default ? " ★" : ""}</option>`).join("");
  if (rs) rs.innerHTML = `<option value="">— no recipe —</option>` +
    (state.recipes || []).map(r => `<option value="${r.id}">${escapeHtml(r.name)}${r.is_default ? " ★" : ""}</option>`).join("");
}
function currentComposerState() {
  const cur = currentModel();
  const params = collectParams(cur);
  delete params.negative_prompt;   // tracked separately below — collectParams folds it in for generate()
  return {
    prompt: $("prompt").value, negative_prompt: $("negprompt").value,
    model: state.model, provider: state.service, params,
    _appliedStyleId: state._appliedStyleId, _appliedStyleUpdated: state._appliedStyleUpdated,
    _appliedRecipeId: state._appliedRecipeId, _appliedRecipeUpdated: state._appliedRecipeUpdated,
  };
}
function setComposerParam(name, val) {
  const el = $("params").querySelector(`[data-p="${name}"]`);
  if (!el) return;
  if (el.type === "checkbox") el.checked = !!val; else el.value = String(val);
  const vs = $("params").querySelector(`[data-v="${name}"]`); if (vs) vs.textContent = String(val);
}
function applyComposerPatch(next) {
  const modelChanged = next.model && next.model !== state.model;
  if (modelChanged) state.model = next.model;
  if (modelChanged) render();   // repaint category/params for the new model FIRST — then set values
  $("prompt").value = next.prompt || "";
  if ($("negwrap").style.display !== "none") $("negprompt").value = next.negative_prompt || "";
  Object.entries(next.params || {}).forEach(([k, v]) => setComposerParam(k, v));
  state._appliedStyleId = next._appliedStyleId; state._appliedStyleUpdated = next._appliedStyleUpdated;
  state._appliedRecipeId = next._appliedRecipeId; state._appliedRecipeUpdated = next._appliedRecipeUpdated;
}
// AC-4.3 preview/diff + confirm gate. ponytail: native confirm() IS a preview+confirm gate —
// upgrade to a styled modal if PRIME wants richer visuals later.
function applyPresetToComposer(kind, preset) {
  const composer = currentComposerState();
  const opts = { targetProvider: state.service, targetParamNames: currentParamNames() };
  const { diffs, warnings } = previewApply(kind, preset, composer, opts);
  if (!diffs.length) { $("statusmsg").textContent = `${preset.name}: already applied — no changes.`; return; }
  const lines = diffs.map(d => `${d.field}: ${d.before || "(empty)"} → ${d.after}`).join("\n");
  const warn = warnings.length ? `\n\n⚠ ${warnings.join("\n⚠ ")}` : "";
  if (!confirm(`Apply ${kind} "${preset.name}"?\n\n${lines}${warn}`)) return;
  applyComposerPatch(applyPreset(kind, preset, composer, opts));
  $("statusmsg").textContent = `${kind} "${preset.name}" applied.`;
}
function currentParamNames() {
  const cur = currentModel();
  return ((cur && cur.params) || []).map(p => p.name);
}
$("styleApplyBtn") && $("styleApplyBtn").addEventListener("click", () => {
  const s = (state.styles || []).find(x => String(x.id) === $("styleSel").value);
  if (s) applyPresetToComposer("Style", s);
});
$("recipeApplyBtn") && $("recipeApplyBtn").addEventListener("click", () => {
  const r = (state.recipes || []).find(x => String(x.id) === $("recipeSel").value);
  if (r) applyPresetToComposer("Recipe", r);
});
$("saveStyleBtn") && $("saveStyleBtn").addEventListener("click", async () => {
  const name = prompt("Name this Style:"); if (!name) return;
  const c = currentComposerState();
  const r = await api().save_style({ name, negative: c.negative_prompt, prompt_template: "", params: c.params, model: "" });
  if (r && r.ok) { await loadPresets(false); $("statusmsg").textContent = `Style "${name}" saved.`; }
});
$("saveRecipeBtn") && $("saveRecipeBtn").addEventListener("click", async () => {
  const name = prompt("Name this Recipe:"); if (!name) return;
  const c = currentComposerState();
  const r = await api().save_recipe({ name, provider: c.provider, model: c.model, seed: c.params.seed || "",
    prompt: c.prompt, negative: c.negative_prompt, params: c.params });
  if (r && r.ok) { await loadPresets(false); $("statusmsg").textContent = `Recipe "${name}" saved.`; }
});

// ---- Settings > Presets manager (AC-4.5: list, rename, delete, set-default) ----
function renderPresetsManager() {
  const renderTable = (containerId, table, items) => {
    const box = $(containerId); if (!box) return;
    box.innerHTML = items.length ? items.map(p => `
      <div class="presetrow" data-id="${p.id}">
        <span class="preset-name ${p.is_default ? "isdefault" : ""}">${escapeHtml(p.name)}${p.is_default ? " ★ default" : ""}</span>
        <button data-act="default" title="set as default (applied on launch)">${p.is_default ? "default" : "set default"}</button>
        <button data-act="rename">rename</button>
        <button data-act="delete">delete</button>
      </div>`).join("") : `<div class="preset-empty">no ${table} saved yet</div>`;
    box.querySelectorAll(".presetrow").forEach(row => {
      const id = +row.dataset.id;
      const item = items.find(p => p.id === id);
      row.querySelector('[data-act="default"]').addEventListener("click", async () => {
        await (table === "styles" ? api().set_default_style(id) : api().set_default_recipe(id));
        await loadPresets(false); renderPresetsManager();
      });
      row.querySelector('[data-act="rename"]').addEventListener("click", async () => {
        const name = prompt("Rename to:", item.name); if (!name) return;
        await (table === "styles" ? api().rename_style(id, name) : api().rename_recipe(id, name));
        await loadPresets(false); renderPresetsManager();
      });
      row.querySelector('[data-act="delete"]').addEventListener("click", async () => {
        if (!confirm(`Delete "${item.name}"? This can't be undone.`)) return;
        await (table === "styles" ? api().delete_style(id) : api().delete_recipe(id));
        await loadPresets(false); renderPresetsManager();
      });
    });
  };
  renderTable("stylesmanager", "styles", state.styles || []);
  renderTable("recipesmanager", "recipes", state.recipes || []);
}

// ---- Settings > Vision auto-tagging status + manual backfill trigger (AC-8.7) ----
async function renderVisionTagStatus() {
  const el = $("visiontagstatus"), note = $("visiontagnote"), btn = $("visiontagbackfill");
  if (!el) return;
  try {
    const s = await api().vision_tagging_status();
    el.textContent = s.configured ? `configured — ${s.endpoint}` : "not configured (off by default)";
    el.className = "pref-note " + (s.configured ? "vt-on" : "vt-off");
    if (btn) btn.disabled = !s.configured;
  } catch (e) { el.textContent = "unavailable"; }
  if (btn && !btn._wired) {
    btn._wired = true;
    btn.addEventListener("click", async () => {
      btn.disabled = true; btn.textContent = "queuing…";
      try {
        const r = await api().start_vision_tag_backfill(200);
        note.textContent = r.ok ? `queued ${r.queued} image(s) — tagging runs in the background.` : (r.error || "failed to start");
      } catch (e) { note.textContent = "failed to start"; }
      btn.disabled = false; btn.textContent = "Backfill untagged now";
    });
  }
}
$("settingsbtn").addEventListener("click", () => {
  renderPresetsManager();
  renderVisionTagStatus();
});

/* ---------- gallery ---------- */
// WebView2 blocks file:// sub-resources from a file:// page — serve via the
// localhost media server instead (basename resolves against the output dir).
function fileUrl(p) {
  const name = p.split(/[\\/]/).pop();
  return state.mediaBase ? state.mediaBase + encodeURIComponent(name)
                         : "file:///" + p.replace(/\\/g, "/");
}
// Small cached thumbnail (generated once, stored on local disk) for grid tiles — avoids
// re-pulling full-size images from the NAS on every app open. Non-images fall back to full URL.
const THUMB_EXT = ["png", "jpg", "jpeg", "webp", "gif", "bmp"];
function thumbUrl(p, size = 400) {
  const name = p.split(/[\\/]/).pop();
  const ext = name.split(".").pop().toLowerCase();
  if (state.mediaBase && THUMB_EXT.includes(ext))
    return state.mediaBase + "thumb/" + encodeURIComponent(name) + "?s=" + size;
  return fileUrl(p);
}
function mediaTag(f, opts = {}) {
  const name = f.split(/[\\/]/).pop();
  const ext = f.split(".").pop().toLowerCase();
  if (["mp4", "webm", "mov"].includes(ext)) return `<video src="${fileUrl(f)}" controls muted></video>`;
  if (["mp3", "wav", "m4a", "flac"].includes(ext)) return `<audio src="${fileUrl(f)}" controls></audio>`;
  if (["glb", "obj", "stl", "bin"].includes(ext))
    return `<div class="filecard">🧊<br>${name}<br><small>3D model — open in a viewer</small></div>`;
  if (["txt", "json"].includes(ext))
    return `<div class="filecard txt" data-txt="${fileUrl(f)}">📄<br>${name}<br><small>text output — click Save As to keep</small></div>`;
  return `<img src="${opts.thumb ? thumbUrl(f) : fileUrl(f)}" alt="" loading="lazy">`;
}
function renderGallery() {
  // Empty session -> the browse landing (models strip + recent work) instead of a bare message.
  const emptySession = state.view === "session" && !state.gallery.length;
  $("browse").hidden = !emptySession;
  $("gallery").hidden = emptySession;
  $("empty").hidden = true;
  if (emptySession) { renderBrowse(); return; }
  $("gallery").innerHTML = state.gallery.map((g, i) => `
    <div class="tile ${i === state.selected ? "sel" : ""}" data-i="${i}">
      ${mediaTag(g.file, { thumb: true })}
      <div class="acts">
        <button data-save="${i}">Save As</button>
        <button data-open="${i}">Folder</button>
        <button data-reveal="${i}" title="Jump to this image in the Library">📍 Reveal</button>
      </div>
      <div class="meta"><span><b>${g.meta.model.split("/").pop()}</b>${g.meta.seed ? " · " + g.meta.seed : ""}</span><span>${g.time}</span></div>
    </div>`).join("");
  $("outinfo").textContent = `OUTPUT · ${state.outDirName}/ · ${state.gallery.length} this session`;
  $("sessioninfo").textContent = `v2.0 · ${state.genCount} generated`;
  applyGrid();
  $("gallery").querySelectorAll(".tile").forEach(t => t.addEventListener("click", e => {
    if (e.target.closest(".acts")) return;
    openLightbox(state.gallery[+t.dataset.i].file, null, state.gallery);   // #7 click-to-enlarge
  }));
  $("gallery").querySelectorAll("[data-save]").forEach(b => b.addEventListener("click", () =>
    api().save_as(state.gallery[+b.dataset.save].file)));
  $("gallery").querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () =>
    api().open_output_folder()));
  $("gallery").querySelectorAll("[data-reveal]").forEach(b => b.addEventListener("click", () =>
    revealInLibrary(state.gallery[+b.dataset.reveal].file)));
}

/* ---------- #7 lightbox + #9 metadata overlay + Spec C #8 manual tags ---------- */
// `list` (optional) = the array currently on screen (state.gallery / state.libFiltered) that this
// image was opened from — powers R3 #2 (←/→ arrow-key nav) without changing any other call site.
async function openLightbox(file, dir, list) {
  state.lbFile = file;
  state.lbDir = dir || "";
  if (list) { state.lbList = list; state.lbIndex = list.findIndex(r => r.file === file && (r.dir || "") === (dir || "")); }
  else { state.lbList = null; state.lbIndex = -1; }
  $("lbmedia").innerHTML = mediaTag(file);          // reuse the media renderer (img/video/audio)
  $("lbside").innerHTML = `<div class="lbm-title">Metadata <em>loading…</em></div>`;
  $("lightbox").hidden = false;
  try {
    const [m, t] = await Promise.all([api().read_meta(file), api().get_image_tags(file, state.lbDir)]);
    state.lbTags = (t && t.tags) || [];
    $("lbside").innerHTML = renderMeta(m, file);
    wireTagEditor();
  } catch (e) {
    $("lbside").innerHTML = `<div class="lbm-title">Metadata <em>unavailable</em></div>`;
  }
}
function renderMeta(m, file) {
  const name = file.split(/[\\/]/).pop();
  const rows = [];
  const add = (k, v) => { if (v !== undefined && v !== null && v !== "") rows.push(
    `<div class="lbm-row"><span>${k}</span><b>${escapeHtml(String(v))}</b></div>`); };
  add("file", name);
  add("model", m.model);          // full id in the metadata panel (gallery shows the short name)
  add("service", m.service);
  add("seed", m.seed);
  if (m.width && m.height) add("size", `${m.width}×${m.height}`);
  if (m.bytes) add("bytes", (m.bytes / 1024).toFixed(0) + " KB");
  add("time", (m.ts || "").replace("T", " "));
  const params = m.params || {};
  const pstr = Object.entries(params).map(([k, v]) => `${k}=${v}`).join(" · ");
  let html = `<div class="lbm-title">Metadata <em>${m.source || ""}</em></div>${rows.join("")}`;
  if (m.prompt) html += `<div class="lbm-block"><span>prompt</span><div>${escapeHtml(m.prompt)}</div></div>`;
  if (pstr) html += `<div class="lbm-block"><span>params</span><div>${escapeHtml(pstr)}</div></div>`;
  html += renderTagEditor();
  return html;
}
// #8 — manual tags from the lightbox (AC-8.2). Renders as its own block so a tag add/remove can
// re-paint JUST this block instead of reloading the whole metadata panel.
function renderTagEditor() {
  const chips = (state.lbTags || []).map(t =>
    `<span class="tagchip lbtag" data-t="${escapeHtml(t)}">${escapeHtml(t)} <button class="tagchip-x" data-rm="${escapeHtml(t)}" title="remove tag">✕</button></span>`).join("");
  return `<div class="lbm-block lbtags-block" id="lbtagsblock">
    <span>tags</span>
    <div class="tagrow" id="lbtagrow">${chips || '<span class="tagchip-empty">no tags yet</span>'}</div>
    <div class="tagadd"><input id="lbtaginput" type="text" placeholder="add a tag, enter to save" spellcheck="false"><button id="lbtagaddbtn">add</button></div>
  </div>`;
}
function wireTagEditor() {
  const box = $("lbtagsblock"); if (!box) return;
  box.querySelectorAll("[data-rm]").forEach(b => b.addEventListener("click", async e => {
    e.stopPropagation();
    await removeLbTag(b.dataset.rm);
  }));
  const input = $("lbtaginput"), btn = $("lbtagaddbtn");
  const submit = async () => { const v = (input.value || "").trim(); if (!v) return; input.value = ""; await addLbTag(v); };
  if (btn) btn.addEventListener("click", submit);
  if (input) input.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });
}
async function addLbTag(tag) {
  if (!state.lbFile) return;
  try {
    const r = await api().add_tag(state.lbFile, tag, state.lbDir);
    if (r && r.ok) { state.lbTags = r.tags; syncLbTagsToLibRecord(); repaintLbTags(); }
  } catch (e) {}
}
async function removeLbTag(tag) {
  if (!state.lbFile) return;
  try {
    const r = await api().remove_tag(state.lbFile, tag, state.lbDir);
    if (r && r.ok) { state.lbTags = r.tags; syncLbTagsToLibRecord(); repaintLbTags(); }
  } catch (e) {}
}
function repaintLbTags() {
  const box = $("lbtagsblock"); if (!box) return;
  box.outerHTML = renderTagEditor();
  wireTagEditor();
}
// Keep the Library view's in-memory record (and its tag chips) fresh without a full refetch.
function syncLbTagsToLibRecord() {
  const name = (state.lbFile || "").split(/[\\/]/).pop();
  for (const r of state.libRecords) {
    if (r.file === name && (!state.lbDir || r.dir === state.lbDir)) r.tags = state.lbTags.slice();
  }
  if (state.view === "library") applyLibFilter();
}
function closeLightbox() { $("lightbox").hidden = true; state.lbFile = null; state.lbDir = ""; state.lbTags = []; $("lbmedia").innerHTML = ""; }
$("lbclose").addEventListener("click", closeLightbox);
$("lightbox").addEventListener("click", e => { if (e.target.id === "lightbox") closeLightbox(); });
$("lbedit").addEventListener("click", () => { if (state.lbFile) api().open_in_editor(state.lbFile); });
$("lbfolder").addEventListener("click", () => api().open_output_folder());
$("lbsave").addEventListener("click", () => { if (state.lbFile) api().save_as(state.lbFile); });
// #3 — img->prompt: detect the original prompt or analyze the image, then seed the prompt box
$("lbanalyze").addEventListener("click", async () => {
  if (!state.lbFile) return;
  const btn = $("lbanalyze"), orig = btn.textContent;
  btn.textContent = "analyzing…"; btn.disabled = true;
  try {
    const r = await api().analyze_image(state.lbFile);
    if (r.prompt) {
      $("prompt").value = r.prompt;
      closeLightbox();
      setView("session");
      $("prompt").focus();
      $("statusmsg").textContent = r.source === "vision"
        ? "prompt from image analysis — edit & regenerate"
        : "prompt detected from metadata — edit & regenerate";
    } else {
      $("lbside").innerHTML = `<div class="lbm-title">Analyze <em>failed</em></div><div class="lbm-block"><div>${escapeHtml(r.error || "no prompt")}</div></div>`;
    }
  } catch (e) {
    $("statusmsg").textContent = "analyze failed: " + e;
  } finally {
    btn.textContent = orig; btn.disabled = false;
  }
});
// R3 #2 — ←/→ walk the lightbox through whatever list it was opened from (session gallery or the
// current filtered library order); Escape still closes. Ignored while typing (e.g. the tag input).
function navLightbox(dir) {
  if (!state.lbList || !state.lbList.length || state.lbIndex < 0) return;
  const next = state.lbIndex + dir;
  if (next < 0 || next >= state.lbList.length) return;   // clamp at the ends, no wraparound
  const r = state.lbList[next];
  openLightbox(r.file, r.dir, state.lbList);
}
document.addEventListener("keydown", e => {
  if ($("lightbox").hidden) return;
  if (e.key === "Escape") { closeLightbox(); return; }
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  if (/^(INPUT|TEXTAREA)$/.test((e.target && e.target.tagName) || "")) return;
  navLightbox(e.key === "ArrowLeft" ? -1 : 1);
});

/* ---------- browse landing (models strip only — pick a model to start) ---------- */
async function renderBrowse() {
  const wrap = $("browse");
  const models = modelsFor(state.service, state.category);
  const cur = currentModel();
  const cards = models.slice(0, 24).map(m => {
    const on = cur && m.id === cur.id ? " on" : "";
    // onerror → swap to the initials placeholder so an expired CDN thumb never renders broken
    const img = m.thumb
      ? `<img src="${m.thumb}" loading="lazy" onerror="this.outerHTML='<div class=\\'mc-ph\\'>${(m.label || m.id).slice(0, 2)}</div>'">`
      : `<div class="mc-ph">${(m.label || m.id).slice(0, 2)}</div>`;
    const tag = m.sample ? `<span class="mc-sample" title="thumbnail is our own verified render from this model">sample: our render</span>` : "";
    const desc = m.description ? `<div class="mc-p" title="${escapeHtml(m.description)}">${escapeHtml(m.description).slice(0, 90)}</div>` : "";
    return `<div class="mcard${on}" data-mid="${m.id}">${tag}${img}
      <div class="mc-t" title="${m.label || m.id}">${m.label || m.id}</div>
      ${desc || `<div class="mc-p">${m.price || ""}</div>`}</div>`;
  }).join("");

  wrap.innerHTML = `
    <div class="s2lbl">Models <em>${models.length} in ${CAT_LABELS[state.category] || state.category}${state.service === "fal" ? " · fal" : ""}</em></div>
    <div class="mstrip" id="mstrip">${cards || '<div class="emptystate">no models here</div>'}</div>
    <div class="emptystate" style="padding:48px 20px">write a prompt and hit GENERATE — your images live in the <b>LIBRARY</b> tab, past prompts in <b>HISTORY</b></div>`;

  wrap.querySelectorAll(".mcard").forEach(c => c.addEventListener("click", () => {
    const m = models.find(x => x.id === c.dataset.mid);
    if (!m) return;
    state.model = m.id;
    if (state.service === "fal" && m.category) state.category = m.category;
    render();
    $("prompt").focus();
  }));
}

/* ---------- library view (all archive files — filter + folder toggles) ---------- */
async function renderLibrary() {
  const wrap = $("library");
  wrap.innerHTML = `
    <div class="s2lbl">Library <em id="libcount">loading…</em>
      <button id="librefresh" class="lib-refresh" title="Rescan the archive folders for new images">↻ refresh</button></div>
    <div class="libfilters">
      <input id="libq" type="text" placeholder="search prompt / model…" spellcheck="false">
      <select id="libfolder" title="Filter by source folder"><option value="">all folders</option></select>
      <select id="libsvc" title="Filter by where it was generated"><option value="">all sources</option></select>
      <select id="libtype" title="Filter by media type"><option value="">all types</option><option value="image">images</option><option value="video">video</option></select>
    </div>
    <div class="libtags" id="libtags"></div>
    <div class="libfolders" id="libfolders"></div>
    <div class="wmason" id="libmason"><div class="emptystate">loading…</div></div>`;
  $("librefresh").addEventListener("click", async () => {
    const rb = $("librefresh"); rb.disabled = true; rb.textContent = "↻ rescanning…";
    try { await api().refresh_library(8000); } catch (e) {}
    await loadLibrary();
  });
  renderLibFolders();
  await loadLibrary();
}

function renderLibFolders() {
  const box = $("libfolders"); if (!box) return;
  box.innerHTML = state.libraryDirs.map(d =>
    `<label class="libfolder ${d.enabled ? "on" : ""} ${d.exists ? "" : "missing"}" title="${escapeHtml(d.path)}${d.exists ? "" : " — folder not found"}">
       <input type="checkbox" data-fp="${escapeHtml(d.path)}" ${d.enabled ? "checked" : ""}> ${escapeHtml(d.name)}</label>`
  ).join("") + `<button id="libadd" class="libaddbtn" title="Add another folder to the library">＋ add folder</button>`;
  box.querySelectorAll("input[data-fp]").forEach(cb => cb.addEventListener("change", async () => {
    cb.disabled = true;
    try { const res = await api().set_library_dir_enabled(cb.dataset.fp, cb.checked); if (res && res.dirs) state.libraryDirs = res.dirs; } catch (e) {}
    renderLibFolders();
    await loadLibrary();
  }));
  $("libadd").addEventListener("click", async () => {
    try { const res = await api().add_library_dir(""); if (res && res.dirs) state.libraryDirs = res.dirs; } catch (e) {}
    renderLibFolders();
    await loadLibrary();
  });
}

async function loadLibrary() {
  try { state.libRecords = await api().list_library(8000); } catch (e) { state.libRecords = []; }
  const dirs = [...new Set(state.libRecords.map(r => r.dir).filter(Boolean))];
  const svcs = [...new Set(state.libRecords.map(r => r.service).filter(Boolean))].sort();
  const folderSel = $("libfolder"), svcSel = $("libsvc");
  if (folderSel) folderSel.innerHTML = `<option value="">all folders</option>` +
    dirs.map(d => `<option value="${escapeHtml(d)}">${escapeHtml(d.split(/[\\/]/).filter(Boolean).pop() || d)}</option>`).join("");
  if (svcSel) svcSel.innerHTML = `<option value="">all sources</option>` +
    svcs.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
  ["libq", "libfolder", "libsvc", "libtype"].forEach(id => {
    const el = $(id); if (el && !el._libwired) { el._libwired = true; el.addEventListener("input", applyLibFilter); }
  });
  applyLibFilter();
}

function applyLibFilter() {
  const q = ($("libq") ? $("libq").value : "").toLowerCase().trim();
  const folder = $("libfolder") ? $("libfolder").value : "";
  const svc = $("libsvc") ? $("libsvc").value : "";
  const type = $("libtype") ? $("libtype").value : "";
  const activeTags = state.libFilter.tags || [];
  state.libFiltered = state.libRecords.filter(r =>
    (!folder || r.dir === folder) &&
    (!svc || (r.service || "") === svc) &&
    (!type || (r.type || "image") === type) &&
    (!q || `${r.prompt || ""} ${r.model || ""} ${r.file}`.toLowerCase().includes(q)) &&
    activeTags.every(t => (r.tags || []).includes(t)));           // AC-8.3 — multi-tag = AND
  const cnt = $("libcount");
  if (cnt) cnt.textContent = `${state.libFiltered.length} of ${state.libRecords.length} files`;
  renderLibTagChips();
  renderLibTiles();
}

// AC-8.3 — chips derived from the distinct tags in the CURRENT filtered result set ("in view" =
// current query results, not the whole DB), capped at 40, sorted by frequency.
function renderLibTagChips() {
  const box = $("libtags"); if (!box) return;
  const freq = new Map();
  for (const r of state.libFiltered) for (const t of (r.tags || [])) freq.set(t, (freq.get(t) || 0) + 1);
  const chips = [...freq.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 40);
  const active = state.libFilter.tags || [];
  box.innerHTML = chips.length
    ? chips.map(([t, n]) => `<button class="tagchip filterchip ${active.includes(t) ? "on" : ""}" data-tag="${escapeHtml(t)}">${escapeHtml(t)} <em>${n}</em></button>`).join("")
      + (active.length ? `<button class="tagchip clearchip" id="libtagsclear">clear tags ✕</button>` : "")
    : `<span class="tagchip-empty">no tags in view</span>`;
  box.querySelectorAll("[data-tag]").forEach(b => b.addEventListener("click", () => {
    const t = b.dataset.tag;
    const i = state.libFilter.tags.indexOf(t);
    if (i === -1) state.libFilter.tags.push(t); else state.libFilter.tags.splice(i, 1);
    applyLibFilter();
  }));
  const clr = $("libtagsclear"); if (clr) clr.addEventListener("click", () => { state.libFilter.tags = []; applyLibFilter(); });
}

// PERF (R3 #1): the library grid used to fully rebuild `mason.innerHTML` (recreating every <img>)
// on EVERY filter/tag-chip click, which re-triggered/re-decoded thousands of thumbnails and made
// the tag filter feel like it was "regenerating" the whole library. Fix: tiles are built ONCE per
// underlying record set (`state.libRecords`, identity-checked) and kept in a Map; filtering never
// touches the DOM nodes or their <img src> — it only toggles `.hidden` on the ones already built.
// Zero new network requests on a filter click, by construction (no src is ever re-assigned).
const LIB_BUILD_CHUNK = 200;   // records per animation-frame tick — first screen paints immediately,
                                // the rest streams in without blocking (windowed initial render)

function libKey(r) { return `${r.dir || ""}␟${r.file}`; }

function renderLibTiles() {
  const mason = $("libmason"); if (!mason) return;
  if (!state.libRecords.length) {
    mason.innerHTML = `<div class="emptystate">no images yet — ↻ refresh to scan the archive folders</div>`;
    state.libTileEls = null;
    return;
  }
  if (!state.libTileEls || state.libTileEls.forArray !== state.libRecords) buildLibTiles(mason);
  else syncLibTileVisibility();
}

function buildLibTile(r) {
  const el = document.createElement("div");
  el.className = "wtile";
  el.dataset.rk = libKey(r);
  el.innerHTML = `
    ${mediaTag(r.file, { thumb: true })}
    <div class="wmeta"><b>${escapeHtml(r.service || r.file.split(".").pop())}</b><span data-open="1">open folder</span></div>
    ${r.prompt ? `<div class="wprompt" title="${escapeHtml(r.prompt)}">${escapeHtml(r.prompt.slice(0, 140))}</div>` : ""}`;
  el.querySelector("[data-open]").addEventListener("click", (e) => { e.stopPropagation(); api().open_output_folder(); });
  el.addEventListener("click", e => {
    if (e.target.closest("[data-open]")) return;
    openLightbox(r.file, r.dir, state.libFiltered);   // #7 lightbox — nav list = current filtered/displayed order
  });
  return el;
}

function buildLibTiles(mason) {
  const recs = state.libRecords;
  const map = new Map();
  map.forArray = recs;                       // identity tag: which array this build belongs to
  state.libTileEls = map;
  mason.innerHTML = `<div class="emptystate" id="libnomatch" hidden>no images match — adjust the filters or ↻ refresh</div>`;
  applyGrid();
  let i = 0;
  (function step() {
    if (state.libTileEls !== map) return;    // a newer build superseded this one mid-flight — bail
    const frag = document.createDocumentFragment();
    const end = Math.min(i + LIB_BUILD_CHUNK, recs.length);
    for (; i < end; i++) { const el = buildLibTile(recs[i]); map.set(libKey(recs[i]), el); frag.appendChild(el); }
    mason.appendChild(frag);
    syncLibTileVisibility();                 // apply the current filter to the just-added chunk
    if (i < recs.length) requestAnimationFrame(step);
  })();
}

function syncLibTileVisibility() {
  if (!state.libTileEls) return;
  const visible = new Set(state.libFiltered.map(libKey));
  let shown = 0;
  for (const [key, el] of state.libTileEls) {
    const on = visible.has(key);
    el.hidden = !on;
    if (on) shown++;
  }
  const nomatch = $("libnomatch");
  if (nomatch) nomatch.hidden = shown > 0;
}

/* ---------- E4 — Reveal in Library (Spec C AC-6.4) ---------- */
// Jumps from a Session tile / History row to its entry in the Library: switches view, waits for
// the index to load, sets the search box to the exact filename, filters, scrolls it into view.
async function revealInLibrary(file) {
  if (!file) return;
  const name = file.split(/[\\/]/).pop();
  setView("library");           // renders the Library shell + kicks off its own loadLibrary()
  await loadLibrary();          // ensure records are current (warm DB read — cheap even if doubled)
  const q = $("libq");
  if (q) q.value = name;
  state.libFilter.tags = [];    // a stale tag filter could hide the very tile we're revealing
  applyLibFilter();
  const rec = state.libFiltered.find(r => r.file === name);
  const tile = rec && state.libTileEls ? state.libTileEls.get(libKey(rec)) : null;
  if (tile) {
    tile.scrollIntoView({ block: "center", behavior: "smooth" });
    const prev = tile.style.outline;
    tile.style.outline = "2px solid var(--accent, #8B5CF6)";
    setTimeout(() => { tile.style.outline = prev; }, 1600);
  } else {
    $("statusmsg").textContent = `"${name}" not found in the library index — try ↻ refresh`;
  }
}

/* ---------- history view ---------- */
async function renderHistory() {
  const wrap = $("history");
  wrap.innerHTML = `<div class="emptystate">loading history…</div>`;
  let rows = [];
  try { rows = await api().get_history(300); } catch (e) { rows = []; }
  if (!rows.length) {
    wrap.innerHTML = `<div class="emptystate">no history yet — every generation is logged here across sessions</div>`;
    return;
  }
  wrap.innerHTML = rows.map((r, i) => {
    const files = (r.files || []);
    const thumbs = files.map(f => `<div class="h-thumb">${mediaTag(f, { thumb: true })}</div>`).join("");
    const when = (r.ts || "").replace("T", " ").slice(0, 16);
    return `<div class="h-row" data-i="${i}">
      <div class="h-thumbs">${thumbs || '<div class="h-thumb none">—</div>'}</div>
      <div class="h-meta">
        <div class="h-prompt">${escapeHtml(r.prompt || "(no prompt)")}</div>
        <div class="h-sub"><b>${(r.model || "").split("/").pop()}</b> · ${r.service || ""} · ${when}${r.seed ? " · seed " + r.seed : ""}</div>
        <div class="h-acts">
          <button data-reuse="${i}">↻ reuse prompt</button>
          <button data-copy="${i}">copy prompt</button>
          <button data-reveal="${i}" ${files.length ? "" : "disabled"} title="Jump to this image in the Library">📍 reveal</button>
        </div>
      </div>
    </div>`;
  }).join("");

  wrap.querySelectorAll("[data-reveal]").forEach(b => b.addEventListener("click", () => {
    const r = rows[+b.dataset.reveal];
    revealInLibrary((r.files || [])[0]);
  }));
  wrap.querySelectorAll("[data-reuse]").forEach(b => b.addEventListener("click", () => {
    const r = rows[+b.dataset.reuse];
    $("prompt").value = r.prompt || "";
    if (state.services.includes(r.service)) {
      state.service = r.service; state.model = r.model;
      renderService();
      const m = state.falModels.find(x => x.id === r.model);
      if (m) state.category = m.category;
      render();
    }
    setView("session");
  }));
  wrap.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", () => {
    navigator.clipboard.writeText(rows[+b.dataset.copy].prompt || "");
    b.textContent = "copied";
    setTimeout(() => { b.textContent = "copy prompt"; }, 1200);
  }));
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* ---------- #14 Logs panel (Portainer-style, searchable, copyable) ---------- */
async function renderLogs() {
  const wrap = $("logs");
  if (!wrap.dataset.init) {
    wrap.innerHTML = `
      <div class="logs-bar">
        <input id="logsearch" placeholder="search logs…">
        <select id="loglevel"><option value="">all levels</option><option value="info">info</option><option value="error">error</option></select>
        <button id="logrefresh" title="refresh">↻</button>
        <button id="logcopy">Copy all</button>
        <button id="logclear">Clear</button>
      </div>
      <div class="logrows" id="logrows"></div>`;
    wrap.dataset.init = "1";
    $("logsearch").addEventListener("input", loadLogs);
    $("loglevel").addEventListener("change", loadLogs);
    $("logrefresh").addEventListener("click", loadLogs);
    $("logcopy").addEventListener("click", async () => {
      const rows = await api().get_logs($("logsearch").value, $("loglevel").value);
      const text = rows.map(r => `[${r.ts}] ${r.level.toUpperCase()} ${r.type} — ${r.message}${r.detail ? "\n" + r.detail : ""}`).join("\n");
      navigator.clipboard.writeText(text);
      $("logcopy").textContent = "copied"; setTimeout(() => { $("logcopy").textContent = "Copy all"; }, 1200);
    });
    $("logclear").addEventListener("click", async () => { await api().clear_logs(); loadLogs(); });
  }
  loadLogs();
}
async function loadLogs() {
  let rows = [];
  const q = $("logsearch") ? $("logsearch").value : "", lv = $("loglevel") ? $("loglevel").value : "";
  try { rows = await api().get_logs(q, lv); } catch (e) { rows = []; }
  const el = $("logrows");
  if (!rows.length) { el.innerHTML = `<div class="emptystate">no log entries${q || lv ? " match" : " yet"}</div>`; return; }
  el.innerHTML = rows.map(r => `
    <div class="logrow lv-${r.level}">
      <span class="lt">${(r.ts || "").replace("T", " ").slice(11)}</span>
      <span class="lv">${r.level}</span>
      <span class="lty">${escapeHtml(r.type)}</span>
      <span class="lm">${escapeHtml(r.message)}</span>
      ${r.detail ? `<pre class="ld">${escapeHtml(r.detail)}</pre>` : ""}
    </div>`).join("");
}
function setView(v) {
  state.view = v;
  document.querySelectorAll("#viewtoggle button").forEach(b => b.classList.toggle("on", b.dataset.view === v));
  $("library").hidden = v !== "library";
  $("history").hidden = v !== "history";
  $("logs").hidden = v !== "logs";
  $("empty").hidden = true;
  if (v === "session") { renderGallery(); }        // session = models landing or this-session gallery
  else { $("browse").hidden = true; $("gallery").hidden = true; }
  if (v === "library") renderLibrary();
  else if (v === "history") renderHistory();
  else if (v === "logs") renderLogs();
}
$("viewtoggle").addEventListener("click", e => { const b = e.target.closest("button"); if (b) setView(b.dataset.view); });

/* ---------- generation ---------- */
function setBusy(busy) {
  const gen = $("gen");
  if (busy) {
    gen.textContent = "CANCEL";
    gen.classList.add("cancel");
    $("qstate").textContent = "running";
    $("pbar").classList.add("run");
    $("canhint").textContent = "click to cancel";
  } else {
    gen.textContent = "GENERATE";
    gen.classList.remove("cancel");
    gen.disabled = false;
    $("qstate").textContent = "idle";
    $("pbar").classList.remove("run");
    $("canhint").textContent = "";
    state.job = null;
  }
}

$("gen").addEventListener("click", async () => {
  if (state.job) { await api().cancel(state.job); return; }
  const cur = currentModel();
  if (!cur) { $("statusmsg").textContent = "no model selected"; return; }
  const prompt = $("prompt").value.trim();
  const kinds = neededKinds(cur);
  if (!prompt && !kinds.length) { $("statusmsg").textContent = "prompt required"; return; }
  const missing = kinds.filter(k => !state.inputFiles[k]);
  if (missing.length) { $("statusmsg").textContent = "input required: " + missing.join(", "); return; }
  const inputFiles = {};
  kinds.forEach(k => { inputFiles[k] = state.inputFiles[k]; });
  const req = {
    service: state.service, model: cur.id, category: state.category,
    prompt, params: applyContentMode(collectParams(cur), cur, state.contentMode, state.service), input_files: inputFiles,
  };
  const r = await api().generate(req);
  if (r.error) { $("statusmsg").textContent = r.error; return; }
  state.job = r.job_id;
  setBusy(true);
});

// Derive the required input from the CATEGORY, not the per-model needs_input_* flags
// (those flags in fal_models.json are unreliable — e.g. an image-to-image model tagged
// needs_input_audio). The category "<src>-to-<dst>" names the input the model consumes.
const SRC_KIND = { image: "image", video: "video", audio: "audio", speech: "audio", "3d": "mesh" };
function neededKinds(model) {
  const cat = (model && model.category) || state.category || "";
  const src = cat.split("-to-")[0];
  const kind = SRC_KIND[src];
  if (kind) return [kind];
  // fall back to any explicit flags for edge models that declare them
  return model ? Object.entries(INPUT_KINDS).filter(([f]) => model[f]).map(([, k]) => k) : [];
}
function renderInputPickers(model) {
  const kinds = neededKinds(model);
  $("inputimgwrap").style.display = kinds.length ? "" : "none";
  if (!kinds.length) { state.inputFiles = {}; return; }
  $("inputimgwrap").querySelector(".lbl").textContent = "Input " + kinds.join(" + ");
  $("inputimgwrap").querySelector(".imgpick").innerHTML = kinds.map(k => `
    <button data-pick="${k}">${k}…</button>
    <span class="path" data-path="${k}">${state.inputFiles[k] ? state.inputFiles[k].split(/[\\/]/).pop() : "none"}</span>`).join("");
  $("inputimgwrap").querySelectorAll("[data-pick]").forEach(b => b.addEventListener("click", async () => {
    const r = await api().pick_input_file(b.dataset.pick);
    if (r.path) {
      state.inputFiles[b.dataset.pick] = r.path;
      $("inputimgwrap").querySelector(`[data-path="${b.dataset.pick}"]`).textContent = r.path.split(/[\\/]/).pop();
    }
  }));
}

/* ---------- engine events ---------- */
window.onEngineEvent = (evt) => {
  if (evt.type === "job_queued") { $("statusmsg").textContent = "queued…"; }
  else if (evt.type === "job_progress") { $("statusmsg").textContent = evt.message || "…"; }
  else if (evt.type === "job_done") {
    const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    evt.files.forEach(f => state.gallery.unshift({ file: f, meta: evt.meta, time: t }));
    state.genCount += evt.files.length;
    state.selected = 0;
    $("statusmsg").textContent = `done — ${evt.files.length} file(s)`;
    setBusy(false); renderGallery(); refreshBalance();  // fal balance drops after a gen
  } else if (evt.type === "job_error") {
    $("statusmsg").textContent = evt.error;
    if (evt.error !== "Cancelled.") showError(evt.error, evt.detail || "");  // #15 copyable popup
    setBusy(false);
  }
  if (state.view === "logs") loadLogs();  // live-refresh the Logs panel on any event
};

/* ---------- #15 copyable error popup ---------- */
function showError(msg, detail) {
  $("errbody").textContent = detail ? (msg + "\n\n" + detail) : msg;
  $("errpop").hidden = false;
}
$("errclose").addEventListener("click", () => { $("errpop").hidden = true; });
$("errpop").addEventListener("click", e => { if (e.target.id === "errpop") $("errpop").hidden = true; });
$("errcopy").addEventListener("click", () => {
  navigator.clipboard.writeText($("errbody").textContent);
  $("errcopy").textContent = "copied"; setTimeout(() => { $("errcopy").textContent = "Copy full error"; }, 1200);
});

/* ---------- service/category/model switching ---------- */
$("svc").addEventListener("change", () => {
  state.service = $("svc").value; state.model = null; state.inputFiles = {};
  renderService(); render(); refreshBalance();
});
$("cats").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  state.category = b.dataset.c; state.model = null; render();
});
$("model").addEventListener("change", () => { state.model = $("model").value; render(); });
// §4 suggestion box: instant filter as you type + click-to-apply (sets provider + model)
$("modelquery") && $("modelquery").addEventListener("input", renderModelSuggest);
$("modelsuggest") && $("modelsuggest").addEventListener("click", e => {
  const btn = e.target.closest(".msuggest-chip"); if (!btn) return;
  const svc = btn.dataset.svc, id = decodeURIComponent(btn.dataset.id);
  if (svc !== state.service) { state.service = svc; state.inputFiles = {}; renderService(); refreshBalance(); }
  state.model = id;
  $("modelquery").value = "";
  render();
});

// §4 AC-4.3/4.4 — Ask-AI model-answered reply (grounded in accessible models, via bridge.suggest_model).
// Picks render as the SAME .msuggest-chip markup as the instant-filter results, so the click-apply
// listener above handles both paths for free — no separate wiring needed.
async function askAI() {
  const box = $("modelsuggest");
  const q = ($("modelquery") && $("modelquery").value.trim()) || "";
  if (!box) return;
  if (!q) { box.innerHTML = `<div class="msuggest-empty">type what you're looking for first</div>`; return; }
  const btn = $("askaibtn"), orig = btn && btn.textContent;
  if (btn) { btn.disabled = true; btn.textContent = "asking…"; }
  box.innerHTML = `<div class="msuggest-empty">asking AI…</div>`;
  try {
    const r = await api().suggest_model(q);
    if (!r || !r.ok) {
      box.innerHTML = `<div class="msuggest-empty">${escapeHtml((r && r.error) || "cliproxy unreachable")}</div>`;
    } else {
      const chips = (r.picks || []).map(m =>
        `<button class="msuggest-chip" data-svc="${m.service}" data-id="${encodeURIComponent(m.id)}"><b>${escapeHtml(m.label)}</b><span>${m.service}</span></button>`).join("");
      box.innerHTML = `<div class="askai-answer" style="white-space:pre-wrap">${escapeHtml((r.text || "").trim())}</div>` +
        (chips || `<div class="msuggest-empty">no accessible model named in the reply — try rephrasing</div>`);
    }
  } catch (e) {
    box.innerHTML = `<div class="msuggest-empty">cliproxy unreachable — ${escapeHtml(String(e))}</div>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}
$("askaibtn") && $("askaibtn").addEventListener("click", askAI);
$("modelquery") && $("modelquery").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); askAI(); } });

/* ---------- boot ---------- */
function tryBoot() {
  boot().catch(err => {
    $("connlabel").textContent = "bridge error: " + err;
    $("conn").classList.add("off");
  });
}
// pywebviewready can fire before this script registers its listener — guard both paths,
// plus a short poll as a belt-and-braces for WebView2 injection timing.
if (window.pywebview && window.pywebview.api) {
  tryBoot();
} else {
  window.addEventListener("pywebviewready", tryBoot, { once: true });
  let tries = 0;
  const poll = setInterval(() => {
    if (window.pywebview && window.pywebview.api) {
      clearInterval(poll);
      if ($("connlabel").textContent === "connecting…") tryBoot();
    } else if (++tries > 50) {
      clearInterval(poll);
    }
  }, 200);
}
