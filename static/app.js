/* App Bodega PA SAS v2.1 */
const $ = (id) => document.getElementById(id);
const API = "/api";

let CATALOGO = { programas: [], tipos_aipi: [], municipios: {} };
let OCS = [];
let OC_ACTUAL = null;
let DESTINOS = [];
let URG_PROV = null;
let URG_ITEMS = [];
let USUARIO = null;

const COLORES_AIPI = {
  gestantes_lactantes: { label: "🟡 AMARILLO — Gestantes y lactantes", bg: "#fef9c3", txt: "#854d0e" },
  ninos_6m_1ano:       { label: "🔵 AZUL — Niños 6 meses a 1 año",     bg: "#dbeafe", txt: "#1e40af" },
  mayores_1_ano:       { label: "🟢 VERDE — Mayores de 1 año",         bg: "#dcfce7", txt: "#166534" },
  complemento_gestantes: { label: "Complemento gestantes (malteada+sachets)", bg: "#f3f4f6", txt: "#374151" },
  complemento_ninos:     { label: "Complemento niños (malteada)",            bg: "#f3f4f6", txt: "#374151" },
};
const etiquetaTipo = (t) => (COLORES_AIPI[t] || { label: t }).label;

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

/* ── unidades: el bodeguero digita como diga la FACTURA (g/kg/ml/L/und);
      al guardar se convierte a la unidad base de la OC (g, ml o unidades) ── */
const UNIDADES = ["g", "kg", "ml", "L", "und"];
const FACTOR_UNIDAD = { g: 1, kg: 1000, ml: 1, L: 1000, und: 1 };
function fmtCant(v, unidad) {
  v = Number(v) || 0;
  if (unidad === "kg") return (v / 1000).toLocaleString("es-CO", { maximumFractionDigits: 1 }) + " kg";
  if (unidad === "L") return (v / 1000).toLocaleString("es-CO", { maximumFractionDigits: 1 }) + " L";
  if (unidad === "und") return v.toLocaleString("es-CO") + " und";
  return v.toLocaleString("es-CO") + " " + unidad;
}
function unidadInicial(esperado) { return esperado >= 1000 ? "kg" : "und"; }
function aValorBase(valor, unidad) { return valor * (FACTOR_UNIDAD[unidad] || 1); }
function deValorBase(valor, unidad) { return valor / (FACTOR_UNIDAD[unidad] || 1); }
const pesosFmt = (v) => "$" + Number(v || 0).toLocaleString("es-CO", { maximumFractionDigits: 0 });

/* ── navegación ── */
const VISTAS = ["usuario", "menu", "llegada", "armado", "despacho", "entregas"];
function mostrar(vista) {
  VISTAS.forEach(v => $("vista-" + v).classList.toggle("hidden", v !== vista));
  $("btn-home").classList.toggle("hidden", vista === "menu" || vista === "usuario");
  if (vista === "llegada")  { $("form-urgencia").classList.add("hidden"); cargarOCs(); }
  if (vista === "armado")   { pintarAvance(); cargarHistorialArmados(); }
  if (vista === "entregas") cargarPendientes();
}
document.querySelectorAll(".nav").forEach(b =>
  b.addEventListener("click", () => mostrar(b.dataset.vista)));
$("btn-home").addEventListener("click", () => mostrar("menu"));
$("chip-usuario").addEventListener("click", () => { localStorage.removeItem("usuario"); pedirUsuario(); });

/* ── usuario fijo + recordar ── */
async function pedirUsuario() {
  mostrar("usuario");
  const usuarios = await api("/usuarios");
  $("lista-usuarios").innerHTML = usuarios.map(u => `
    <button data-id="${u.id}" data-nombre="${u.nombre}"
      class="card-btn usr w-full bg-white rounded-2xl shadow p-4 text-left text-lg font-bold">👷 ${u.nombre}</button>`).join("");
  document.querySelectorAll(".usr").forEach(b => b.addEventListener("click", () => {
    USUARIO = { id: parseInt(b.dataset.id), nombre: b.dataset.nombre };
    localStorage.setItem("usuario", JSON.stringify(USUARIO));
    pintarUsuario();
    mostrar("menu");
  }));
}
function pintarUsuario() {
  $("chip-usuario").textContent = USUARIO ? `👷 ${USUARIO.nombre.split(" ")[0]} · cambiar` : "elegir usuario";
}

