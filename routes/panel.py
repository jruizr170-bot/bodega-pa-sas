"""Panel del dueño — resumen gerencial protegido por código de acceso.

No es seguridad bancaria: es un código compartido (env DASHBOARD_CODE) para que
los bodegueros no entren por accidente. Todos los valores monetarios salen de
las OCs / entradas de Zeus, nunca de datos digitados en la app.
"""
import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db

router = APIRouter(prefix="/panel", tags=["panel"])

CODIGO = os.environ.get("DASHBOARD_CODE", "2006")


def _check(code: str):
    if code != CODIGO:
        raise HTTPException(401, "Código incorrecto")


@router.get("/resumen")
def resumen(code: str = "", db: Session = Depends(get_db)):
    _check(code)
    hace14 = (date.today() - timedelta(days=14)).isoformat()
    hace7 = (date.today() - timedelta(days=7)).isoformat()

    # Llegadas por día con valor estimado (cantidad recibida x precio de la OC)
    llegadas_dia = db.execute(text("""
        SELECT DATE(l.fecha_registro) AS dia,
               COUNT(DISTINCT l.id) AS llegadas,
               COALESCE(SUM(li.cantidad_recibida * COALESCE(oci.valor_unitario, 0)), 0) AS valor
        FROM llegadas l
        JOIN llegada_items li ON li.llegada_id = l.id
        LEFT JOIN ordenes_compra oc ON oc.orden_numero = l.oc_numero
        LEFT JOIN ordenes_compra_items oci
               ON oci.orden_id = oc.id AND oci.articulo_codigo = li.articulo_codigo
        WHERE l.fecha_registro >= :f
        GROUP BY DATE(l.fecha_registro) ORDER BY dia DESC
    """), {"f": hace14}).fetchall()

    # Facturación real por día (entradas del ERP, sincronizadas desde Zeus)
    facturacion_dia = db.execute(text("""
        SELECT e.fecha_factura AS dia, COUNT(DISTINCT e.consecutivo) AS facturas,
               COALESCE(SUM(i.costo_total), 0) AS valor
        FROM entradas_zeus e
        JOIN entradas_zeus_items i ON i.entrada_consecutivo = e.consecutivo
        WHERE e.fecha_factura >= :f
        GROUP BY e.fecha_factura ORDER BY dia DESC
    """), {"f": hace14}).fetchall()

    armados = db.execute(text("""
        SELECT programa, COALESCE(SUM(paquetes), 0) FROM armados
        WHERE fecha >= :f GROUP BY programa
    """), {"f": hace7}).fetchall()

    despachos = db.execute(text("""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN EXISTS (
                   SELECT 1 FROM despacho_destinos x
                   WHERE x.despacho_id = d.id AND x.hora_entrega IS NULL
               ) THEN 1 ELSE 0 END), 0)
        FROM despachos d WHERE d.fecha >= :f
    """), {"f": hace7}).fetchone()

    urgentes = db.execute(text("""
        SELECT l.id, l.proveedor_nombre, l.fecha_registro, l.observaciones
        FROM llegadas l WHERE l.sin_oc = true AND l.fecha_registro >= :f
        ORDER BY l.fecha_registro DESC
    """), {"f": hace14}).fetchall()

    sospechosas = db.execute(text("""
        SELECT l.id, l.oc_numero, l.proveedor_nombre, l.fecha_registro, l.observaciones
        FROM llegadas l WHERE l.sospechosa = true AND l.fecha_registro >= :f
        ORDER BY l.fecha_registro DESC
    """), {"f": hace14}).fetchall()

    return {
        "llegadas_por_dia": [
            {"dia": str(d), "llegadas": int(n), "valor": float(v)}
            for d, n, v in llegadas_dia],
        "facturacion_por_dia": [
            {"dia": str(d), "facturas": int(n), "valor": float(v)}
            for d, n, v in facturacion_dia],
        "armados_semana": [{"programa": p, "paquetes": int(n)} for p, n in armados],
        "despachos_semana": {"total": int(despachos[0] or 0),
                             "con_entregas_pendientes": int(despachos[1] or 0)},
        "llegadas_urgentes": [
            {"id": i, "proveedor": p, "fecha": str(f)[:16], "obs": o}
            for i, p, f, o in urgentes],
        "llegadas_sospechosas": [
            {"id": i, "oc": oc, "proveedor": p, "fecha": str(f)[:16], "obs": o}
            for i, oc, p, f, o in sospechosas],
    }


