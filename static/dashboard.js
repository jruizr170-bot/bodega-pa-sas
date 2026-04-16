/* dashboard.js */

// ── PIN de acceso al dashboard ────────────────────────────────────────────────
const DASHBOARD_PIN = "2006";   // ← cambia este PIN cuando quieras

function checkPin() {
  if (sessionStorage.getItem("pa_dashboard_ok") === "1") return true;
  const entered = prompt("PIN de acceso al dashboard:");
  if (entered === DASHBOARD_PIN) {
    sessionStorage.setItem("pa_dashboard_ok", "1");
    return true;
  }
  document.body.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
      min-height:100vh;background:#f3f4f6;font-family:sans-serif;gap:1rem;">
      <p style="font-size:1.1rem;color:#dc2626;font-weight:600;">PIN incorrecto.</p>
      <button onclick="location.reload()"
        style="background:#1e3a8a;color:#fff;padding:.6rem 1.5rem;border-radius:.5rem;border:none;cursor:pointer;font-size:1rem;">
        Reintentar
      </button>
    </div>`;
  return false;
}

if (!checkPin()) throw new Error("PIN requerido");

const API = "";
let allRecepciones = [];
let page = 0;
const PAGE_SIZE = 20;
let filterBodegaId = "";
let filterSearch = "";
let currentDetailId = null;

const BODEGA_COLORS = ["bg-blue-100 text-blue-800", "bg-green-100 text-green-800",
  "bg-yellow-100 text-yellow-800", "bg-purple-100 text-purple-800",
  "bg-orange-100 text-orange-800"];

function fmt(n) {
  return new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP",
    minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n);
}
function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CO", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ── Stats & bodegas ───────────────────────────────────────────────────────────
async function loadStats() {
  const stats = await fetch(`${API}/api/recepciones/dashboard/stats`).then(r => r.json());

  const grid = document.getElementById("stats-grid");
  grid.innerHTML = `
    <div class="bg-white rounded-xl shadow-sm p-4 flex flex-col gap-1">
      <span class="text-xs text-gray-500">Total recepciones</span>
      <span class="text-2xl font-bold text-blue-900">${stats.total_recepciones}</span>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 flex flex-col gap-1">
      <span class="text-xs text-gray-500">Hoy</span>
      <span class="text-2xl font-bold text-green-700">${stats.recepciones_hoy}</span>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 flex flex-col gap-1">
      <span class="text-xs text-gray-500">Esta semana</span>
      <span class="text-2xl font-bold text-indigo-700">${stats.recepciones_semana}</span>
    </div>
    <div class="bg-white rounded-xl shadow-sm p-4 flex flex-col gap-1">
      <span class="text-xs text-gray-500">Total facturado</span>
      <span class="text-xl font-bold text-gray-800">${fmt(stats.total_facturado)}</span>
    </div>
  `;

  // Barras por bodega
  const maxCant = Math.max(...stats.recepciones_por_bodega.map(b => b.cantidad), 1);
  const bars = document.getElementById("bodega-bars");
  bars.innerHTML = stats.recepciones_por_bodega.map((b, i) => `
    <div class="flex items-center gap-2">
      <span class="text-xs text-gray-600 w-28 shrink-0 truncate">${b.bodega}</span>
      <div class="flex-1 bg-gray-100 rounded-full h-3">
        <div class="h-3 rounded-full bg-blue-600 transition-all"
          style="width:${(b.cantidad / maxCant * 100).toFixed(1)}%"></div>
      </div>
      <span class="text-xs font-semibold text-gray-700 w-6 text-right">${b.cantidad}</span>
    </div>
  `).join("");
}

// ── Cargar bodegas en filtro ───────────────────────────────────────────────────
async function loadBodegaFilter() {
  const bodegas = await fetch(`${API}/api/bodegas`).then(r => r.json());
  const sel = document.getElementById("filter-bodega");
  bodegas.forEach(b => {
    const opt = document.createElement("option");
    opt.value = b.id;
    opt.textContent = `${b.codigo} – ${b.nombre}`;
    sel.appendChild(opt);
  });
}

// ── Lista de recepciones ──────────────────────────────────────────────────────
async function loadRecepciones(reset = false) {
  if (reset) { page = 0; allRecepciones = []; }
  const params = new URLSearchParams({ skip: page * PAGE_SIZE, limit: PAGE_SIZE });
  if (filterBodegaId) params.set("bodega_id", filterBodegaId);
  const data = await fetch(`${API}/api/recepciones/?${params}`).then(r => r.json());

  if (reset) allRecepciones = data;
  else allRecepciones = [...allRecepciones, ...data];
  page++;

  renderList();
  document.getElementById("btn-load-more").classList.toggle("hidden", data.length < PAGE_SIZE);
}

function filtered() {
  const q = filterSearch.toLowerCase();
  if (!q) return allRecepciones;
  return allRecepciones.filter(r =>
    (r.numero_factura || "").toLowerCase().includes(q) ||
    (r.proveedor?.nombre || r.proveedor_nombre || "").toLowerCase().includes(q)
  );
}

function renderList() {
  const list = document.getElementById("recepciones-list");
  const recs = filtered();
  if (!recs.length) {
    list.innerHTML = `<p class="text-sm text-gray-400 italic text-center py-4">Sin recepciones.</p>`;
    return;
  }
  list.innerHTML = recs.map((r, i) => {
    const provNombre = r.proveedor?.nombre || r.proveedor_nombre || "Sin proveedor";
    const colorClass = BODEGA_COLORS[i % BODEGA_COLORS.length];
    const bodegaNombre = r.bodega?.nombre || "—";
    return `
    <div class="bg-white rounded-xl shadow-sm p-4 cursor-pointer active:bg-gray-50 border border-transparent hover:border-blue-200 transition"
      data-id="${r.id}" onclick="openDetail(${r.id})">
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-semibold text-gray-800 text-sm">${r.numero_factura || `#${r.id}`}</span>
            <span class="badge-bodega ${colorClass}">${bodegaNombre}</span>
          </div>
          <p class="text-xs text-gray-500 truncate">${provNombre}</p>
          <p class="text-xs text-gray-400">${fmtDate(r.fecha_registro)}</p>
        </div>
        <div class="text-right shrink-0">
          <span class="text-sm font-bold text-green-700">${fmt(r.total_factura)}</span>
          <p class="text-xs text-gray-400">${r.items?.length || 0} ítems</p>
        </div>
      </div>
    </div>`;
  }).join("");
}

// ── Modal detalle ─────────────────────────────────────────────────────────────
async function openDetail(id) {
  currentDetailId = id;
  const modal = document.getElementById("modal");
  modal.classList.remove("hidden");
  document.getElementById("modal-body").innerHTML = `<div class="flex justify-center py-6">
    <div style="border:3px solid #e5e7eb;border-top-color:#1e3a8a;border-radius:50%;
      width:1.5rem;height:1.5rem;animation:spin .6s linear infinite"></div>
  </div>`;

  const r = await fetch(`${API}/api/recepciones/${id}`).then(res => res.json());
  const provNombre = r.proveedor?.nombre || r.proveedor_nombre || "—";
  const provNit    = r.proveedor?.nit || "—";

  document.getElementById("modal-title").textContent = `Recepción #${r.id}`;
  document.getElementById("modal-body").innerHTML = `
    <div class="space-y-3 text-sm">
      ${r.foto_path ? `<img src="/${r.foto_path}" class="w-full rounded-lg max-h-48 object-cover"/>` : ""}
      <div class="grid grid-cols-2 gap-x-4 gap-y-2">
        <div><p class="text-xs text-gray-400">Factura</p><p class="font-medium">${r.numero_factura || "—"}</p></div>
        <div><p class="text-xs text-gray-400">Fecha factura</p><p class="font-medium">${r.fecha_factura || "—"}</p></div>
        <div><p class="text-xs text-gray-400">Proveedor</p><p class="font-medium">${provNombre}</p></div>
        <div><p class="text-xs text-gray-400">NIT</p><p class="font-medium">${provNit}</p></div>
        <div><p class="text-xs text-gray-400">Bodega</p><p class="font-medium">${r.bodega?.nombre || "—"}</p></div>
        <div><p class="text-xs text-gray-400">Almacenista</p><p class="font-medium">${r.usuario?.nombre || "—"}</p></div>
        <div><p class="text-xs text-gray-400">Registrado</p><p class="font-medium">${fmtDate(r.fecha_registro)}</p></div>
        <div><p class="text-xs text-gray-400">Total</p><p class="font-bold text-green-700">${fmt(r.total_factura)}</p></div>
      </div>
      ${r.observaciones ? `<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
        <p class="text-xs text-yellow-700 font-medium mb-1">Observaciones</p>
        <p class="text-xs text-yellow-900">${r.observaciones}</p>
      </div>` : ""}
      ${r.items?.length ? `
        <div>
          <p class="text-xs text-gray-400 font-medium mb-2">Artículos (${r.items.length})</p>
          <div class="space-y-1">
            ${r.items.map(it => `
              <div class="flex justify-between text-xs bg-gray-50 rounded p-2">
                <span class="flex-1 text-gray-700">${it.descripcion} <span class="text-gray-400">${it.cantidad} ${it.unidad}</span></span>
                <span class="font-medium text-gray-800 ml-2">${fmt(it.total)}</span>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

document.getElementById("modal-close").addEventListener("click", () => {
  document.getElementById("modal").classList.add("hidden");
});
document.getElementById("modal").addEventListener("click", e => {
  if (e.target === document.getElementById("modal")) {
    document.getElementById("modal").classList.add("hidden");
  }
});

document.getElementById("modal-delete").addEventListener("click", async () => {
  if (!currentDetailId) return;
  if (!confirm("¿Eliminar esta recepción? Esta acción no se puede deshacer.")) return;
  const res = await fetch(`${API}/api/recepciones/${currentDetailId}`, { method: "DELETE" });
  if (res.ok || res.status === 204) {
    document.getElementById("modal").classList.add("hidden");
    await loadRecepciones(true);
    await loadStats();
  }
});

// ── Filtros ───────────────────────────────────────────────────────────────────
document.getElementById("filter-bodega").addEventListener("change", e => {
  filterBodegaId = e.target.value;
  loadRecepciones(true);
});

let searchTimer;
document.getElementById("filter-search").addEventListener("input", e => {
  filterSearch = e.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => renderList(), 200);
});

document.getElementById("btn-load-more").addEventListener("click", () => loadRecepciones(false));

// ── Boot ──────────────────────────────────────────────────────────────────────
Promise.all([loadStats(), loadBodegaFilter(), loadRecepciones(true)]);