/* ── init ── */
async function init() {
  try {
    CATALOGO = await api("/operaciones/catalogo");
    pintarSelectorPrograma("arm-programa", onProgramaArmado);
    pintarSelectorPrograma("dest-programa", onProgramaDestino);
    pintarTipos("arm-tipo");
    pintarTipos("dest-tipo");
    onProgramaDestino();
  } catch (e) { err("No se pudo cargar el catálogo: " + e.message); }
  const guardado = localStorage.getItem("usuario");
  if (guardado) { USUARIO = JSON.parse(guardado); pintarUsuario(); mostrar("menu"); }
  else pedirUsuario();
}

function pintarSelectorPrograma(contId, onChange) {
  const cont = $(contId);
  cont.innerHTML = CATALOGO.programas.map((p, i) => `
    <button type="button" data-p="${p}" class="tipo-btn prog-${contId} ${i === 0 ? "sel" : ""}"
      style="background:#f3f4f6">${p}</button>`).join("");
  cont.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    cont.querySelectorAll("button").forEach(x => x.classList.remove("sel"));
    b.classList.add("sel");
    onChange();
  }));
}
const programaSel = (contId) => $(contId).querySelector(".sel")?.dataset.p || CATALOGO.programas[0];

function pintarTipos(contId) {
  const cont = $(contId);
  cont.innerHTML = CATALOGO.tipos_aipi.map((t, i) => {
    const c = COLORES_AIPI[t] || { bg: "#f3f4f6", txt: "#374151", label: t };
    return `<button type="button" data-t="${t}" class="tipo-btn ${i === 0 ? "sel" : ""}"
      style="background:${c.bg};color:${c.txt}">${c.label}</button>`;
  }).join("");
  cont.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    cont.querySelectorAll("button").forEach(x => x.classList.remove("sel"));
    b.classList.add("sel");
  }));
}
const tipoSel = (contId) => $(contId).querySelector(".sel")?.dataset.t || null;

/* ════ LLEGADAS ════ */
async function cargarOCs() {
  $("detalle-oc").classList.add("hidden");
  const cont = $("lista-ocs");
  cont.innerHTML = '<div class="spinner mx-auto"></div>';
  try {
    OCS = await api("/llegadas/ocs-abiertas");
    pintarOCs();
  } catch (e) { cont.innerHTML = ""; err(e.message); }
}

function pintarOCs() {
  const q = ($("buscador-oc").value || "").trim().toLowerCase();
  const lista = q ? OCS.filter(oc =>
    (oc.proveedor_nombre || "").toLowerCase().includes(q) ||
    (oc.proveedor_nit || "").includes(q) ||
    String(oc.orden_numero).includes(q)) : OCS;
  const cont = $("lista-ocs");
  if (!lista.length) { cont.innerHTML = '<p class="text-sm text-gray-500 text-center py-4">Sin resultados. ¿Es una urgencia sin OC? Usa el botón naranja.</p>'; return; }
  cont.innerHTML = lista.map(oc => `
    <button data-n="${oc.orden_numero}" class="oc-btn w-full bg-white rounded-xl shadow-sm p-3 text-left flex justify-between items-center">
      <span>
        <b>${oc.proveedor_nombre || oc.proveedor_nit || "?"}</b>
        <span class="block text-xs text-gray-400">OC ${oc.orden_numero} · ${oc.items.length} producto(s) · entrega ${oc.fecha_entrega || "?"}</span>
      </span>
      ${oc.dias_atraso > 0 ? `<span class="text-xs bg-red-100 text-red-700 rounded-full px-2 py-1 ml-2 shrink-0">${oc.dias_atraso}d atraso</span>` : ""}
    </button>`).join("");
  cont.querySelectorAll(".oc-btn").forEach(b =>
    b.addEventListener("click", () => abrirOC(b.dataset.n)));
}
$("buscador-oc").addEventListener("input", pintarOCs);

