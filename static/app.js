/* App Bodega PA SAS v2 — Llegadas (bodega) + Armado y Despachos (operaciones) */
const $ = (id) => document.getElementById(id);
const API = "/api";

let CATALOGO = { programas: [], tipos_aipi: [], municipios: {} };
let OCS = [];
let OC_ACTUAL = null;
let DESTINOS = [];

/* ── mensajes ── */
function ok(msg)  { const e = $("msg-ok");  e.textContent = msg; e.classList.remove("hidden");
                    $("msg-err").classList.add("hidden"); setTimeout(() => e.classList.add("hidden"), 5000); window.scrollTo(0,0); }
function err(msg) { const e = $("msg-err"); e.textContent = msg; e.classList.remove("hidden");
                    $("msg-ok").classList.add("hidden"); window.scrollTo(0,0); }

async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: opts.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    let d = ""; try { d = (await r.json()).detail || ""; } catch {}
    throw new Error(d || `Error ${r.status}`);
  }
  return r.json();
}

/* ── navegación ── */
const VISTAS = ["menu", "llegada", "armado", "despacho", "entregas"];
function mostrar(vista) {
  VISTAS.forEach(v => $("vista-" + v).classList.toggle("hidden", v !== vista));
  $("btn-home").classList.toggle("hidden", vista === "menu");
  if (vista === "llegada")  cargarOCs();
  if (vista === "armado")   cargarHistorialArmados();
  if (vista === "entregas") cargarPendientes();
}
document.querySelectorAll(".nav").forEach(b =>
  b.addEventListener("click", () => mostrar(b.dataset.vista)));
$("btn-home").addEventListener("click", () => mostrar("menu"));

function usuarioId() {
  const v = $("usuario").value;
  return v ? parseInt(v) : null;
}

/* ── init ── */
async function init() {
  try {
    const usuarios = await api("/usuarios");
    $("usuario").innerHTML = usuarios.map(u => `<option value="${u.id}">${u.nombre}</option>`).join("");
  } catch (e) { err("No se pudieron cargar usuarios: " + e.message); }
  try {
    CATALOGO = await api("/operaciones/catalogo");
    const progOpts = CATALOGO.programas.map(p => `<option>${p}</option>`).join("");
    $("arm-programa").innerHTML = progOpts;
    $("dest-programa").innerHTML = progOpts;
    $("arm-tipo").innerHTML = CATALOGO.tipos_aipi.map(t => `<option>${t}</option>`).join("");
    $("dest-tipo").innerHTML = $("arm-tipo").innerHTML;
    actualizarMunicipios();
  } catch (e) { err("No se pudo cargar el catálogo: " + e.message); }
}

/* ════ LLEGADAS ════ */
async function cargarOCs() {
  $("detalle-oc").classList.add("hidden");
  const cont = $("lista-ocs");
  cont.innerHTML = '<div class="spinner mx-auto"></div>';
  try {
    OCS = await api("/llegadas/ocs-abiertas");
    if (!OCS.length) { cont.innerHTML = '<p class="text-sm text-gray-500">No hay OCs abiertas.</p>'; return; }
    cont.innerHTML = OCS.map((oc, i) => `
      <button data-i="${i}" class="oc-btn w-full bg-white rounded-xl shadow-sm p-3 text-left flex justify-between items-center">
        <span>
          <b class="text-blue-900">OC ${oc.orden_numero}</b>
          <span class="block text-sm text-gray-600">${oc.proveedor_nombre || oc.proveedor_nit || ""}</span>
          <span class="block text-xs text-gray-400">${oc.items.length} producto(s) · entrega ${oc.fecha_entrega || "?"}</span>
        </span>
        ${oc.dias_atraso > 0 ? `<span class="text-xs bg-red-100 text-red-700 rounded-full px-2 py-1">${oc.dias_atraso}d atraso</span>` : ""}
      </button>`).join("");
    cont.querySelectorAll(".oc-btn").forEach(b =>
      b.addEventListener("click", () => abrirOC(parseInt(b.dataset.i))));
  } catch (e) { cont.innerHTML = ""; err(e.message); }
}

