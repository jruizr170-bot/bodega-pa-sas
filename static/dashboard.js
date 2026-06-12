/* Panel del dueño — v2.3. El código se valida en el SERVIDOR (env DASHBOARD_CODE).
   La clave se pide CADA VEZ que se abre el panel (no se recuerda en el teléfono). */
const $ = (id) => document.getElementById(id);
const pesos = (v) => "$" + Number(v || 0).toLocaleString("es-CO", { maximumFractionDigits: 0 });
let CODE = "";                       // solo en memoria mientras la página esté abierta
let FILTRO = { desde: "", hasta: "" };

function vista(id) {
  ["puerta", "panel", "cargando"].forEach(v => $(v).classList.add("hidden"));
  $(id).classList.remove("hidden");
}

function tab(cual) {
  $("vista-resumen").classList.toggle("hidden", cual !== "resumen");
  $("vista-facturas").classList.toggle("hidden", cual !== "facturas");
  const on = 'style="background:var(--color-primario)"';
  $("tab-btn-resumen").className = "tab-btn flex-1 rounded-xl py-2.5 font-bold " +
    (cual === "resumen" ? "text-white" : "bg-white text-gray-600 shadow");
  $("tab-btn-resumen").style.background = cual === "resumen" ? "var(--color-primario)" : "";
  $("tab-btn-facturas").className = "tab-btn flex-1 rounded-xl py-2.5 font-bold " +
    (cual === "facturas" ? "text-white" : "bg-white text-gray-600 shadow");
  $("tab-btn-facturas").style.background = cual === "facturas" ? "var(--color-primario)" : "";
  if (cual === "facturas") cargarFacturas();
}

async function cargar(code) {
  vista("cargando");
  const r = await fetch(`/api/panel/resumen?code=${encodeURIComponent(code)}`);
  if (r.status === 401) {
    CODE = "";
    vista("puerta");
    $("puerta-err").textContent = "Código incorrecto";
    $("puerta-err").classList.remove("hidden");
    return;
  }
  const d = await r.json();
  CODE = code;
  $("codigo").value = "";
  pintar(d);
  vista("panel");
  tab("resumen");
}

/* ── pestaña Facturas ── */
function veredictoIA(v) { return (v && v.titulo ? v.titulo : "").split("—").pop().trim(); }
function badgeIA(v) {
  if (!v) return '<span class="text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5">⏳ sin validar aún</span>';
  const ver = veredictoIA(v);
  if (["SIN_ERRORES", "SOLO_TYPOS", "SOLO_IVA"].includes(ver))
    return '<span class="text-xs bg-green-100 text-green-700 rounded-full px-2 py-0.5">🤖 ✓ coincide con la foto</span>';
  if (ver === "DATOS_INSUFICIENTES")
    return '<span class="text-xs bg-yellow-100 text-yellow-800 rounded-full px-2 py-0.5">🤖 📷 no se pudo leer la foto</span>';
  return '<span class="text-xs bg-red-100 text-red-700 rounded-full px-2 py-0.5">🤖 ⚠️ diferencias con la foto</span>';
}

function fmtU(cant, u) {
  if (u === "kg" || u === "L") return (Number(cant) / 1000).toLocaleString("es-CO") + " " + u;
  return Number(cant || 0).toLocaleString("es-CO") + " " + (u === "unidades" ? "und" : (u || ""));
}

