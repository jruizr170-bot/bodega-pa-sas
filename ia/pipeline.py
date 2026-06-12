"""Punto de entrada único: leer_factura(fotos, oc_numero, db) → propuesta de pre-llenado.

Producción (POST /llegadas/leer-factura) y el backtest corren EXACTAMENTE este código.
"""
from typing import List, Optional

from ia import extraccion, matching


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def leer_factura(fotos_jpeg: List[bytes], oc_numero, db) -> dict:
    ext = extraccion.extraer_de_fotos(fotos_jpeg)
    if not ext.get("ok"):
        return {"ok": False, "error": ext.get("error", "error desconocido"),
                "costo_usd": ext.get("costo_usd", 0), "duracion_s": ext.get("duracion_s", 0)}

    d = ext["datos"]
    advertencias = []
    if not d.get("foto_valida", True):
        return {"ok": False, "error": "La foto no parece ser de una factura o remisión.",
                "costo_usd": ext["costo_usd"], "duracion_s": ext["duracion_s"]}
    calidad = d.get("calidad_foto", "buena")
    if calidad in ("mala", "ilegible"):
        advertencias.append("Foto de calidad %s: revisa bien los datos." % calidad)

    # proveedor
    prov_match = matching.match_proveedor(db, d.get("nit"), d.get("proveedor"))
    if not prov_match:
        advertencias.append("Proveedor no reconocido en el catálogo.")

    # señales para el matching de artículos
    catalogo = matching.cargar_catalogo(db)
    oc_items = matching.items_de_oc(db, oc_numero)
    codigos_oc = {i["articulo_codigo"] for i in oc_items}
    nit_para_historial = (prov_match or {}).get("nit") or d.get("nit")
    codigos_prov = matching.codigos_historial_proveedor(db, nit_para_historial)

    items = []
    no_reconocidos = 0
    for p in d.get("productos", []) or []:
        nombre_f = p.get("nombre") or ""
        candidatos = matching.match_articulo(nombre_f, catalogo, codigos_oc, codigos_prov)
        confianza = matching.clasificar_confianza(candidatos)
        top = candidatos[0] if candidatos else None

        conv = matching.convertir_a_base(
            p.get("cantidad"), p.get("unidad"), p.get("contenido_por_unidad"),
            top["presentacion"] if top else "")

        precio_total = _num(p.get("precio_total"))
        precio_unit = _num(p.get("precio_unitario"))
        if precio_total is None and precio_unit is not None and _num(p.get("cantidad")):
            precio_total = round(precio_unit * float(p["cantidad"]), 2)

        # referencia de precio: primero la OC, después el último costo del proveedor
        ref = None
        if top:
            for oi in oc_items:
                if oi["articulo_codigo"] == top["codigo"] and _num(oi.get("valor_unitario")):
                    ref = {"fuente": "oc", "valor_unitario": float(oi["valor_unitario"])}
                    break
            if ref is None:
                ref = matching.precio_referencia(db, nit_para_historial, top["codigo"])

        desvio_pct = None
        if ref and precio_unit:
            try:
                desvio_pct = round(abs(precio_unit - ref["valor_unitario"]) / ref["valor_unitario"] * 100, 1)
                if desvio_pct > matching.DESVIO_PRECIO_ADVERTIR * 100:
                    confianza = "media" if confianza == "alta" else confianza
            except ZeroDivisionError:
                pass

        if confianza == "baja":
            no_reconocidos += 1

        items.append({
            "nombre_factura": nombre_f,
            "cantidad_factura": p.get("cantidad"),
            "unidad_factura": p.get("unidad"),
            "articulo_codigo": top["codigo"] if top else None,
            "articulo_nombre": top["nombre"] if top else None,
            "presentacion": top["presentacion"] if top else None,
            "confianza": confianza,
            "score": top["score"] if top else 0,
            "en_oc": bool(top and top["codigo"] in codigos_oc),
            "cantidad_base": conv["cantidad_base"],
            "unidad_base": conv["unidad_base"],
            "conversion_confiable": conv["confiable"],
            "precio_total": precio_total,
            "precio_unitario": precio_unit,
            "precio_referencia": ref,
            "desvio_precio_pct": desvio_pct,
            "candidatos": [{"codigo": c["codigo"], "nombre": c["nombre"],
                            "presentacion": c["presentacion"], "score": c["score"]}
                           for c in candidatos],
        })

    if no_reconocidos:
        advertencias.append("%d producto(s) no reconocidos en el catálogo." % no_reconocidos)

    return {
        "ok": True,
        "calidad_foto": calidad,
        "tipo_documento": d.get("tipo_documento"),
        "documento": {"numero": d.get("numero_documento"), "fecha": d.get("fecha")},
        "proveedor": {
            "nit_factura": d.get("nit"),
            "nombre_factura": d.get("proveedor"),
            "match": prov_match,
        },
        "items": items,
        "datos_fiscales": d.get("datos_fiscales") or {},
        "observaciones_factura": d.get("observaciones"),
        "advertencias": advertencias,
        "modelo": ext["modelo"],
        "costo_usd": ext["costo_usd"],
        "tokens_input": ext["tokens_input"],
        "tokens_output": ext["tokens_output"],
        "duracion_s": ext["duracion_s"],
    }