@router.get("/llegadas")
def llegadas(code: str = "", limit: int = 100, desde: str = "", hasta: str = "",
             db: Session = Depends(get_db)):
    """Todas las facturas/llegadas registradas por los bodegueros, con fotos,
    precios digitados y el veredicto del agente IA (si ya corrió).
    desde/hasta (YYYY-MM-DD) filtran por fecha de registro."""
    _check(code)
    q = (db.query(models.Llegada)
           .options(joinedload(models.Llegada.items),
                    joinedload(models.Llegada.fotos),
                    joinedload(models.Llegada.usuario)))
    if desde:
        q = q.filter(models.Llegada.fecha_registro >= desde)
    if hasta:
        q = q.filter(models.Llegada.fecha_registro < f"{hasta} 23:59:59")
    llegs = q.order_by(models.Llegada.fecha_registro.desc()).limit(limit).all()

    # Veredicto IA por llegada (tabla analisis_agente, escrita por el lote 8am/2pm)
    validaciones = {}
    try:
        for lid, titulo, contenido in db.execute(text("""
            SELECT DISTINCT ON (llegada_id) llegada_id, titulo, contenido
            FROM analisis_agente
            WHERE tipo = 'LLEGADA_VALIDACION' AND llegada_id IS NOT NULL
            ORDER BY llegada_id, fecha DESC
        """)):
            validaciones[lid] = {"titulo": titulo, "detalle": contenido}
    except Exception:
        db.rollback()  # la tabla puede no existir aún (ej. SQLite local)

    out = [{
        "id": l.id,
        "fecha": l.fecha_registro.isoformat() if l.fecha_registro else None,
        "oc_numero": l.oc_numero,
        "sin_oc": l.sin_oc,
        "sospechosa": l.sospechosa,
        "historico": False,
        "proveedor": l.proveedor_nombre,
        "usuario": l.usuario.nombre if l.usuario else None,
        "observaciones": l.observaciones,
        "fotos": [f.url for f in l.fotos],
        "total": sum(i.precio_total or 0 for i in l.items),
        "items": [{
            "nombre": i.articulo_nombre,
            "cantidad_recibida": i.cantidad_recibida,
            "cantidad_esperada": i.cantidad_esperada,
            "unidad_reportada": i.unidad_reportada,
            "precio_total": i.precio_total,
        } for i in l.items],
        "validacion_ia": validaciones.get(l.id),
    } for l in llegs]

    # Histórico de la app ANTERIOR (v1, tablas recepciones/recepcion_fotos):
    # ahí están todas las fotos que subieron los bodegueros antes de la v2.
    try:
        cond, params = "", {"lim": limit}
        if desde:
            cond += " AND r.fecha_registro >= CAST(:desde AS timestamp)"
            params["desde"] = desde
        if hasta:
            cond += " AND r.fecha_registro < CAST(:hasta AS timestamp) + interval '1 day'"
            params["hasta"] = hasta
        recs = db.execute(text(f"""
            SELECT r.id, r.fecha_registro, r.numero_factura,
                   COALESCE(NULLIF(r.proveedor_nombre, ''), p.nombre) AS proveedor,
                   r.total_factura, r.observaciones, u.nombre AS usuario
            FROM recepciones r
            LEFT JOIN usuarios u ON u.id = r.usuario_id
            LEFT JOIN proveedores p ON p.id = r.proveedor_id
            WHERE 1=1 {cond}
            ORDER BY r.fecha_registro DESC LIMIT :lim
        """), params).fetchall()
        ids = [r[0] for r in recs]
        fotos_rec, items_rec = {}, {}
        if ids:
            for rid, url in db.execute(text(
                    "SELECT recepcion_id, url FROM recepcion_fotos "
                    "WHERE recepcion_id = ANY(:i)"), {"i": ids}):
                fotos_rec.setdefault(rid, []).append(url)
            for rid, desc, cant, uni, total in db.execute(text(
                    "SELECT recepcion_id, descripcion, cantidad, unidad, total "
                    "FROM recepcion_items WHERE recepcion_id = ANY(:i)"), {"i": ids}):
                items_rec.setdefault(rid, []).append({
                    "nombre": desc, "cantidad_recibida": float(cant or 0),
                    "cantidad_esperada": None, "unidad_reportada": uni,
                    "precio_total": float(total or 0)})
        for (rid, fecha, nfac, prov, total, obs, usuario) in recs:
            out.append({
                "id": rid,
                "fecha": fecha.isoformat() if fecha else None,
                "oc_numero": None, "sin_oc": False, "sospechosa": False,
                "historico": True, "factura": nfac,
                "proveedor": prov, "usuario": usuario, "observaciones": obs,
                "fotos": fotos_rec.get(rid, []),
                "total": float(total or 0) or sum(i["precio_total"] for i in items_rec.get(rid, [])),
                "items": items_rec.get(rid, []),
                "validacion_ia": None,
            })
    except Exception:
        db.rollback()  # tablas v1 pueden no existir en una BD nueva

    out.sort(key=lambda x: x["fecha"] or "", reverse=True)
    return out[:limit]


