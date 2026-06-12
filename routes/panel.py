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

    return [{
        "id": l.id,
        "fecha": l.fecha_registro.isoformat() if l.fecha_registro else None,
        "oc_numero": l.oc_numero,
        "sin_oc": l.sin_oc,
        "sospechosa": l.sospechosa,
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
