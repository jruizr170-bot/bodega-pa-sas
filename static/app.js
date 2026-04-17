/* app.js — Formulario de nueva recepción */

const API = "";
let itemCount = 0;
let fotoFiles = [];   // array de File objects

// ── Carga inicial ─────────────────────────────────────────────────────────────
async function init() {
  const bodegas = await fetch(`${API}/api/bodegas`).then(r => r.json());

  const selBodega = document.getElementById("bodega_id");
  bodegas.forEach(b => {
    const opt = document.createElement("option");
    opt.value = b.id;
    opt.textContent = `${b.codigo} – ${b.nombre}`;
    selBodega.appendChild(opt);
  });

  const inputNombre = document.getElementById("usuario_nombre");
  const savedNombre = localStorage.getItem("pa_usuario_nombre");
  if (savedNombre) inputNombre.value = savedNombre;
  inputNombre.addEventListener("change", () => {
    localStorage.setItem("pa_usuario_nombre", inputNombre.value.trim());
  });

  document.getElementById("fecha_factura").valueAsDate = new Date();
}

// ── Autocomplete genérico ─────────────────────────────────────────────────────
function makeAutocomplete({ input, dropdown, fetchFn, onSelect, onClear }) {
  let debounceTimer = null;
  let items = [];
  let activeIdx = -1;

  function show(list) {
    items = list; activeIdx = -1;
    dropdown.innerHTML = "";
    if (!list.length) { hide(); return; }
    list.forEach((item, i) => {
      const div = document.createElement("div");
      div.className = "ac-item";
      div.textContent = item.label;
      div.addEventListener("mousedown", e => { e.preventDefault(); select(i); });
      dropdown.appendChild(div);
    });
    dropdown.classList.remove("hidden");
  }

  function hide() { dropdown.classList.add("hidden"); items = []; }

  function select(i) {
    if (items[i]) { input.value = items[i].label; onSelect(items[i]); }
    hide();
  }

  input.addEventListener("input", () => {
    onClear();
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (!q.length) { hide(); return; }
    debounceTimer = setTimeout(async () => show(await fetchFn(q)), 220);
  });

  input.addEventListener("keydown", e => {
    if (dropdown.classList.contains("hidden")) return;
    if (e.key === "ArrowDown") activeIdx = Math.min(activeIdx + 1, items.length - 1);
    else if (e.key === "ArrowUp") activeIdx = Math.max(activeIdx - 1, 0);
    else if (e.key === "Enter") { e.preventDefault(); select(activeIdx); }
    else if (e.key === "Escape") hide();
    else return;
    [...dropdown.children].forEach((c, i) => c.classList.toggle("active", i === activeIdx));
  });

  document.addEventListener("click", e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) hide();
  });
}

// ── Proveedor autocomplete ────────────────────────────────────────────────────
function initProveedorAC() {
  const input    = document.getElementById("prov-input");
  const dropdown = document.getElementById("prov-dropdown");
  const hiddenId = document.getElementById("proveedor_id");
  const nitInput = document.getElementById("prov-nit");

  makeAutocomplete({
    input, dropdown,
    fetchFn: async q => {
      const data = await fetch(`${API}/api/proveedores?q=${encodeURIComponent(q)}&limit=8`).then(r => r.json());
      return data.map(p => ({ label: `${p.nombre} (${p.nit})`, id: p.id, nombre: p.nombre, nit: p.nit }));
    },
    onSelect: item => {
      hiddenId.value = item.id;
      nitInput.value = item.nit;
      nitInput.readOnly = true;
      nitInput.classList.add("bg-gray-50");
    },
    onClear: () => {
      hiddenId.value = "";
      nitInput.value = "";
      nitInput.readOnly = false;
      nitInput.classList.remove("bg-gray-50");
    },
  });
}

// ── Items ─────────────────────────────────────────────────────────────────────
function refreshEmpty() {
  const container = document.getElementById("items-container");
  document.getElementById("items-empty").classList.toggle("hidden", container.children.length > 0);
}

function addItem() {
  const tmpl  = document.getElementById("item-template");
  const clone = tmpl.content.cloneNode(true);
  const row   = clone.querySelector(".item-row");
  row.dataset.idx = itemCount++;

  const descInput  = row.querySelector("[name=descripcion]");
  const prodDrop   = row.querySelector(".prod-dropdown");
  const prodHidden = row.querySelector("[name=producto_id]");

  makeAutocomplete({
    input: descInput, dropdown: prodDrop,
    fetchFn: async q => {
      const data = await fetch(`${API}/api/productos?q=${encodeURIComponent(q)}&limit=10`).then(r => r.json());
      return data.map(p => ({ label: p.descripcion, id: p.id, unidad: p.unidad }));
    },
    onSelect: item => {
      prodHidden.value = item.id;
      const sel = row.querySelector("[name=unidad]");
      if (item.unidad) sel.value = item.unidad;
    },
    onClear: () => { prodHidden.value = ""; },
  });

  row.querySelector(".btn-remove-item").addEventListener("click", () => {
    row.remove(); refreshEmpty();
  });

  document.getElementById("items-container").appendChild(clone);
  refreshEmpty();
  descInput.focus();
}