function filaItem(idx, nombre, esperado) {
  const uni = unidadInicial(esperado);
  const mostrado = deValorBase(esperado, uni);
  return `
    <div class="bg-white rounded-xl shadow-sm p-3 item-fila" data-idx="${idx}" data-esperado="${esperado}">
      <div class="text-sm font-bold">${nombre}</div>
      <div class="text-xs text-gray-500 mb-2">Esperado: <b>${fmtCant(esperado, uni)}</b> · digita como diga la factura</div>
      <div class="flex items-center gap-2">
        <input type="number" min="0" step="any" inputmode="decimal" value="${mostrado}"
          class="cant flex-1 border-2 border-gray-300 rounded-lg px-2 py-2.5 text-right text-lg font-bold" />
        <div class="flex gap-0.5">
          ${UNIDADES.map(u => `<button type="button" data-u="${u}" class="chip uni ${uni === u ? "activo" : ""}">${u}</button>`).join("")}
        </div>
      </div>
      <div class="flex items-center gap-2 mt-2">
        <span class="text-lg">💲</span>
        <input type="number" min="0" step="any" inputmode="decimal" placeholder="Valor TOTAL según factura"
          class="precio flex-1 border-2 border-amber-300 rounded-lg px-2 py-2 text-right font-bold" />
      </div>
      <button type="button" class="completo mt-2 w-full border border-green-400 text-green-700 bg-green-50 rounded-lg py-1.5 text-sm font-bold">✓ Llegó completo</button>
    </div>`;
}

function activarFilas(contId) {
  $(contId).querySelectorAll(".item-fila").forEach(fila => {
    const esperado = parseFloat(fila.dataset.esperado || 0);
    fila.querySelectorAll(".uni").forEach(b => b.addEventListener("click", () => {
      const previa = fila.querySelector(".uni.activo")?.dataset.u || "g";
      const input = fila.querySelector(".cant");
      const base = aValorBase(parseFloat(input.value || 0), previa);
      fila.querySelectorAll(".uni").forEach(x => x.classList.remove("activo"));
      b.classList.add("activo");
      input.value = deValorBase(base, b.dataset.u) || "";
    }));
    fila.querySelector(".completo").addEventListener("click", () => {
      const uni = fila.querySelector(".uni.activo")?.dataset.u || "g";
      fila.querySelector(".cant").value = deValorBase(esperado, uni);
    });
  });
}

function leerItems(contId, base) {
  return Array.from($(contId).querySelectorAll(".item-fila")).map((fila, i) => {
    const uni = fila.querySelector(".uni.activo")?.dataset.u || "g";
    const valor = parseFloat(fila.querySelector(".cant").value || 0);
    const it = base[parseInt(fila.dataset.idx)];
    return {
      articulo_codigo: it.articulo_codigo,
      articulo_nombre: it.articulo_nombre,
      cantidad_esperada: parseFloat(fila.dataset.esperado || 0),
      cantidad_recibida: aValorBase(valor, uni),
      unidad_reportada: uni === "und" ? "unidades" : uni,
      precio_total: parseFloat(fila.querySelector(".precio").value || 0),
    };
  });
}

function avisosSospecha(items) {
  const avisos = [];
  for (const it of items) {
    if (it.cantidad_esperada > 0 && it.cantidad_recibida > it.cantidad_esperada * 1.5)
      avisos.push(`${it.articulo_nombre}: pusiste ${it.cantidad_recibida.toLocaleString()} y se esperaban ${it.cantidad_esperada.toLocaleString()}`);
    if (it.unidad_reportada === "unidades" && it.cantidad_recibida > 100000)
      avisos.push(`${it.articulo_nombre}: ${it.cantidad_recibida.toLocaleString()} unidades parece un gramaje`);
  }
  return avisos;
}

