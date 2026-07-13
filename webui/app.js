/* AI Studio Void — schema-driven client (P1). Catalog + per-model form come from the bridge live. */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  tab: "image",
  provider: "fal",
  model: null,
  catalog: [],        // [{id,label,kind}] for current provider+tab
  ready: {},          // provider -> bool
  providerLabels: {}, // provider -> label
};

function api() { return window.pywebview && window.pywebview.api; }
function toast(m) {
  let t = $("#toast"); if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; document.body.appendChild(t); }
  t.textContent = m; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 3400);
}
function setStatus(s) { $("#status").textContent = s; }
function asObj(v) { return typeof v === "string" ? JSON.parse(v) : v; }  // some pywebview builds return JSON strings

async function boot() {
  try {
    let tries = 0;
    while (!api() && tries++ < 80) await new Promise(r => setTimeout(r, 100));
    if (!api()) { setStatus("bridge offline"); return; }
    const provs = asObj(await api().providers());
    provs.forEach(p => { state.ready[p.name] = p.ready; state.providerLabels[p.name] = p.label; });
    wireProviders(); wireTabs(); wireControls();
    await loadCatalog();
    await renderGallery();
    setStatus("ready");
  } catch (e) { setStatus("boot error: " + (e.message || e)); console.error(e); }
}

function wireProviders() {
  $$("#providers .chip[data-provider]").forEach(c => {
    const p = c.dataset.provider;
    if (!state.ready[p]) { c.style.opacity = ".38"; c.title = "no API key in .env"; }
    c.onclick = async () => {
      if (!state.ready[p]) { toast(`${p}: no API key set`); return; }
      state.provider = p;
      $$("#providers .chip").forEach(x => x.classList.toggle("on", x.dataset.provider === p));
      await loadCatalog();
    };
  });
}

function wireTabs() {
  $$("#tabs span").forEach(t => t.onclick = async () => {
    if (t.hasAttribute("data-disabled")) { toast(t.getAttribute("data-reason")); return; }
    state.tab = t.dataset.tab;
    $$("#tabs span").forEach(x => x.classList.toggle("on", x === t));
    await loadCatalog();
  });
}

async function loadCatalog(refresh) {
  setStatus(refresh ? "refreshing catalog…" : "loading models…");
  let cat = [];
  try { cat = asObj(await api().catalog(state.provider, state.tab, !!refresh)); }
  catch (e) { toast("catalog error: " + (e.message || e)); }
  // provider may not serve this tab's kind (e.g. only fal has video) -> fall to fal
  if (!cat.length && state.tab === "video" && state.provider !== "fal" && state.ready.fal) {
    state.provider = "fal";
    $$("#providers .chip").forEach(x => x.classList.toggle("on", x.dataset.provider === "fal"));
    cat = asObj(await api().catalog("fal", "video"));
  }
  state.catalog = cat || [];
  renderModelOptions();
  setStatus(`ready · ${state.catalog.length} ${state.tab} models`);
}

function renderModelOptions() {
  const filter = ($("#modelFilter").value || "").toLowerCase();
  const sel = $("#modelSelect"); sel.innerHTML = "";
  const shown = state.catalog.filter(m => !filter || m.id.toLowerCase().includes(filter) || (m.label || "").toLowerCase().includes(filter));
  shown.forEach(m => { const o = document.createElement("option"); o.value = m.id; o.textContent = m.label || m.id; sel.appendChild(o); });
  $("#modelCount").textContent = shown.length === state.catalog.length ? `(${state.catalog.length})` : `(${shown.length}/${state.catalog.length})`;
  if (shown.length) { sel.value = (shown.find(m => m.id === state.model) ? state.model : shown[0].id); selectModel(sel.value); }
  else { state.model = null; $("#dynForm").innerHTML = '<div class="fhint">no models match</div>'; }
}

async function selectModel(id) {
  state.model = id;
  const m = state.catalog.find(x => x.id === id) || {};
  $("#modelMeta").textContent = m.desc || id;
  $("#dynForm").innerHTML = '<div class="fhint">loading params…</div>';
  let spec = [];
  try { spec = asObj(await api().form_spec(id, state.provider)); }
  catch (e) { $("#dynForm").innerHTML = '<div class="fhint">schema error: ' + (e.message || e) + '</div>'; return; }
  renderForm(spec, $("#dynForm"), { renderLoras: renderLoraBox });
}

async function renderLoraBox(box) {
  const loras = asObj(await api().lora_list());
  box.innerHTML = "";
  loras.forEach((l, i) => {
    const row = document.createElement("div"); row.className = "lrow";
    const tgl = document.createElement("span"); tgl.className = "tgl" + (l.enabled ? "" : " off");
    tgl.onclick = async () => { await api().lora_toggle(i); renderLoraBox(box); };
    const nm = document.createElement("span"); nm.className = "ln"; nm.textContent = l.url.split("/").pop();
    const sc = document.createElement("span"); sc.className = "sc"; sc.textContent = Number(l.scale).toFixed(2);
    sc.onclick = async () => { const v = prompt("LoRA scale (0-1.5):", l.scale); if (v !== null) { await api().lora_set_scale(i, parseFloat(v)); renderLoraBox(box); } };
    const rm = document.createElement("span"); rm.className = "rm"; rm.textContent = "×";
    rm.onclick = async () => { await api().lora_remove(i); renderLoraBox(box); };
    row.append(tgl, nm, sc, rm); box.appendChild(row);
  });
  const add = document.createElement("div"); add.className = "lrow addrow"; add.textContent = "+ Add LoRA";
  add.onclick = async () => { const url = prompt("LoRA URL (.safetensors):"); if (url) { await api().lora_add(url, 0.8); renderLoraBox(box); } };
  box.appendChild(add);
}

async function renderGallery() {
  const items = asObj(await api().gallery(48));
  const g = $("#gallery"); g.innerHTML = "";
  $("#empty").style.display = items.length ? "none" : "block";
  items.forEach(it => {
    const fig = document.createElement("figure"); fig.className = "m";
    const media = it.kind === "video"
      ? Object.assign(document.createElement("video"), { src: it.url, muted: true, loop: true, controls: true })
      : Object.assign(new Image(), { src: it.url, loading: "lazy" });
    const cap = document.createElement("figcaption"); cap.textContent = it.name;
    fig.append(media, cap); g.appendChild(fig);
  });
}

function wireControls() {
  $("#modelFilter").oninput = renderModelOptions;
  $("#modelSelect").onchange = (e) => selectModel(e.target.value);
  $("#refreshCatalog").onclick = () => loadCatalog(true);
  $("#histBtn").onclick = async () => {
    let pop = $("#histPop");
    if (pop && pop.style.display === "block") { pop.style.display = "none"; return; }
    const hist = asObj(await api().history_list());
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
  const promptText = $("#prompt").value.trim();
  if (!promptText) { toast("Enter a prompt first"); return; }
  if (!state.model) { toast("No model selected"); return; }
  const params = collectParams($("#dynForm"));
  params.prompt = promptText;
  const btn = $("#genBtn"); btn.disabled = true;
  setStatus(state.tab === "video" ? "generating video… (minutes)" : "generating…");
  try {
    await api().history_add(promptText);
    const res = asObj(await api().generate(state.model, params, state.provider));
    if (res.error) { toast(res.error); setStatus("error"); }
    else { toast(`Saved ${res.files.length} file(s)`); setStatus("ready"); await renderGallery(); }
  } catch (e) { toast(String(e)); setStatus("error"); }
  finally { btn.disabled = false; }
}

window.addEventListener("DOMContentLoaded", boot);
