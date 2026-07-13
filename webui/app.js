/* AI Studio Void — web UI client v2. Registry-driven (webui/models.json via bridge). */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  tab: "image",            // image | video (virality disabled)
  provider: "fal",
  model: "fal-ai/flux-2/turbo",
  dims: "1:1", batch: 4, guidance: 3.5, seed: null, enhance: false,
  imageData: null,         // base64 data URI for img2img / i2v
  registry: { providers: {}, models: [] },
  ready: {},               // provider -> bool (env key present)
};

function api() { return window.pywebview && window.pywebview.api; }
function toast(msg) {
  let t = $("#toast"); if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 3200);
}
function setStatus(s) { $("#status").textContent = s; }

function currentEntry() { return state.registry.models.find(m => m.id === state.model) || {}; }
function modelsFor(provider, kind) { return state.registry.models.filter(m => m.provider === provider && m.kind === kind); }

async function boot() {
  let tries = 0;
  while (!api() && tries++ < 50) await new Promise(r => setTimeout(r, 100));
  if (!api()) { setStatus("bridge offline"); return; }
  state.registry = await api().models();
  (await api().providers()).forEach(p => state.ready[p.name] = p.ready);
  wireProviders();
  rebuildModelSelect();
  await renderLoras();
  await renderGallery();
  wireControls();
  setStatus("ready");
}

function wireProviders() {
  $$("#providers .chip[data-provider]").forEach(c => {
    const p = c.dataset.provider;
    if (!state.ready[p]) { c.style.opacity = ".38"; c.title = "no API key in .env — greyed until added"; }
    c.onclick = () => {
      if (!state.ready[p]) { toast(`${p}: no API key set — add ${state.registry.providers[p].key_env} to .env`); return; }
      if (!modelsFor(p, state.tab).length) { toast(`${p} has no ${state.tab} models`); return; }
      state.provider = p;
      $$("#providers .chip[data-provider]").forEach(x => x.classList.toggle("on", x.dataset.provider === p));
      rebuildModelSelect();
    };
  });
}

function rebuildModelSelect() {
  const list = modelsFor(state.provider, state.tab);
  const sel = $("#modelSelect"); sel.innerHTML = "";
  list.forEach(m => { const o = document.createElement("option"); o.value = m.id; o.textContent = m.label; sel.appendChild(o); });
  state.model = list.length ? list[0].id : "";
  sel.value = state.model;
  sel.onchange = () => { state.model = sel.value; refreshModelUI(); };
  refreshModelUI();
}

function refreshModelUI() {
  const e = currentEntry();
  $("#modelName").textContent = e.label || state.model || "—";
  $("#modelProv").textContent = (state.registry.providers[state.provider] || {}).label || state.provider;
  // dynamic param visibility from the registry schema (restores the old app's per-model forms)
  const has = (p) => (e.params || []).includes(p);
  $("#batchV").parentElement.style.display = has("batch") ? "" : "none";
  $("#batch").style.display = has("batch") ? "" : "none";
  $("#guidV").parentElement.style.display = has("guidance") ? "" : "none";
  $("#guidance").style.display = has("guidance") ? "" : "none";
  $("#seedV").parentElement.style.display = has("seed") ? "" : "none";
  $("#dims").style.display = has("dims") ? "" : "none";
  // image input row only for models that declare one
  const needsImg = !!e.image_input;
  $("#imgInputRow").style.display = needsImg ? "" : "none";
  if (!needsImg) { state.imageData = null; $("#imgInputLabel").textContent = "+ source image (img2img / i2v)"; }
}

async function renderLoras() {
  const loras = await api().lora_list();
  const box = $("#loraStack");
  box.querySelectorAll(".lrow:not(.addrow)").forEach(el => el.remove());
  const add = $("#addLora");
  loras.forEach((l, i) => {
    const row = document.createElement("div"); row.className = "lrow";
    const tgl = document.createElement("span"); tgl.className = "tgl" + (l.enabled ? "" : " off");
    tgl.onclick = async () => { await api().lora_toggle(i); renderLoras(); };
    const nm = document.createElement("span"); nm.className = "ln"; nm.textContent = l.url.split("/").pop();
    const sc = document.createElement("span"); sc.className = "sc"; sc.textContent = Number(l.scale).toFixed(2);
    sc.onclick = async () => { const v = prompt("LoRA scale (0-1.5):", l.scale); if (v !== null) { await api().lora_set_scale(i, parseFloat(v)); renderLoras(); } };
    const rm = document.createElement("span"); rm.className = "rm"; rm.textContent = "×";
    rm.onclick = async () => { await api().lora_remove(i); renderLoras(); };
    row.append(tgl, nm, sc, rm);
    box.insertBefore(row, add);
  });
  add.onclick = async () => {
    const url = prompt("LoRA URL (.safetensors):"); if (!url) return;
    await api().lora_add(url, 0.8); renderLoras();
  };
}