async function cargarFacturas() {
  $("lista-facturas").innerHTML = '<div class="spinner mx-auto"></div>';
  const params = new URLSearchParams({ code: CODE });
  if (FILTRO.desde) params.set("desde", FILTRO.desde);
  if (FILTRO.hasta) params.set("hasta", FILTRO.hasta);
  const r = await fetch(`/api/panel/llegadas?${params}`);
  if (!r.ok) { $("lista-facturas").innerHTML = '<p class="text-sm text-red-600">No se pudo cargar.</p>'; return; }
  const llegs = await r.json();
  if (!llegs.length) { $("lista-facturas").innerHTML = '<p class="text-sm text-gray-400">Sin llegadas registradas en esas fechas.</p>'; return; }
  $("lista-facturas").innerHTML = llegs.map(l => `
    <div class="bg-white rounded-2xl shadow p-4">
      <div class="flex flex-wrap items-center gap-2">
        <b>${l.proveedor || "?"}</b>
        <span class="text-xs text-gray-400">${(l.fecha || "").slice(0, 16).replace("T", " ")}</span>
        ${l.historico
          ? `<span class="text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5">📜 ${l.factura ? "Factura " + l.factura : "app anterior"}</span>`
          : l.sin_oc ? '<span class="text-xs bg-orange-100 text-orange-700 rounded-full px-2 py-0.5">🚨 urgencia sin OC</span>'
                     : `<span class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">OC ${l.oc_numero}</span>`}
        ${l.sospechosa ? '<span class="text-xs bg-red-100 text-red-700 rounded-full px-2 py-0.5">⚠️ sospechosa</span>' : ""}
        ${l.historico ? "" : badgeIA(l.validacion_ia)}
      </div>
      <div class="text-xs text-gray-500 mt-0.5">Registró: ${l.usuario || "?"}</div>
      <table class="w-full mt-2 text-sm">
        <thead><tr class="text-left text-xs text-gray-400">
          <th class="py-1">Producto</th><th class="text-right">Llegó</th><th class="text-right">Valor factura</th></tr></thead>
        <tbody>
        ${l.items.map(i => `<tr class="border-t">
          <td class="py-1">${i.nombre}</td>
          <td class="text-right">${fmtU(i.cantidad_recibida, i.unidad_reportada)}</td>
          <td class="text-right font-bold">${i.precio_total ? pesos(i.precio_total) : "—"}</td></tr>`).join("")}
        <tr class="border-t"><td class="py-1 font-bold">TOTAL</td><td></td>
          <td class="text-right font-extrabold">${pesos(l.total)}</td></tr>
        </tbody>
      </table>
      ${l.observaciones ? `<div class="text-xs text-gray-500 mt-1">📝 ${l.observaciones}</div>` : ""}
      ${l.validacion_ia && !["SIN_ERRORES","SOLO_TYPOS","SOLO_IVA"].includes(veredictoIA(l.validacion_ia)) ? `<div class="text-xs text-red-700 bg-red-50 rounded-lg p-2 mt-2">🤖 ${l.validacion_ia.titulo}</div>` : ""}
      <div class="flex gap-2 mt-2 overflow-x-auto">
        ${l.fotos.map(f => `<a href="${f}" target="_blank"><img src="${f}" class="h-20 rounded-lg border border-gray-200" /></a>`).join("")}
      </div>
    </div>`).join("");
}

function pintar(d) {
  const hoy = new Date().toISOString().slice(0, 10);
  const llegHoy = d.llegadas_por_dia.find(x => x.dia === hoy) || { llegadas: 0, valor: 0 };
  const factSemana = d.facturacion_por_dia.slice(0, 7).reduce((s, x) => s + x.valor, 0);
  const armados = d.armados_semana.map(a => `${a.programa}: ${a.paquetes.toLocaleString()}`).join(" · ") || "0";

  $("tarjetas").innerHTML = [
    ["📦 Llegadas hoy", `${llegHoy.llegadas}`, pesos(llegHoy.valor)],
    ["🧾 Facturado 7 días", pesos(factSemana), `${d.facturacion_por_dia.slice(0, 7).reduce((s, x) => s + x.facturas, 0)} facturas`],
    ["🛠️ Armados 7 días", armados, ""],
    ["🚚 Rutas 7 días", `${d.despachos_semana.total}`, d.despachos_semana.con_entregas_pendientes ? `${d.despachos_semana.con_entregas_pendientes} con entregas pendientes` : "todo entregado"],
  ].map(([t, v, s]) => `
    <div class="bg-white rounded-2xl shadow p-3">
      <div class="text-xs text-gray-500">${t}</div>
      <div class="text-lg font-extrabold leading-tight">${v}</div>
      <div class="text-xs text-gray-400">${s}</div>
    </div>`).join("");

  const tabla = (filas, cols) => filas.length
    ? `<table class="w-full"><thead><tr class="text-left text-xs text-gray-400">
        ${cols.map(c => `<th class="py-1">${c}</th>`).join("")}</tr></thead><tbody>` +
      filas + "</tbody></table>"
    : '<p class="text-gray-400">Sin datos todavía.</p>';

  $("tab-llegadas").innerHTML = tabla(
    d.llegadas_por_dia.map(x => `<tr class="border-t dia-lleg cursor-pointer active:bg-red-50" data-dia="${x.dia}">
      <td class="py-1.5 underline decoration-dotted">${x.dia}</td><td>${x.llegadas} llegada(s)</td>
      <td class="text-right font-bold">${pesos(x.valor)}</td></tr>`).join(""),
    ["Día", "Llegadas", "Valor estimado"]);
  document.querySelectorAll(".dia-lleg").forEach(tr => tr.addEventListener("click", () => {
    FILTRO = { desde: tr.dataset.dia, hasta: tr.dataset.dia };
    $("f-desde").value = tr.dataset.dia; $("f-hasta").value = tr.dataset.dia;
    tab("facturas");
  }));

  let acumulado = 0;
  const factOrdenada = [...d.facturacion_por_dia].reverse();
  const filasFact = factOrdenada.map(x => {
    acumulado += x.valor;
    return { ...x, acumulado };
  }).reverse();
  $("tab-facturas").innerHTML = tabla(
    filasFact.map(x => `<tr class="border-t dia-fact cursor-pointer active:bg-red-50" data-dia="${x.dia}">
      <td class="py-1.5"><span class="underline decoration-dotted">${x.dia}</span> <span class="text-gray-400">▸</span></td>
      <td>${x.facturas} factura(s)</td>
      <td class="text-right">${pesos(x.valor)}</td>
      <td class="text-right font-bold">${pesos(x.acumulado)}</td></tr>
      <tr class="hidden" id="det-${x.dia}"><td colspan="4" class="bg-gray-50 rounded-lg p-2"></td></tr>`).join(""),
    ["Día factura", "Facturas", "Valor del día", "Acumulado 14d"]);
  document.querySelectorAll(".dia-fact").forEach(tr =>
    tr.addEventListener("click", () => toggleDia(tr.dataset.dia, tr)));

  $("card-urgentes").classList.toggle("hidden", !d.llegadas_urgentes.length);
  $("tab-urgentes").innerHTML = d.llegadas_urgentes.map(u =>
    `<div class="border-t py-1.5">🚨 <b>${u.proveedor}</b> — ${u.fecha}${u.obs ? `<br><span class="text-xs text-gray-500">${u.obs}</span>` : ""}</div>`).join("");

  $("card-sospechosas").classList.toggle("hidden", !d.llegadas_sospechosas.length);
  $("tab-sospechosas").innerHTML = d.llegadas_sospechosas.map(s =>
    `<div class="border-t py-1.5">⚠️ <b>${s.proveedor}</b> (OC ${s.oc || "urgencia"}) — ${s.fecha}<br><span class="text-xs text-gray-600">${s.obs || ""}</span></div>`).join("");
}

/* ── detalle de un día de facturación (click en la fila) ── */
async function toggleDia(dia, fila) {
  const det = $(`det-${dia}`);
  if (!det) return;
  if (!det.classList.contains("hidden")) { det.classList.add("hidden"); return; }
  document.querySelectorAll("[id^='det-']").forEach(x => x.classList.add("hidden"));
  det.classList.remove("hidden");
  const celda = det.firstElementChild;
  celda.innerHTML = '<div class="spinner mx-auto"></div>';
  const r = await fetch(`/api/panel/facturas-dia?dia=${dia}&code=${encodeURIComponent(CODE)}`);
  if (!r.ok) { celda.innerHTML = '<p class="text-xs text-red-600">No se pudo cargar el detalle.</p>'; return; }
  const facturas = await r.json();
  if (!facturas.length) { celda.innerHTML = '<p class="text-xs text-gray-400 p-2">Sin detalle para este día.</p>'; return; }
  celda.innerHTML = facturas.map(f => `
    <div class="bg-white rounded-xl border border-gray-200 p-3 my-1.5 text-sm">
      <div class="flex flex-wrap items-center gap-2">
        <b>${f.proveedor || "?"}</b>
        ${f.factura ? `<span class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">Factura ${f.factura}</span>` : ""}
        ${f.oc_numero ? `<span class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">OC ${f.oc_numero}</span>` : ""}
        <span class="ml-auto font-extrabold">${pesos(f.total)}</span>
      </div>
      <table class="w-full mt-1.5 text-xs">
        <thead><tr class="text-left text-gray-400"><th>Producto</th><th class="text-right">Cant.</th><th class="text-right">Vr. unit</th><th class="text-right">Total</th></tr></thead>
        <tbody>${f.items.map(i => `<tr class="border-t">
          <td class="py-0.5">${i.nombre}</td>
          <td class="text-right">${i.cantidad.toLocaleString("es-CO")}</td>
          <td class="text-right">${pesos(i.valor_unitario)}</td>
          <td class="text-right font-bold">${pesos(i.total)}</td></tr>`).join("")}</tbody>
      </table>
      ${f.llegadas_app.length ? f.llegadas_app.map(l => `
        <div class="mt-2 bg-green-50 border border-green-200 rounded-lg p-2 text-xs">
          📦 Bodega registró esta OC: <b>${l.usuario || "?"}</b> el ${l.fecha}
          <div class="flex gap-2 mt-1 overflow-x-auto">
            ${l.fotos.map(u => `<a href="${u}" target="_blank"><img src="${u}" class="h-16 rounded border border-gray-200" /></a>`).join("")}
          </div>
        </div>`).join("")
        : '<div class="mt-2 text-xs text-gray-400">Bodega no registró esta OC en la app (o entró antes de la app).</div>'}
    </div>`).join("");
}

$("btn-entrar").addEventListener("click", () => cargar($("codigo").value.trim()));
$("codigo").addEventListener("keydown", (e) => { if (e.key === "Enter") cargar($("codigo").value.trim()); });
$("btn-refrescar").addEventListener("click", () => cargar(CODE));
$("btn-salir").addEventListener("click", () => { CODE = ""; vista("puerta"); });
$("tab-btn-resumen").addEventListener("click", () => tab("resumen"));
$("tab-btn-facturas").addEventListener("click", () => tab("facturas"));

/* filtros por fecha de la pestaña Facturas */
const hoyISO = () => new Date().toISOString().slice(0, 10);
const haceISO = (dias) => new Date(Date.now() - dias * 86400000).toISOString().slice(0, 10);
document.querySelectorAll(".rango").forEach(b => b.addEventListener("click", () => {
  const r = b.dataset.rango;
  if (r === "hoy") FILTRO = { desde: hoyISO(), hasta: hoyISO() };
  else if (r === "todo") FILTRO = { desde: "", hasta: "" };
  else FILTRO = { desde: haceISO(parseInt(r)), hasta: hoyISO() };
  $("f-desde").value = FILTRO.desde; $("f-hasta").value = FILTRO.hasta;
  cargarFacturas();
}));
$("f-aplicar").addEventListener("click", () => {
  FILTRO = { desde: $("f-desde").value, hasta: $("f-hasta").value };
  cargarFacturas();
});

// la clave se pide SIEMPRE al abrir el panel (limpieza por si quedó guardada antes)
localStorage.removeItem("panel_code");
vista("puerta");