// ── Fotos múltiples ───────────────────────────────────────────────────────────
function initFotos() {
  const input   = document.getElementById("foto-input");
  const btnAdd  = document.getElementById("btn-add-foto");
  const preview = document.getElementById("fotos-preview");
  const empty   = document.getElementById("fotos-empty");

  btnAdd.addEventListener("click", () => {
    input.value = "";
    input.click();
  });

  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) return;
    fotoFiles.push(file);

    const url  = URL.createObjectURL(file);
    const idx  = fotoFiles.length - 1;
    const wrap = document.createElement("div");
    wrap.className = "relative";
    wrap.innerHTML = `
      <img src="${url}" class="foto-thumb" />
      <button type="button" data-idx="${idx}"
        class="absolute -top-1 -right-1 bg-red-500 text-white rounded-full w-5 h-5 text-xs flex items-center justify-center btn-rm-foto">
        &times;
      </button>`;
    wrap.querySelector(".btn-rm-foto").addEventListener("click", () => {
      fotoFiles[idx] = null;
      wrap.remove();
      empty.classList.toggle("hidden", fotoFiles.some(f => f));
    });
    preview.appendChild(wrap);
    empty.classList.add("hidden");
  });
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function submit(e) {
  e.preventDefault();
  hideMessages();

  const bodega_id      = +document.getElementById("bodega_id").value;
  const usuario_nombre = document.getElementById("usuario_nombre").value.trim();
  const proveedor_id   = +document.getElementById("proveedor_id").value || null;
  const prov_nombre    = document.getElementById("prov-input").value.trim() || null;
  const prov_nit       = document.getElementById("prov-nit").value.trim() || null;

  if (!bodega_id)      { showErr("Selecciona una bodega."); return; }
  if (!usuario_nombre) { showErr("Escribe tu nombre como almacenista."); return; }
  if (!prov_nombre && !proveedor_id) { showErr("Ingresa un proveedor."); return; }
  if (!proveedor_id && !prov_nit)    { showErr("Ingresa el NIT del proveedor."); return; }

  const rows  = document.querySelectorAll("#items-container .item-row");
  const items = [];
  for (const row of rows) {
    const desc   = row.querySelector("[name=descripcion]").value.trim();
    const cant   = parseFloat(row.querySelector("[name=cantidad]").value) || 0;
    const unidad = row.querySelector("[name=unidad]").value;
    const precio = parseFloat(row.querySelector("[name=precio_unit]").value) || 0;
    const prodId = +row.querySelector("[name=producto_id]").value || null;
    if (!desc) continue;
    items.push({ descripcion: desc, cantidad: cant, unidad, precio_unit: precio,
                 total: cant * precio, producto_id: prodId });
  }

  localStorage.setItem("pa_usuario_nombre", usuario_nombre);

  const payload = {
    numero_factura:   document.getElementById("numero_factura").value.trim() || null,
    fecha_factura:    document.getElementById("fecha_factura").value || null,
    proveedor_id,
    proveedor_nombre: proveedor_id ? null : prov_nombre,
    proveedor_nit:    proveedor_id ? null : prov_nit,
    bodega_id,
    usuario_nombre,
    total_factura: parseFloat(document.getElementById("total_factura").value) || 0,
    observaciones: document.getElementById("observaciones").value.trim() || null,
    items,
  };

  setBusy(true);
  try {
    const res = await fetch(`${API}/api/recepciones/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Error ${res.status}`);
    }
    const recepcion = await res.json();

    // Subir fotos en paralelo
    const fotosValidas = fotoFiles.filter(Boolean);
    if (fotosValidas.length) {
      setBusy(true);
      document.getElementById("btn-text").textContent = `Subiendo ${fotosValidas.length} foto(s)…`;
      await Promise.all(fotosValidas.map(file => {
        const fd = new FormData();
        fd.append("foto", file);
        return fetch(`${API}/api/recepciones/${recepcion.id}/foto`, { method: "POST", body: fd });
      }));
    }

    showOk(`Recepcion #${recepcion.id} guardada.`);
    document.getElementById("form-recepcion").reset();
    document.getElementById("items-container").innerHTML = "";
    document.getElementById("fotos-preview").innerHTML = "";
    document.getElementById("fotos-empty").classList.remove("hidden");
    document.getElementById("proveedor_id").value = "";
    document.getElementById("prov-nit").readOnly = false;
    document.getElementById("prov-nit").classList.remove("bg-gray-50");
    fotoFiles = [];
    refreshEmpty();
    document.getElementById("fecha_factura").valueAsDate = new Date();
    document.getElementById("msg-ok").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    showErr(err.message);
  } finally {
    setBusy(false);
  }
}

function showOk(msg)  { const el = document.getElementById("msg-ok");  el.textContent = msg; el.classList.remove("hidden"); }
function showErr(msg) { const el = document.getElementById("msg-err"); el.textContent = msg; el.classList.remove("hidden"); }
function hideMessages() {
  document.getElementById("msg-ok").classList.add("hidden");
  document.getElementById("msg-err").classList.add("hidden");
}
function setBusy(busy) {
  const btn = document.getElementById("btn-submit");
  btn.disabled = busy;
  document.getElementById("btn-text").textContent = busy ? "Guardando…" : "Registrar Recepcion";
  document.getElementById("btn-spinner").classList.toggle("hidden", !busy);
}

init();
initProveedorAC();
initFotos();
document.getElementById("btn-add-item").addEventListener("click", addItem);
document.getElementById("form-recepcion").addEventListener("submit", submit);