async function renderGallery() {
  const items = await api().gallery(48);
  const g = $("#gallery"); g.innerHTML = "";
  $("#empty").style.display = items.length ? "none" : "block";
  items.forEach(it => {
    const fig = document.createElement("figure"); fig.className = "m";
    const media = it.kind === "video"
      ? Object.assign(document.createElement("video"), { src: it.url, muted: true, loop: true, controls: true })
      : Object.assign(new Image(), { src: it.url, loading: "lazy" });
    const cap = document.createElement("figcaption"); cap.textContent = it.name;
    const acts = document.createElement("div"); acts.className = "acts";
    const reuse = document.createElement("span"); reuse.textContent = "Use as input";
    reuse.onclick = async () => {
      const r = await fetch(it.url); const blob = await r.blob();
      const fr = new FileReader();
      fr.onload = () => { state.imageData = fr.result; $("#imgInputLabel").textContent = "✓ " + it.name; toast("Set as source image (pick an img2img / i2v model)"); };
      fr.readAsDataURL(blob);
    };
    acts.appendChild(reuse);
    fig.append(media, acts, cap);
    g.appendChild(fig);
  });
}

function wireControls() {
  $$("#tabs span").forEach(t => t.onclick = () => {
    if (t.hasAttribute("data-disabled")) { toast(t.getAttribute("data-reason")); return; }
    state.tab = t.dataset.tab;
    $$("#tabs span").forEach(x => x.classList.toggle("on", x === t));
    // keep provider valid for this tab (video is fal-only today)
    if (!modelsFor(state.provider, state.tab).length) {
      const p = Object.keys(state.registry.providers).find(p => state.ready[p] && modelsFor(p, state.tab).length);
      if (p) { state.provider = p; $$("#providers .chip[data-provider]").forEach(x => x.classList.toggle("on", x.dataset.provider === p)); }
    }
    rebuildModelSelect();
  });
  $$("#dims .dim").forEach(d => d.onclick = () => { state.dims = d.dataset.dim; $$("#dims .dim").forEach(x => x.classList.toggle("on", x === d)); });
  $("#batch").oninput = e => { state.batch = +e.target.value; $("#batchV").textContent = state.batch; };
  $("#guidance").oninput = e => { state.guidance = +e.target.value; $("#guidV").textContent = state.guidance.toFixed(1); };
  $("#enhance").onclick = () => { state.enhance = !state.enhance; $("#enhance").classList.toggle("off", !state.enhance); };
  $("#seedV").onclick = () => { const v = prompt("Seed (blank = random):", state.seed ?? ""); state.seed = v ? parseInt(v) : null; $("#seedV").innerHTML = state.seed === null ? "random ↻" : String(state.seed); };
  $("#imgInput").onchange = (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fr = new FileReader();
    fr.onload = () => { state.imageData = fr.result; $("#imgInputLabel").textContent = "✓ " + f.name; };
    fr.readAsDataURL(f);
  };
  const histBtn = $("#histBtn");
  histBtn.onclick = async () => {
    let pop = $("#histPop");
    if (pop && pop.style.display === "block") { pop.style.display = "none"; return; }
    const hist = await api().history_list();
    if (!pop) { pop = document.createElement("div"); pop.id = "histPop"; document.body.appendChild(pop); }
    pop.innerHTML = ""; (hist.length ? hist : ["(no history yet)"]).forEach(h => {
      const d = document.createElement("div"); d.textContent = h;
      d.onclick = () => { $("#prompt").value = h; pop.style.display = "none"; };
      pop.appendChild(d);
    });
    pop.style.display = "block";
  };
  $("#genBtn").onclick = doGenerate;
  $("#prompt").addEventListener("keydown", e => { if (e.key === "Enter") doGenerate(); });
}

async function doGenerate() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) { toast("Enter a prompt first"); return; }
  const e = currentEntry();
  if (e.image_input && !state.imageData) { toast("This model needs a source image — click '+ source image' or 'Use as input' on a gallery item"); return; }
  const btn = $("#genBtn"); btn.disabled = true;
  setStatus(e.kind === "video" ? "generating video… (can take minutes)" : "generating…");
  try {
    await api().history_add(prompt);
    const res = await api().generate(prompt, state.model, state.provider, state.batch, state.seed,
                                     state.dims, state.guidance, state.enhance, false, state.imageData);
    if (res.error) { toast(res.error); setStatus("error"); }
    else { toast(`Saved ${res.files.length} file(s) — ${res.model}`); setStatus("ready"); await renderGallery(); }
  } catch (err) { toast(String(err)); setStatus("error"); }
  finally { btn.disabled = false; }
}

window.addEventListener("DOMContentLoaded", boot);