function abrirOC(i) {
  OC_ACTUAL = OCS[i];
  $("oc-encabezado").innerHTML =
    `<b>OC ${OC_ACTUAL.orden_numero}</b> — ${OC_ACTUAL.proveedor_nombre || ""}<br>
     <span class="text-xs text-gray-500">Ajusta las cantidades a lo que llegó realmente:</span>`;
  $("oc-items").innerHTML = OC_ACTUAL.items.map((it, j) => `
    <div class="bg-white rounded-xl shadow-sm p-3">
      <div class="text-sm font-medium">${it.articulo_nombre}</div>
      <div class="flex items-center gap-2 mt-1">
        <span class="text-xs text-gray-400">Esperado: ${Number(it.faltante).toLocaleString()}</span>
        <input data-j="${j}" type="number" min="0" inputmode="decimal" value="${it.faltante}"
          class="cant-recibida flex-1 border border-gray-300 rounded-lg px-2 py-2 text-right text-base font-semibold" />
      </div>
    </div>`).join("");
  $("lleg-obs").value = "";
  $("lleg-foto").value = "";
  $("detalle-oc").classList.remove("hidden");
  $("detalle-oc").scrollIntoView({ behavior: "smooth" });
}

$("btn-guardar-llegada").addEventListener("click", async () => {
  if (!OC_ACTUAL) return;
  const items = OC_ACTUAL.items.map((it, j) => ({
    articulo_codigo: it.articulo_codigo,
    articulo_nombre: it.articulo_nombre,
    cantidad_esperada: it.faltante,
    cantidad_recibida: parseFloat(document.querySelector(`.cant-recibida[data-j="${j}"]`).value || 0),
  }));
  try {
    const lleg = await api("/llegadas/", { method: "POST", body: JSON.stringify({
      oc_numero: OC_ACTUAL.orden_numero, usuario_id: usuarioId(),
      observaciones: $("lleg-obs").value || null, items }) });
    const f = $("lleg-foto").files[0];
    if (f) {
      const fd = new FormData(); fd.append("foto", f);
      await api(`/llegadas/${lleg.id}/foto`, { method: "POST", body: fd });
    }
    ok(`Llegada de la OC ${lleg.oc_numero} registrada ✔`);
    mostrar("menu");
  } catch (e) { err(e.message); }
});

/* ════ ARMADO ════ */
$("arm-programa").addEventListener("change", () =>
  $("arm-tipo-wrap").classList.toggle("hidden", $("arm-programa").value !== "AIPI"));

async function cargarHistorialArmados() {
  $("arm-tipo-wrap").classList.toggle("hidden", $("arm-programa").value !== "AIPI");
  try {
    const arms = await api("/operaciones/armados?limit=5");
    $("arm-historial").innerHTML = arms.length
      ? "<b>Últimos armados:</b><br>" + arms.map(a =>
          `• ${(a.fecha || "").slice(0, 10)} — ${a.programa}${a.tipo_paquete ? " / " + a.tipo_paquete : ""}: <b>${a.paquetes}</b> paq (${a.usuario || "?"})`).join("<br>")
      : "";
  } catch {}
}

$("btn-guardar-armado").addEventListener("click", async () => {
  const paquetes = parseInt($("arm-paquetes").value || 0);
  if (!paquetes) return err("Indica cuántos paquetes se armaron.");
  try {
    await api("/operaciones/armados", { method: "POST", body: JSON.stringify({
      programa: $("arm-programa").value,
      tipo_paquete: $("arm-programa").value === "AIPI" ? $("arm-tipo").value : null,
      paquetes, usuario_id: usuarioId(),
      observaciones: $("arm-obs").value || null }) });
    ok(`Armado registrado: ${paquetes} paquetes ✔`);
    $("arm-paquetes").value = ""; $("arm-obs").value = "";
    cargarHistorialArmados();
  } catch (e) { err(e.message); }
});

/* ════ DESPACHO ════ */
function actualizarMunicipios() {
  const prog = $("dest-programa").value || CATALOGO.programas[0];
  const muns = CATALOGO.municipios[prog] || [];
  $("dest-municipio").innerHTML = muns.map(m => `<option>${m}</option>`).join("");
  $("dest-tipo").classList.toggle("hidden", prog !== "AIPI");
}
$("dest-programa").addEventListener("change", actualizarMunicipios);

function pintarDestinos() {
  $("destinos-lista").innerHTML = DESTINOS.map((d, i) => `
    <div class="flex justify-between items-center bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm">
      <span><b>${d.municipio}</b> · ${d.programa}${d.tipo_paquete ? " / " + d.tipo_paquete : ""}
        — ${d.paquetes} paq${d.complementos ? " + " + d.complementos + " compl" : ""}</span>
      <button data-i="${i}" class="del-dest text-red-600 font-bold px-2">✕</button>
    </div>`).join("");
  document.querySelectorAll(".del-dest").forEach(b =>
    b.addEventListener("click", () => { DESTINOS.splice(parseInt(b.dataset.i), 1); pintarDestinos(); }));
}

