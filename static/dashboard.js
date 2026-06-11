/* Panel del dueño — v2.1. El código se valida en el SERVIDOR (env DASHBOARD_CODE). */
const $ = (id) => document.getElementById(id);
const pesos = (v) => "$" + Number(v || 0).toLocaleString("es-CO", { maximumFractionDigits: 0 });

function vista(id) {
  ["puerta", "panel", "cargando"].forEach(v => $(v).classList.add("hidden"));
  $(id).classList.remove("hidden");
}

async function cargar(code) {
  vista("cargando");
  const r = await fetch(`/api/panel/resumen?code=${encodeURIComponent(code)}`);
  if (r.status === 401) {
    localStorage.removeItem("panel_code");
    vista("puerta");
    $("puerta-err").textContent = "Código incorrecto";
    $("puerta-err").classList.remove("hidden");
    return;
  }
  const d = await r.json();
  localStorage.setItem("panel_code", code);
  pintar(d);
  vista("panel");
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
    d.llegadas_por_dia.map(x => `<tr class="border-t">
      <td class="py-1.5">${x.dia}</td><td>${x.llegadas} llegada(s)</td>
      <td class="text-right font-bold">${pesos(x.valor)}</td></tr>`).join(""),
    ["Día", "Llegadas", "Valor estimado"]);

  let acumulado = 0;
  const factOrdenada = [...d.facturacion_por_dia].reverse();
  const filasFact = factOrdenada.map(x => {
    acumulado += x.valor;
    return { ...x, acumulado };
  }).reverse();
  $("tab-facturas").innerHTML = tabla(
    filasFact.map(x => `<tr class="border-t">
      <td class="py-1.5">${x.dia}</td><td>${x.facturas} factura(s)</td>
      <td class="text-right">${pesos(x.valor)}</td>
      <td class="text-right font-bold">${pesos(x.acumulado)}</td></tr>`).join(""),
    ["Día factura", "Facturas", "Valor del día", "Acumulado 14d"]);

  $("card-urgentes").classList.toggle("hidden", !d.llegadas_urgentes.length);
  $("tab-urgentes").innerHTML = d.llegadas_urgentes.map(u =>
    `<div class="border-t py-1.5">🚨 <b>${u.proveedor}</b> — ${u.fecha}${u.obs ? `<br><span class="text-xs text-gray-500">${u.obs}</span>` : ""}</div>`).join("");

  $("card-sospechosas").classList.toggle("hidden", !d.llegadas_sospechosas.length);
  $("tab-sospechosas").innerHTML = d.llegadas_sospechosas.map(s =>
    `<div class="border-t py-1.5">⚠️ <b>${s.proveedor}</b> (OC ${s.oc || "urgencia"}) — ${s.fecha}<br><span class="text-xs text-gray-600">${s.obs || ""}</span></div>`).join("");
}

$("btn-entrar").addEventListener("click", () => cargar($("codigo").value.trim()));
$("codigo").addEventListener("keydown", (e) => { if (e.key === "Enter") cargar($("codigo").value.trim()); });
$("btn-refrescar").addEventListener("click", () => cargar(localStorage.getItem("panel_code") || ""));
$("btn-salir").addEventListener("click", () => { localStorage.removeItem("panel_code"); vista("puerta"); });

const guardado = localStorage.getItem("panel_code");
if (guardado) cargar(guardado); else vista("puerta");
