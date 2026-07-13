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
const SVC_LABELS = { fal: "Fal", openai: "OpenAI", nvidia: "NVIDIA", replicate: "Replicate", huggingface: "HF", gemini: "Gemini", openrouter: "OpenRouter" };

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
  services: [], keys: {}, falModels: [], recentModels: {}, lastUsed: {},
  service: "fal", category: "text-to-image", model: null,
  inputFiles: {}, job: null, gallery: [], selected: null,
  genCount: 0, loras: {}, mediaBase: "", outDirName: "generated_images",
  view: "session", grid: "m", lbFile: null, nsfw: true,
};

/* ---------- bridge helpers ---------- */
const api = () => window.pywebview.api;

async function boot() {
  const s = await api().get_state();
  state.services = s.services;
  state.keys = s.keys_status;
  state.keyPools = s.key_pools || {};
  state.falModels = s.fal_models;
  state.recentModels = s.recent_models;
  state.loras = s.loras || {};
  state.mediaBase = s.media_base || "";
  state.outDirName = s.output_dir_name || "generated_images";
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
  state.nsfw = cfg.ui_nsfw !== false;   // #1 permissive-by-default (max coverage); persisted
  if (cfg.parameters && cfg.parameters.negative_prompt) $("negprompt").value = cfg.parameters.negative_prompt;
  $("conn").classList.remove("off");
  $("connlabel").textContent = Object.entries(state.keys)
    .map(([k, ok]) => `${k}:${ok ? "✓" : "✗"}`).join(" ");
  renderService();
  render();
  refreshBalance();
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

/* ---------- settings modal (API keys) ---------- */
const KEY_HINTS = {
  fal: "FAL_KEY · fal.ai/dashboard/keys",
  openai: "OPENAI_API_KEY · platform.openai.com/api-keys",
  nvidia: "NVIDIA_API_KEY · build.nvidia.com (nvapi-…)",
  replicate: "REPLICATE_API_TOKEN · replicate.com/account/api-tokens",
  gemini: "GEMINI_API_KEY · aistudio.google.com/apikey (free)",
  huggingface: "HUGGINGFACE_TOKEN · huggingface.co/settings/tokens",
  openrouter: "OPENROUTER_API_KEY · openrouter.ai/keys (sk-or-v1-…)",
};
function renderKeyRows() {
  $("keyrows").innerHTML = ["fal", "openai", "nvidia", "replicate", "huggingface", "gemini", "openrouter"].map(s => `
    <div class="keyrow" data-svc="${s}">
      <div class="keyrow-head">
        <span class="svc-name">${SVC_LABELS[s]}</span>
        <span class="status ${state.keys[s] ? "set" : "unset"}" data-status>${state.keys[s] ? "key set" : "not set"}${(state.keyPools && state.keyPools[s] > 1) ? ` · ${state.keyPools[s]} keys (auto-swap)` : ""}</span>
      </div>
      <div class="keyrow-in">
        <input type="password" placeholder="paste new ${SVC_LABELS[s]} key to override…" data-keyin>
        <button data-save>Save &amp; Validate</button>
        <button data-check title="check the key already in use, without changing it">Check current</button>
      </div>
      <div class="hint">${KEY_HINTS[s]}</div>
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
      setStatus(v.valid ? "valid" : "invalid",
                v.valid ? `saved · valid (${v.http})` : `saved · ${v.detail} (${v.http})`);
      input.value = "";
      renderService();            // reflect new key state in the dropdown immediately
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
$("settingsbtn").addEventListener("click", () => { renderKeyRows(); $("settings").hidden = false; });
$("settingsclose").addEventListener("click", () => { $("settings").hidden = true; });
$("settings").addEventListener("click", e => { if (e.target.id === "settings") $("settings").hidden = true; });

/* ---------- model catalog ---------- */
function modelsFor(service, category) {
  if (service === "fal") return state.falModels.filter(m => m.category === category);
  return (state.recentModels[service] || []).map(id => ({ id, label: id, category: "text-to-image", params: LEGACY_PARAMS }));
}
function currentModel() {
  const models = modelsFor(state.service, state.category);
  return models.find(m => m.id === state.model)
      || models.find(m => m.id === state.lastUsed[state.service])
      || models[0] || null;
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
  $("model").innerHTML = models.map(m =>
    `<option value="${m.id}" ${cur && m.id === cur.id ? "selected" : ""}>${m.label}${m.price ? " — " + m.price : ""}</option>`).join("");
  $("pricenote").textContent = cur && cur.price ? cur.price : "";
  $("estcost").textContent = cur && cur.price ? "est " + cur.price : "";
  $("modellabel").textContent = cur ? cur.label || cur.id : "";
  $("hdrinfo").textContent = `${state.service} · ${cur ? (cur.label || cur.id) : "—"}`;

  renderInputPickers(cur);
  renderPromptGuide(cur);
  // #12 — negative prompt only where the family actually uses it (FLUX/gpt-image/nano-banana hide it)
  const fam = PROMPT_GUIDE[modelFamily(cur && cur.id)] || PROMPT_GUIDE.generic;
  $("negwrap").style.display = fam.neg ? "" : "none";
  renderParams(cur);
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
  { p: "fal", allow: "yes", policy: "Permissive — artistic/implied nudity on many models via safety params.",
    config: "enable_safety_checker=false (28 models) + safety_tolerance up to 6 (15 models). The toggle sets these on models that declare them." },
  { p: "huggingface", allow: "partial", policy: "Model-dependent; many SDXL/community checkpoints are uncensored.",
    config: "Steer with negative_prompt; no global flag. FLUX_DISABLE_SAFETY honored where the model reads it." },
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
    const help = PARAM_HELP[p.name] || "";
    const info = help ? ` <span class="phelp" title="${help.replace(/"/g, "&quot;")}">&#9432;</span>` : "";
    return `<div class="prow"><span title="${help.replace(/"/g, "&quot;")}">${p.name.replace(/_/g, " ")}${info}</span>${paramControl(p)}</div>`;
  }).join("");
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
  // The Content toggle governs the safety params; mirror it into the param controls
  // (which #5 still renders as labeled) so collectParams reads the right values.
  const chk = $("params").querySelector('[data-p="enable_safety_checker"]');
  if (chk) chk.checked = !state.nsfw;                 // permissive -> checker OFF
  const tol = $("params").querySelector('[data-p="safety_tolerance"]');
  if (tol && state.nsfw) tol.value = "6";             // permissive -> max tolerance
}
function nsfwNote() {
  $("nsfwnote").textContent = state.nsfw
    ? "permissive — safety filter off where the model supports it"
    : "safety filter ON (provider default)";
}
function renderNsfw(model) {
  const sp = modelSafetyParams(model);
  const show = state.service === "fal" && (sp.checker || sp.tolerance);
  $("nsfwwrap").style.display = show ? "" : "none";
  if (!show) return;
  $("nsfw").checked = state.nsfw;
  syncSafetyControls();
  nsfwNote();
}
$("nsfw").addEventListener("change", () => {
  state.nsfw = $("nsfw").checked;
  syncSafetyControls();
  nsfwNote();
  api().set_config({ ui_nsfw: state.nsfw });
});
$("nsfwinfo").addEventListener("click", () => {
  $("nsfwrows").innerHTML = NSFW_POLICY.map(r => `
    <div class="nsfw-row allow-${r.allow}">
      <div class="nsfw-head"><b>${SVC_LABELS[r.p] || r.p}</b><span class="nsfw-badge">${r.allow === "yes" ? "permitted" : r.allow === "partial" ? "model-dependent" : "hard filter"}</span></div>
      <div class="nsfw-pol">${r.policy}</div>
      <div class="nsfw-cfg"><span>config</span> ${escapeHtml(r.config)}</div>
    </div>`).join("");
  $("nsfwpanel").hidden = false;
});
$("nsfwpanelclose").addEventListener("click", () => { $("nsfwpanel").hidden = true; });
$("nsfwpanel").addEventListener("click", e => { if (e.target.id === "nsfwpanel") $("nsfwpanel").hidden = true; });