$("btn-agregar-destino").addEventListener("click", () => {
  const paquetes = parseInt($("dest-paquetes").value || 0);
  if (!paquetes) return err("Indica los paquetes para el destino.");
  const prog = $("dest-programa").value;
  DESTINOS.push({
    municipio: $("dest-municipio").value, programa: prog,
    tipo_paquete: prog === "AIPI" ? $("dest-tipo").value : null,
    paquetes, complementos: parseInt($("dest-complementos").value || 0),
  });
  $("dest-paquetes").value = ""; $("dest-complementos").value = "";
  pintarDestinos();
});

$("btn-guardar-despacho").addEventListener("click", async () => {
  if (!$("desp-placa").value.trim()) return err("Indica la placa del carro.");
  if (!DESTINOS.length) return err("Agrega al menos un destino.");
  try {
    const d = await api("/operaciones/despachos", { method: "POST", body: JSON.stringify({
      vehiculo_placa: $("desp-placa").value, vehiculo_tipo: $("desp-tipo-veh").value || null,
      conductor: $("desp-conductor").value || null, operario: $("desp-operario").value || null,
      hora_salida: $("desp-hora").value || null, usuario_id: usuarioId(),
      observaciones: $("desp-obs").value || null, destinos: DESTINOS }) });
    const f = $("desp-foto").files[0];
    if (f) {
      const fd = new FormData(); fd.append("foto", f);
      await api(`/operaciones/despachos/${d.id}/foto`, { method: "POST", body: fd });
    }
    ok(`Despacho ${d.vehiculo_placa} registrado con ${d.destinos.length} destino(s) ✔`);
    DESTINOS = []; pintarDestinos();
    ["desp-placa","desp-conductor","desp-operario","desp-hora","desp-obs"].forEach(id => $(id).value = "");
    $("desp-foto").value = "";
    mostrar("menu");
  } catch (e) { err(e.message); }
});

/* ════ ENTREGAS ════ */
async function cargarPendientes() {
  const cont = $("lista-pendientes");
  cont.innerHTML = '<div class="spinner mx-auto"></div>';
  try {
    const desps = await api("/operaciones/despachos?pendientes=true");
    if (!desps.length) { cont.innerHTML = '<p class="text-sm text-gray-500">No hay entregas pendientes 🎉</p>'; return; }
    cont.innerHTML = desps.map(d => `
      <div class="bg-white rounded-xl shadow-sm p-3">
        <div class="text-sm font-bold text-blue-900">🚚 ${d.vehiculo_placa} · ${(d.fecha || "").slice(0, 10)}
          <span class="font-normal text-gray-500">salió ${d.hora_salida || "?"} — ${d.conductor || ""}</span></div>
        <div class="mt-2 space-y-2">
          ${d.destinos.map(x => x.entregado
            ? `<div class="text-sm text-green-700">✔ ${x.municipio} (${x.paquetes} paq) — ${x.hora_entrega} ${x.recibido_por ? "· recibió " + x.recibido_por : ""}</div>`
            : `<div class="border border-gray-200 rounded-lg p-2">
                <div class="text-sm font-medium">${x.municipio} · ${x.programa} — ${x.paquetes} paq</div>
                <div class="grid grid-cols-2 gap-2 mt-1">
                  <input id="he-${x.id}" type="time" class="border border-gray-300 rounded px-2 py-1 text-sm" />
                  <input id="rp-${x.id}" type="text" placeholder="¿Quién recibió?" class="border border-gray-300 rounded px-2 py-1 text-sm" />
                  <input id="nv-${x.id}" type="text" placeholder="Novedades (opcional)" class="col-span-2 border border-gray-300 rounded px-2 py-1 text-sm" />
                  <button data-d="${d.id}" data-x="${x.id}" class="conf-btn col-span-2 bg-green-600 text-white rounded-lg py-2 text-sm font-bold">Confirmar entrega</button>
                </div>
              </div>`).join("")}
        </div>
      </div>`).join("");
    cont.querySelectorAll(".conf-btn").forEach(b => b.addEventListener("click", async () => {
      const x = b.dataset.x;
      try {
        await api(`/operaciones/despachos/${b.dataset.d}/destinos/${x}`, {
          method: "PATCH", body: JSON.stringify({
            hora_entrega: $(`he-${x}`).value || new Date().toTimeString().slice(0, 5),
            recibido_por: $(`rp-${x}`).value || null,
            novedades: $(`nv-${x}`).value || null }) });
        ok("Entrega confirmada ✔");
        cargarPendientes();
      } catch (e) { err(e.message); }
    }));
  } catch (e) { cont.innerHTML = ""; err(e.message); }
}

init();
