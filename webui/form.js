/* FormSpec -> DOM. renderForm(spec, host, ctx) builds controls; collectParams(host) reads them back.
   Runs in the browser (pywebview) AND standalone under node for a self-check (see bottom). */

function _el(tag, attrs, children) {
  const e = (typeof document !== "undefined") ? document.createElement(tag) : { tag, attrs: {}, children: [], value: "", checked: false, dataset: {}, appendChild(c){this.children.push(c);}, querySelectorAll(){return [];}, addEventListener(){}, setAttribute(k,v){this.attrs[k]=v;} };
  if (attrs) for (const k in attrs) { if (k === "class") e.className = attrs[k]; else if (k === "text") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]); }
  (children || []).forEach(c => e.appendChild(c));
  return e;
}

// Build a control for one field. Returns {node, get} where get() -> [name, value] or null.
function buildField(f, ctx) {
  const wrap = _el("div", { class: "field", "data-name": f.name });
  const lab = _el("label", { class: "flabel", text: f.label || f.name });
  wrap.appendChild(lab);
  let get = () => null;

  if (f.widget === "select") {
    const sel = _el("select", { class: "fctl" });
    (f.enum || []).forEach(v => { const o = _el("option", { value: v, text: v }); if (String(v) === String(f.default)) o.selected = true; sel.appendChild(o); });
    if (typeof f.default !== "undefined") sel.value = String(f.default);
    wrap.appendChild(sel);
    get = () => [f.name, sel.value];
  } else if (f.widget === "toggle") {
    const cb = _el("input", { type: "checkbox", class: "fctl ftoggle" });
    cb.checked = !!f.default;
    wrap.appendChild(cb);
    get = () => [f.name, !!cb.checked];
  } else if (f.widget === "slider") {
    const row = _el("div", { class: "sliderrow" });
    const rng = _el("input", { type: "range", class: "fctl slider", min: f.min, max: f.max, step: f.step });
    rng.value = f.default;
    const val = _el("span", { class: "sval", text: String(f.default) });
    if (typeof rng.addEventListener === "function") rng.addEventListener("input", () => { val.textContent = rng.value; });
    row.appendChild(rng); row.appendChild(val); wrap.appendChild(row);
    get = () => [f.name, f.int ? parseInt(rng.value) : parseFloat(rng.value)];
  } else if (f.widget === "number") {
    const inp = _el("input", { type: "number", class: "fctl" });
    inp.value = f.default;
    wrap.appendChild(inp);
    get = () => { const v = inp.value; if (v === "") return null; return [f.name, f.int ? parseInt(v) : parseFloat(v)]; };
  } else if (f.widget === "image") {
    const btn = _el("label", { class: "fctl imgpick", text: "+ source image" });
    const inp = _el("input", { type: "file", accept: "image/*", style: "display:none" });
    let dataUri = null;
    if (typeof inp.addEventListener === "function") inp.addEventListener("change", () => {
      const file = inp.files[0]; if (!file) return;
      const fr = new FileReader(); fr.onload = () => { dataUri = fr.result; btn.textContent = "✓ " + file.name; }; fr.readAsDataURL(file);
    });
    btn.appendChild(inp); wrap.appendChild(btn);
    get = () => dataUri ? [f.name, f.multi ? [dataUri] : dataUri] : null;
  } else if (f.widget === "loras") {
    const box = _el("div", { class: "fctl lorabox" });
    if (ctx && ctx.renderLoras) ctx.renderLoras(box);
    wrap.appendChild(box);
    get = () => null; // LoRAs travel via the bridge lora_* state, injected server-side
  } else {
    const inp = _el("input", { type: "text", class: "fctl" });
    inp.value = f.default || "";
    wrap.appendChild(inp);
    get = () => { const v = inp.value; return v === "" ? null : [f.name, v]; };
  }
  wrap._get = get;
  return wrap;
}

function renderForm(spec, host, ctx) {
  host.innerHTML = "";
  host._fields = [];
  (spec || []).forEach(f => { const node = buildField(f, ctx); host.appendChild(node); host._fields.push(node); });
  return host;
}

function collectParams(host) {
  const out = {};
  (host._fields || []).forEach(node => { const kv = node._get && node._get(); if (kv) out[kv[0]] = kv[1]; });
  return out;
}

function hasLoras(spec) { return (spec || []).some(f => f.widget === "loras"); }

if (typeof module !== "undefined") module.exports = { buildField, renderForm, collectParams, hasLoras };

// ---- node self-check (AC-7) ----
if (typeof require !== "undefined" && require.main === module) {
  const spec = [
    { name: "image_size", widget: "select", enum: ["square", "portrait_3_4"], default: "square" },
    { name: "num_images", widget: "number", int: true, default: 4 },
    { name: "guidance_scale", widget: "slider", min: 0, max: 10, step: 0.5, default: 3.5 },
    { name: "enable_safety_checker", widget: "toggle", default: true },
    { name: "loras", widget: "loras" },
  ];
  const host = { innerHTML: "", _fields: [], appendChild(c){this._fields.push(c);} };
  // emulate renderForm building fields (document is stubbed by _el)
  host._fields = [];
  spec.forEach(f => host._fields.push(buildField(f, {})));
  // slider get returns number, select returns default, toggle bool, number int, loras null
  const got = collectParams(host);
  const assert = (c, m) => { if (!c) { console.error("FAIL", m); process.exit(1); } };
  assert(got.image_size === "square", "select default");
  assert(got.num_images === 4, "number int");
  assert(got.guidance_scale === 3.5, "slider float");
  assert(got.enable_safety_checker === true, "toggle bool");
  assert(!("loras" in got), "loras excluded from params");
  assert(hasLoras(spec) === true, "hasLoras true");
  assert(hasLoras(spec.slice(0, 2)) === false, "hasLoras false");
  console.log("form.js self-check OK");
}