function abrirOC(numero) {
  OC_ACTUAL = OCS.find(o => String(o.orden_numero) === String(numero));
  if (!OC_ACTUAL) return;
  $("form-urgencia").classList.add("hidden");
  $("oc-encabezado").innerHTML =
    `<b>OC ${OC_ACTUAL.orden_numero}</b> — ${OC_ACTUAL.proveedor_nombre || ""}<br>
     <span class="text-xs text-gray-500">Ajusta a lo que llegó realmente. Si todo llegó, usa "✓ Llegó completo".</span>`;
  $("oc-items").innerHTML = OC_ACTUAL.items.map((it, j) =>
    filaItem(j, it.articulo_nombre, it.faltante)).join("");
  activarFilas("oc-items");
  $("lleg-obs").value = ""; $("lleg-foto").value = "";
  $("btn-guardar-llegada").disabled = true;
  $("detalle-oc").classList.remove("hidden");
  $("detalle-oc").scrollIntoView({ behavior: "smooth" });
}
$("lleg-foto").addEventListener("change", () =>
  $("btn-guardar-llegada").disabled = !$("lleg-foto").files.length);

$("btn-guardar-llegada").addEventListener("click", async () => {
  if (!OC_ACTUAL) return;
  if (!$("lleg-foto").files.length) return err("La foto de la factura es obligatoria.");
  const items = leerItems("oc-items", OC_ACTUAL.items);
  if (items.some(i => i.cantidad_recibida > 0 && !(i.precio_total > 0)))
    return err("💲 Pon el valor según factura de cada producto que llegó.");
  const avisos = avisosSospecha(items);
  if (avisos.length && !confirm("⚠️ REVISA:\n\n" + avisos.join("\n") + "\n\n¿Seguro que está bien?")) return;
  const fd = new FormData();
  fd.append("datos", JSON.stringify({
    oc_numero: OC_ACTUAL.orden_numero, usuario_id: USUARIO?.id,
    observaciones: $("lleg-obs").value || null, items }));
  for (const f of $("lleg-foto").files) fd.append("fotos", f);
  try {
    const l = await api("/llegadas/", { method: "POST", body: fd });
    ok(`Llegada de la OC ${l.oc_numero} registrada ✔${l.sospechosa ? " (quedó marcada para revisión)" : ""}`);
    mostrar("menu");
  } catch (e) { err(e.message); }
});

/* ── urgencia sin OC ── */
$("btn-urgencia").addEventListener("click", () => {
  $("detalle-oc").classList.add("hidden");
  URG_PROV = null; URG_ITEMS = [];
  $("urg-prov").value = ""; $("urg-prov-sel").classList.add("hidden");
  $("urg-items").innerHTML = ""; $("urg-obs").value = ""; $("urg-foto").value = "";
  $("btn-guardar-urgencia").disabled = true;
  $("form-urgencia").classList.remove("hidden");
  $("form-urgencia").scrollIntoView({ behavior: "smooth" });
});

function autocomplete(inputId, dropId, buscarUrl, onPick, render) {
  let timer = null;
  $(inputId).addEventListener("input", () => {
    clearTimeout(timer);
    const q = $(inputId).value.trim();
    if (q.length < 2) { $(dropId).classList.add("hidden"); return; }
    timer = setTimeout(async () => {
      try {
        const res = await api(`${buscarUrl}?q=${encodeURIComponent(q)}`);
        $(dropId).innerHTML = res.map((r, i) => `<div class="ac-item" data-i="${i}">${render(r)}</div>`).join("")
          || '<div class="ac-item text-gray-400">Sin resultados</div>';
        $(dropId).classList.remove("hidden");
        $(dropId).querySelectorAll(".ac-item[data-i]").forEach(el =>
          el.addEventListener("click", () => { $(dropId).classList.add("hidden"); onPick(res[parseInt(el.dataset.i)]); }));
      } catch {}
    }, 250);
  });
}

