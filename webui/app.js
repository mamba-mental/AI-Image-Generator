/* AI Studio Void — web UI client. Calls bridge.Api via window.pywebview.api.* */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  provider: "fal",
  model: "fal-ai/flux-2/turbo",
  dims: "1:1",
  batch: 4,
  guidance: 3.5,
  seed: null,
  enhance: false,
  catalog: {},
};

const PROV_LABEL = { fal: "fal.ai", replicate: "replicate", hf: "hugging face", gemini: "gemini" };
const MODEL_NICE = { "fal-ai/flux-2/turbo": "FLUX.2 [Turbo]", "fal-ai/flux-2/flash": "FLUX.2 [Flash]",
  "fal-ai/flux-2": "FLUX.2 [dev]", "fal-ai/flux-2-pro": "FLUX.2 [pro]", "fal-ai/flux-2/lora": "FLUX.2 [LoRA]" };

function api() { return window.pywebview && window.pywebview.api; }
function toast(msg) {
  let t = $("#toast"); if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2600);
}
function setStatus(s) { $("#status").textContent = s; }

async function boot() {
  // wait for pywebview bridge
  let tries = 0;
  while (!api() && tries++ < 50) await new Promise(r => setTimeout(r, 100));
  if (!api()) { setStatus("bridge offline"); return; }
  await buildProviders();
  await buildModels();
  await renderLoras();
  await renderGallery();
  wireControls();
  setStatus("ready");
}

async function buildProviders() {
  const provs = await api().providers();
  const box = $("#providers"); box.innerHTML = "";
  provs.forEach(p => {
    const c = document.createElement("span");
    c.className = "chip" + (p === state.provider ? " on" : "");
    c.dataset.provider = p; c.textContent = p;
    c.onclick = async () => { state.provider = p; $$("#providers .chip").forEach(x => x.classList.toggle("on", x.dataset.provider === p)); await buildModels(); };
    box.appendChild(c);
  });
}

async function buildModels() {
  state.catalog = await api().models();
  const list = state.catalog[state.provider] || [];
  const sel = $("#modelSelect"); sel.innerHTML = "";
  list.forEach(m => { const o = document.createElement("option"); o.value = m; o.textContent = m; sel.appendChild(o); });
  state.model = list[0] || "";
  sel.value = state.model;
  updateModelLabel();
  sel.onchange = () => { state.model = sel.value; updateModelLabel(); };
}
function updateModelLabel() {
  $("#modelName").textContent = MODEL_NICE[state.model] || state.model;
  $("#modelProv").textContent = PROV_LABEL[state.provider] || state.provider;
}

async function renderLoras() {
  const loras = await api().lora_list();
  const box = $("#loraStack");
  box.querySelectorAll(".lrow:not(.addrow)").forEach(e => e.remove());
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
      ? Object.assign(document.createElement("video"), { src: it.url, muted: true, loop: true, onmouseover: e => e.target.play(), onmouseout: e => e.target.pause() })
      : Object.assign(new Image(), { src: it.url, loading: "lazy" });
    const cap = document.createElement("figcaption"); cap.textContent = it.name;
    const acts = document.createElement("div"); acts.className = "acts";
    ["Reuse", "⬇"].forEach(lbl => { const s = document.createElement("span"); s.textContent = lbl; acts.appendChild(s); });
    fig.append(media, acts, cap);
    g.appendChild(fig);
  });
}

function wireControls() {
  // tabs (disabled ones just explain themselves)
  $$("#tabs span").forEach(t => t.onclick = () => {
    if (t.hasAttribute("data-disabled")) { toast(t.getAttribute("data-reason")); return; }
    $$("#tabs span").forEach(x => x.classList.toggle("on", x === t));
  });
  // dims
  $$("#dims .dim").forEach(d => d.onclick = () => { state.dims = d.dataset.dim; $$("#dims .dim").forEach(x => x.classList.toggle("on", x === d)); });
  // sliders
  $("#batch").oninput = e => { state.batch = +e.target.value; $("#batchV").textContent = state.batch; };
  $("#guidance").oninput = e => { state.guidance = +e.target.value; $("#guidV").textContent = state.guidance.toFixed(1); };
  $("#enhance").onclick = () => { state.enhance = !state.enhance; $("#enhance").classList.toggle("off", !state.enhance); };
  $("#seedV").onclick = () => { const v = prompt("Seed (blank = random):", state.seed ?? ""); state.seed = v ? parseInt(v) : null; $("#seedV").innerHTML = state.seed === null ? "random ↻" : String(state.seed); };
  // history popup
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
  // generate
  $("#genBtn").onclick = doGenerate;
  $("#prompt").addEventListener("keydown", e => { if (e.key === "Enter") doGenerate(); });
}

async function doGenerate() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) { toast("Enter a prompt first"); return; }
  const btn = $("#genBtn"); btn.disabled = true; setStatus("generating…");
  try {
    await api().history_add(prompt);
    const res = await api().generate(prompt, state.model, state.provider, state.batch, state.seed, state.dims, state.guidance, state.enhance, false);
    if (res.error) { toast(res.error); setStatus("error"); }
    else { toast(`Generated ${res.files.length} image(s)`); setStatus("ready"); await renderGallery(); }
  } catch (e) { toast(String(e)); setStatus("error"); }
  finally { btn.disabled = false; }
}

window.addEventListener("DOMContentLoaded", boot);