function renderLoras() {
  const svc = state.service === "huggingface" ? "huggingface" : state.service === "replicate" ? "replicate" : null;
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
    </div>`).join("");
  $("loras").querySelectorAll("[data-li]").forEach(el => el.addEventListener("change", async () => {
    state.loras[svc] = await api().lora_set(svc, +el.dataset.li, { enabled: el.checked }); renderLoras();
  }));
  $("loras").querySelectorAll("[data-ls]").forEach(el => el.addEventListener("change", async () => {
    state.loras[svc] = await api().lora_set(svc, +el.dataset.ls, { scale: +el.value });
  }));
  $("loras").querySelectorAll("[data-lx]").forEach(el => el.addEventListener("click", async () => {
    state.loras[svc] = await api().lora_remove(svc, +el.dataset.lx); renderLoras();
  }));
}

/* ---------- gallery ---------- */
// WebView2 blocks file:// sub-resources from a file:// page — serve via the
// localhost media server instead (basename resolves against the output dir).
function fileUrl(p) {
  const name = p.split(/[\\/]/).pop();
  return state.mediaBase ? state.mediaBase + encodeURIComponent(name)
                         : "file:///" + p.replace(/\\/g, "/");
}
function mediaTag(f) {
  const name = f.split(/[\\/]/).pop();
  const ext = f.split(".").pop().toLowerCase();
  if (["mp4", "webm", "mov"].includes(ext)) return `<video src="${fileUrl(f)}" controls muted></video>`;
  if (["mp3", "wav", "m4a", "flac"].includes(ext)) return `<audio src="${fileUrl(f)}" controls></audio>`;
  if (["glb", "obj", "stl", "bin"].includes(ext))
    return `<div class="filecard">🧊<br>${name}<br><small>3D model — open in a viewer</small></div>`;
  if (["txt", "json"].includes(ext))
    return `<div class="filecard txt" data-txt="${fileUrl(f)}">📄<br>${name}<br><small>text output — click Save As to keep</small></div>`;
  return `<img src="${fileUrl(f)}" alt="">`;
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
      ${mediaTag(g.file)}
      <div class="acts">
        <button data-save="${i}">Save As</button>
        <button data-open="${i}">Folder</button>
      </div>
      <div class="meta"><span><b>${g.meta.model.split("/").pop()}</b>${g.meta.seed ? " · " + g.meta.seed : ""}</span><span>${g.time}</span></div>
    </div>`).join("");
  $("outinfo").textContent = `OUTPUT · ${state.outDirName}/ · ${state.gallery.length} this session`;
  $("sessioninfo").textContent = `v2.0 · ${state.genCount} generated`;
  applyGrid();
  $("gallery").querySelectorAll(".tile").forEach(t => t.addEventListener("click", e => {
    if (e.target.closest(".acts")) return;
    openLightbox(state.gallery[+t.dataset.i].file);   // #7 click-to-enlarge
  }));
  $("gallery").querySelectorAll("[data-save]").forEach(b => b.addEventListener("click", () =>
    api().save_as(state.gallery[+b.dataset.save].file)));
  $("gallery").querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () =>
    api().open_output_folder()));
}