autocomplete("urg-prov", "urg-prov-drop", "/llegadas/buscar-proveedores",
  (p) => { URG_PROV = p; $("urg-prov").value = "";
           $("urg-prov-sel").textContent = `✔ ${p.nombre} (NIT ${p.nit})`;
           $("urg-prov-sel").classList.remove("hidden"); revisarUrgencia(); },
  (p) => `<b>${p.nombre}</b><br><span class="text-xs text-gray-400">NIT ${p.nit}</span>`);

autocomplete("urg-art", "urg-art-drop", "/llegadas/buscar-articulos",
  (a) => { URG_ITEMS.push({ articulo_codigo: a.codigo, articulo_nombre: a.nombre, faltante: 0 });
           $("urg-art").value = ""; pintarUrgItems(); },
  (a) => `<b>${a.nombre}</b><br><span class="text-xs text-gray-400">${a.codigo}${a.presentacion ? " · " + a.presentacion : ""}</span>`);

function pintarUrgItems() {
  $("urg-items").innerHTML = URG_ITEMS.map((it, j) => `
    <div class="relative">
      ${filaItem(j, it.articulo_nombre, 0)}
      <button type="button" data-j="${j}" class="quitar-urg absolute top-2 right-2 text-red-600 font-bold px-2">✕</button>
    </div>`).join("");
  activarFilas("urg-items");
  document.querySelectorAll(".quitar-urg").forEach(b =>
    b.addEventListener("click", () => { URG_ITEMS.splice(parseInt(b.dataset.j), 1); pintarUrgItems(); }));
  revisarUrgencia();
}
function revisarUrgencia() {
  $("btn-guardar-urgencia").disabled =
    !(URG_PROV && URG_ITEMS.length && $("urg-foto").files.length);
}
$("urg-foto").addEventListener("change", revisarUrgencia);

$("btn-guardar-urgencia").addEventListener("click", async () => {
  const items = leerItems("urg-items", URG_ITEMS);
  if (items.some(i => !i.cantidad_recibida)) return err("Pon la cantidad de cada producto.");
  if (items.some(i => !(i.precio_total > 0)))
    return err("💲 Pon el valor según factura de cada producto.");
  const avisos = avisosSospecha(items);
  if (avisos.length && !confirm("⚠️ REVISA:\n\n" + avisos.join("\n") + "\n\n¿Seguro?")) return;
  const fd = new FormData();
  fd.append("datos", JSON.stringify({
    sin_oc: true, proveedor_nit: URG_PROV.nit, usuario_id: USUARIO?.id,
    observaciones: $("urg-obs").value || null, items }));
  for (const f of $("urg-foto").files) fd.append("fotos", f);
  try {
    await api("/llegadas/", { method: "POST", body: fd });
    ok("Urgencia registrada ✔ (quedó marcada para regularizar la OC en Zeus)");
    mostrar("menu");
  } catch (e) { err(e.message); }
});