@router.get("/facturas-dia")
def facturas_dia(dia: str, code: str = "", db: Session = Depends(get_db)):
    """Detalle de la facturación de un día (entradas del ERP Zeus): cada factura
    con sus productos, y si bodega registró la llegada de esa OC en la app,
    la foto y quién la subió."""
    _check(code)
    rows = db.execute(text("""
        SELECT e.consecutivo, e.proveedor_nombre, e.factura_proveedor, e.oc_numero,
               COALESCE(SUM(i.costo_total), 0) AS total
        FROM entradas_zeus e
        JOIN entradas_zeus_items i ON i.entrada_consecutivo = e.consecutivo
        WHERE e.fecha_factura = :d
        GROUP BY e.consecutivo, e.proveedor_nombre, e.factura_proveedor, e.oc_numero
        ORDER BY total DESC
    """), {"d": dia}).fetchall()

    # llegadas registradas en la app para las OCs de ese día (foto + quién)
    ocs = [str(r[3]) for r in rows if r[3]]
    llegadas_oc = {}
    if ocs:
        llegs = (db.query(models.Llegada)
                   .options(joinedload(models.Llegada.fotos),
                            joinedload(models.Llegada.usuario))
                   .filter(models.Llegada.oc_numero.in_(ocs)).all())
        for l in llegs:
            llegadas_oc.setdefault(l.oc_numero, []).append({
                "id": l.id,
                "usuario": l.usuario.nombre if l.usuario else None,
                "fecha": l.fecha_registro.isoformat()[:16] if l.fecha_registro else None,
                "fotos": [f.url for f in l.fotos],
            })

    out = []
    for cons, prov, fac, oc, total in rows:
        items = db.execute(text("""
            SELECT articulo_nombre, cantidad, valor_unitario, costo_total
            FROM entradas_zeus_items WHERE entrada_consecutivo = :c
            ORDER BY costo_total DESC
        """), {"c": cons}).fetchall()
        out.append({
            "consecutivo": cons,
            "proveedor": prov,
            "factura": fac,
            "oc_numero": oc,
            "total": float(total),
            "items": [{"nombre": n, "cantidad": float(c or 0),
                       "valor_unitario": float(v or 0), "total": float(t or 0)}
                      for n, c, v, t in items],
            "llegadas_app": llegadas_oc.get(str(oc) if oc else "", []),
        })
    return out


# ── Digitación asistida: llegadas listas para pasar a Zeus ────────────────────