/* ---------- #7 lightbox + #9 metadata overlay ---------- */
async function openLightbox(file) {
  state.lbFile = file;
  $("lbmedia").innerHTML = mediaTag(file);          // reuse the media renderer (img/video/audio)
  $("lbside").innerHTML = `<div class="lbm-title">Metadata <em>loading…</em></div>`;
  $("lightbox").hidden = false;
  try {
    const m = await api().read_meta(file);
    $("lbside").innerHTML = renderMeta(m, file);
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
  return html;
}
function closeLightbox() { $("lightbox").hidden = true; state.lbFile = null; $("lbmedia").innerHTML = ""; }
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
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("lightbox").hidden) closeLightbox(); });

/* ---------- browse landing (models strip only — pick a model to start) ---------- */
async function renderBrowse() {
  const wrap = $("browse");
  const models = modelsFor(state.service, state.category);
  const cur = currentModel();
  const cards = models.slice(0, 24).map(m => {
    const on = cur && m.id === cur.id ? " on" : "";
    const img = m.thumb ? `<img src="${m.thumb}" loading="lazy">` : `<div class="mc-ph">${(m.label || m.id).slice(0, 2)}</div>`;
    return `<div class="mcard${on}" data-mid="${m.id}">${img}
      <div class="mc-t" title="${m.label || m.id}">${m.label || m.id}</div>
      <div class="mc-p">${m.price || ""}</div></div>`;
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

/* ---------- library view (all output files — its own tab) ---------- */
async function renderLibrary() {
  const wrap = $("library");
  wrap.innerHTML = `<div class="s2lbl">Library <em>loading…</em></div><div class="wmason" id="libmason"></div>`;
  let files = [];
  try { files = await api().recent_files(500); } catch (e) { files = []; }
  wrap.querySelector(".s2lbl em").textContent = `${files.length} files · ${state.outDirName}/`;
  const mason = $("libmason");
  if (!files.length) { mason.innerHTML = `<div class="emptystate">no images yet — generate something</div>`; return; }
  mason.innerHTML = files.map((r, i) => `
    <div class="wtile" data-wi="${i}">
      ${mediaTag(r.file)}
      <div class="wmeta"><b>${r.file.split(".").pop()}</b><span data-open="${i}">open folder</span></div>
    </div>`).join("");
  applyGrid();
  mason.querySelectorAll("[data-open]").forEach(s => s.addEventListener("click", (e) => {
    e.stopPropagation(); api().open_output_folder();
  }));
  mason.querySelectorAll(".wtile").forEach(t => t.addEventListener("click", e => {
    if (e.target.closest("[data-open]")) return;
    openLightbox(files[+t.dataset.wi].file);   // #7 lightbox from library too
  }));
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
    const thumbs = files.map(f => `<div class="h-thumb">${mediaTag(f)}</div>`).join("");
    const when = (r.ts || "").replace("T", " ").slice(0, 16);
    return `<div class="h-row" data-i="${i}">
      <div class="h-thumbs">${thumbs || '<div class="h-thumb none">—</div>'}</div>
      <div class="h-meta">
        <div class="h-prompt">${escapeHtml(r.prompt || "(no prompt)")}</div>
        <div class="h-sub"><b>${(r.model || "").split("/").pop()}</b> · ${r.service || ""} · ${when}${r.seed ? " · seed " + r.seed : ""}</div>
        <div class="h-acts">
          <button data-reuse="${i}">↻ reuse prompt</button>
          <button data-copy="${i}">copy prompt</button>
        </div>
      </div>
    </div>`;
  }).join("");

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
    prompt, params: collectParams(cur), input_files: inputFiles,
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