/* ════ ARMADO ════ */
function onProgramaArmado() {
  $("arm-tipo-wrap").classList.toggle("hidden", programaSel("arm-programa") !== "AIPI");
}
async function pintarAvance() {
  onProgramaArmado();
  try {
    const av = await api("/operaciones/avance");
    $("avance-armado").innerHTML = av.map(a => {
      const pct = a.total ? Math.min(100, Math.round(a.armados * 100 / a.total)) : 0;
      return `<div class="bg-white rounded-xl shadow-sm p-3">
        <div class="flex justify-between text-sm font-bold">
          <span>${a.programa}</span><span>van ${a.armados.toLocaleString()} de ${a.total.toLocaleString()}</span>
        </div>
        <div class="mt-1 h-3 bg-gray-200 rounded-full overflow-hidden">
          <div class="h-3 rounded-full" style="width:${pct}%;background:var(--color-primario)"></div>
        </div>
        <div class="text-xs text-gray-500 mt-1">faltan ${a.faltan.toLocaleString()} paquetes</div>
      </div>`;
    }).join("") || "";
  } catch {}
}
async function cargarHistorialArmados() {
  try {
    const arms = await api("/operaciones/armados?limit=5");
    $("arm-historial").innerHTML = arms.length
      ? "<b>Últimos armados:</b><br>" + arms.map(a =>
          `• ${(a.fecha || "").slice(0, 10)} — ${a.programa}${a.tipo_paquete ? " / " + etiquetaTipo(a.tipo_paquete) : ""}: <b>${a.paquetes}</b> paq (${a.usuario || "?"})`).join("<br>")
      : "";
  } catch {}
}
$("btn-guardar-armado").addEventListener("click", async () => {
  const paquetes = parseInt($("arm-paquetes").value || 0);
  if (!paquetes) return err("Indica cuántos paquetes se armaron.");
  const prog = programaSel("arm-programa");
  try {
    await api("/operaciones/armados", { method: "POST", body: JSON.stringify({
      programa: prog,
      tipo_paquete: prog === "AIPI" ? tipoSel("arm-tipo") : null,
      paquetes, usuario_id: USUARIO?.id, observaciones: null }) });
    ok(`Armado registrado: ${paquetes} paquetes ✔`);
    $("arm-paquetes").value = "";
    pintarAvance(); cargarHistorialArmados();
  } catch (e) { err(e.message); }
});

/* ════ DESPACHO ════ */
function onProgramaDestino() {
  const prog = programaSel("dest-programa");
  const muns = CATALOGO.municipios[prog] || [];
  $("dest-municipio").innerHTML = muns.map(m => `<option>${m}</option>`).join("");
  $("dest-tipo").classList.toggle("hidden", prog !== "AIPI");
}
function pintarDestinos() {
  $("destinos-lista").innerHTML = DESTINOS.map((d, i) => {
    const c = COLORES_AIPI[d.tipo_paquete] || null;
    return `<div class="flex justify-between items-center rounded-lg px-3 py-2 text-sm border"
      style="background:${c ? c.bg : "#fef2f2"};border-color:#fca5a5">
      <span><b>${d.municipio}</b> · ${d.programa}${c ? " · " + c.label.split("—")[0].trim() : ""}
        — ${d.paquetes} paq${d.complementos ? " + " + d.complementos + " compl" : ""}</span>
      <button data-i="${i}" class="del-dest text-red-600 font-bold px-2">✕</button>
    </div>`;
  }).join("");
  document.querySelectorAll(".del-dest").forEach(b =>
    b.addEventListener("click", () => { DESTINOS.splice(parseInt(b.dataset.i), 1); pintarDestinos(); }));
}
$("btn-agregar-destino").addEventListener("click", () => {
  const paquetes = parseInt($("dest-paquetes").value || 0);
  if (!paquetes) return err("Indica los paquetes para el destino.");
  const prog = programaSel("dest-programa");
  DESTINOS.push({
    municipio: $("dest-municipio").value, programa: prog,
    tipo_paquete: prog === "AIPI" ? tipoSel("dest-tipo") : null,
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
      hora_salida: $("desp-hora").value || null, usuario_id: USUARIO?.id,
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
        <div class="text-sm font-bold">🚚 ${d.vehiculo_placa} · ${(d.fecha || "").slice(0, 10)}
          <span class="font-normal text-gray-500">salió ${d.hora_salida || "?"} — ${d.conductor || ""}</span></div>
        <div class="mt-2 space-y-2">
          ${d.destinos.map(x => x.entregado
            ? `<div class="text-sm text-green-700">✔ ${x.municipio} (${x.paquetes} paq) — ${x.hora_entrega} ${x.recibido_por ? "· recibió " + x.recibido_por : ""}</div>`
            : `<div class="border border-gray-200 rounded-lg p-2">
                <div class="text-sm font-medium">${x.municipio} · ${x.programa}${x.tipo_paquete ? " · " + etiquetaTipo(x.tipo_paquete).split("—")[0].trim() : ""} — ${x.paquetes} paq</div>
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