def _fmt_cantidad(base, unidad):
    """14400 g → '14,4 kg' / 24000 ml → '24 L' / 300 und → '300 und'."""
    base = float(base or 0)
    if unidad == "unidades" or unidad == "und":
        return "%s und" % ("{:,.0f}".format(base).replace(",", "."))
    grande = base / 1000.0
    if unidad in ("g", "kg"):
        return "%s kg" % ("{:,.2f}".format(grande).rstrip("0").rstrip(".").replace(",", "@").replace(".", ",").replace("@", "."))
    if unidad in ("ml", "l"):
        return "%s L" % ("{:,.2f}".format(grande).rstrip("0").rstrip(".").replace(",", "@").replace(".", ",").replace("@", "."))
    return "{:,.0f}".format(base).replace(",", ".")


@router.get("/digitacion")
def digitacion(code: str = "", db: Session = Depends(get_db)):
    """Llegadas confirmadas pendientes de digitar en Zeus, con los campos
    formateados como la pantalla de Entrada de Zeus los pide."""
    _check(code)
    llegs = (db.query(models.Llegada)
               .options(joinedload(models.Llegada.items),
                        joinedload(models.Llegada.usuario),
                        joinedload(models.Llegada.fotos))
               .filter((models.Llegada.zeus_estado == "PENDIENTE")
                       | (models.Llegada.zeus_estado.is_(None)))
               .order_by(models.Llegada.fecha_registro)
               .all())
    out = []
    for l in llegs:
        items = []
        for i in l.items:
            if not (i.cantidad_recibida or 0) > 0:
                continue
            unidad_base = "und" if (i.unidad_reportada or "") == "unidades" else \
                          ("g" if (i.unidad_reportada or "") in ("g", "kg") else
                           ("ml" if (i.unidad_reportada or "") in ("ml", "L", "l") else "und"))
            valor_unidad = round((i.precio_total or 0) / i.cantidad_recibida, 4) if i.cantidad_recibida else None
            items.append({
                "articulo_codigo": i.articulo_codigo,
                "articulo_nombre": i.articulo_nombre,
                "cantidad_base": i.cantidad_recibida,
                "unidad_base": unidad_base,
                "cantidad_fmt": _fmt_cantidad(i.cantidad_recibida, i.unidad_reportada or "und"),
                "valor_unidad_zeus": valor_unidad,   # CostoTotal / Cantidad (convención Zeus)
                "precio_unitario_factura": i.precio_unitario,
                "iva_porcentaje": i.iva_porcentaje,
                "precio_total": i.precio_total,
            })
        out.append({
            "id": l.id,
            "fecha_registro": l.fecha_registro.isoformat()[:16] if l.fecha_registro else None,
            "oc_numero": l.oc_numero,
            "sin_oc": l.sin_oc,
            "proveedor_nit": (l.proveedor_nit or "").strip(),
            "proveedor_nombre": l.proveedor_nombre,
            "factura_numero": l.factura_numero,
            "bodega_destino": l.bodega_destino,
            "usuario": l.usuario.nombre if l.usuario else None,
            "observaciones": l.observaciones,
            "fotos": [f.url for f in l.fotos],
            "total_llegada": round(sum(i.precio_total or 0 for i in l.items), 2),
            "items": items,
        })
    return out


@router.post("/digitacion/{llegada_id}/marcar")
def marcar_digitada(llegada_id: int, datos: dict, code: str = "", db: Session = Depends(get_db)):
    """Marca una llegada como ya ingresada en Zeus (o NO_APLICA)."""
    from datetime import datetime as _dt
    _check(code)
    lleg = db.query(models.Llegada).filter_by(id=llegada_id).first()
    if not lleg:
        raise HTTPException(404, "Llegada no encontrada")
    if datos.get("no_aplica"):
        lleg.zeus_estado = "NO_APLICA"
    else:
        consecutivo = str(datos.get("zeus_consecutivo") or "").strip()
        if not consecutivo:
            raise HTTPException(422, "Falta el consecutivo de la Entrada en Zeus")
        lleg.zeus_estado = "INGRESADA"
        lleg.zeus_consecutivo = consecutivo
    lleg.zeus_marcada_en = _dt.utcnow()
    db.commit()
    return {"id": lleg.id, "zeus_estado": lleg.zeus_estado,
            "zeus_consecutivo": lleg.zeus_consecutivo}
