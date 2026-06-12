"""BODEGA — Llegada física de mercancía.

Dos flujos, ambos con FOTO OBLIGATORIA y cero texto libre:
- Normal: guiada por las OCs abiertas de Zeus (sincronizadas a Neon cada 30 min).
- Urgencia (sin_oc): pedidos urgentes sin OC montada; proveedor y productos se
  eligen de los catálogos oficiales (proveedores / articulos_zeus).

El bodeguero solo ajusta cantidades. Nunca digita nombres ni precios.
Validación anti "errores bobos": cantidades muy fuera de lo esperado marcan la
llegada como sospechosa (no se bloquea, pero gerencia la ve resaltada).
"""
import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_, text
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from routes.fotos import _save_photo, comprimir_imagen

router = APIRouter(prefix="/llegadas", tags=["llegadas"])

ESTADOS_ABIERTOS = ["PENDIENTE", "PARCIAL", "ATRASADA"]
FACTOR_SOSPECHA = 1.5        # recibido > 1.5x lo esperado
UND_GIGANTE = 100_000        # "unidades" con número absurdo
DESVIO_PRECIO = 0.20         # precio digitado vs (cantidad x valor unitario OC)


# ── Catálogos para autocomplete (urgencias) ───────────────────────────────────

@router.get("/buscar-proveedores")
def buscar_proveedores(q: str = "", db: Session = Depends(get_db)):
    """Proveedores reales (sincronizados desde Zeus/Terceros). Por nombre o NIT."""
    q = q.strip()
    if len(q) < 2:
        return []
    provs = (db.query(models.Proveedor)
               .filter(or_(models.Proveedor.nombre.ilike(f"%{q}%"),
                           models.Proveedor.nit.like(f"{q}%")))
               .order_by(models.Proveedor.nombre).limit(10).all())
    return [{"nit": p.nit, "nombre": p.nombre} for p in provs]


@router.get("/buscar-articulos")
def buscar_articulos(q: str = "", db: Session = Depends(get_db)):
    """Maestro oficial de artículos de Zeus — evita 'mismo producto, otro nombre'."""
    q = q.strip()
    if len(q) < 2:
        return []
    arts = (db.query(models.ArticuloZeus)
              .filter(models.ArticuloZeus.nombre.ilike(f"%{q}%"),
                      models.ArticuloZeus.deshabilitado.isnot(True))
              .order_by(models.ArticuloZeus.nombre).limit(10).all())
    return [{"codigo": a.codigo, "nombre": a.nombre,
             "presentacion": a.presentacion} for a in arts]


# ── Lectura de factura con IA (pre-llenado; el bodeguero siempre confirma) ────

@router.get("/ia-estado")
def ia_estado():
    """La UI muestra el botón de IA solo si el flag está prendido (env, sin redeploy)."""
    return {"activo": os.environ.get("PRELLENADO_IA", "off").lower() == "on"}


@router.get("/bodegas")
def bodegas(db: Session = Depends(get_db)):
    """Bodegas/líneas de negocio reales (de las entradas Zeus). Etiquetas por env."""
    try:
        filas = db.execute(text(
            "SELECT DISTINCT bodega FROM entradas_zeus_items "
            "WHERE bodega IS NOT NULL ORDER BY 1")).fetchall()
        codigos = [f[0] for f in filas]
    except Exception:
        db.rollback()
        codigos = []
    try:
        labels = json.loads(os.environ.get("BODEGAS_LABELS", "{}"))
    except json.JSONDecodeError:
        labels = {}
    return [{"codigo": c, "nombre": labels.get(c, f"Bodega {c}")} for c in codigos]


def _guardar_telemetria(db: Session, propuesta: dict) -> Optional[int]:
    """Registra la lectura en analisis_agente (la tabla la crea el sistema de agentes)."""
    try:
        fila = db.execute(text(
            "INSERT INTO analisis_agente (fecha, tipo, agente, modelo_usado, severidad, "
            "titulo, contenido, datos_json, monto_en_riesgo, tokens_input, tokens_output, "
            "costo_usd) VALUES (now(), 'LLEGADA_PRELLENADO', 'PRELLENADO', :modelo, 'INFO', "
            ":titulo, :contenido, :datos, 0, :tin, :tout, :costo) RETURNING id"),
            {"modelo": propuesta.get("modelo"),
             "titulo": "Pre-llenado IA (%s items, %s)" % (
                len(propuesta.get("items", [])), propuesta.get("calidad_foto", "?")),
             "contenido": json.dumps({"advertencias": propuesta.get("advertencias", [])}),
             "datos": json.dumps(propuesta, default=str),
             "tin": propuesta.get("tokens_input", 0),
             "tout": propuesta.get("tokens_output", 0),
             "costo": propuesta.get("costo_usd", 0)}).fetchone()
        db.commit()
        return fila[0]
    except Exception:
        db.rollback()
        return None


@router.post("/leer-factura")
def leer_factura(
    fotos: list[UploadFile] = File(...),
    oc_numero: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Lee la(s) foto(s) con IA y devuelve la propuesta de pre-llenado.

    Nunca tumba el flujo: ante cualquier problema responde {"ok": false} y el
    bodeguero digita manual como siempre.
    """
    if os.environ.get("PRELLENADO_IA", "off").lower() != "on":
        raise HTTPException(503, "Lectura con IA desactivada")
    if not fotos or all(not f.filename for f in fotos):
        raise HTTPException(422, "Adjunta al menos una foto")
    if os.environ.get("ANTHROPIC_API_KEY") is None:
        return {"ok": False, "error": "IA sin configurar en el servidor"}

    fotos_bytes = [comprimir_imagen(f.file.read()) for f in fotos if f.filename]
    try:
        from ia import pipeline
        propuesta = pipeline.leer_factura(fotos_bytes, oc_numero, db)
    except Exception as e:
        return {"ok": False, "error": "Error inesperado leyendo la factura: %s" % e}

    if propuesta.get("ok"):
        propuesta["prellenado_id"] = _guardar_telemetria(db, propuesta)
    return propuesta


# ── OCs abiertas ──────────────────────────────────────────────────────────────

@router.get("/ocs-abiertas")
def ocs_abiertas(db: Session = Depends(get_db)):
    ocs = (db.query(models.OrdenCompraZeus)
             .options(joinedload(models.OrdenCompraZeus.items))
             .filter(models.OrdenCompraZeus.estado.in_(ESTADOS_ABIERTOS))
             .order_by(models.OrdenCompraZeus.fecha_entrega)
             .all())
    hoy = datetime.utcnow().date()
    out = []
    for oc in ocs:
        entrega = oc.fecha_entrega
        if hasattr(entrega, "date"):
            entrega = entrega.date()
        pendientes = [i for i in oc.items if (i.faltante or 0) > 0]
        mostrar = pendientes or oc.items
        out.append({
            "orden_numero": oc.orden_numero,
            "proveedor_nit": oc.proveedor_nit,
            "proveedor_nombre": oc.proveedor_nombre,
            "fecha_entrega": entrega.isoformat() if entrega else None,
            "dias_atraso": (hoy - entrega).days if entrega and entrega < hoy else 0,
            "estado": oc.estado,
            "items": [{
                "articulo_codigo": i.articulo_codigo,
                "articulo_nombre": i.articulo_nombre,
                "faltante": (i.faltante or 0) if pendientes else (i.cantidad or 0),
                "cantidad": i.cantidad or 0,
            } for i in mostrar],
        })
    return out


# ── Crear llegada (multipart: datos + fotos en la MISMA petición) ─────────────

def _validar_sospecha(items: list[dict], precios_oc: Optional[dict] = None) -> list[str]:
    motivos = []
    for it in items:
        esperado = float(it.get("cantidad_esperada") or 0)
        recibido = float(it.get("cantidad_recibida") or 0)
        unidad = (it.get("unidad_reportada") or "").lower()
        nombre = it.get("articulo_nombre", "?")
        if esperado > 0 and recibido > esperado * FACTOR_SOSPECHA:
            motivos.append(f"{nombre}: llegó {recibido:,.0f} vs {esperado:,.0f} esperado")
        if unidad == "unidades" and recibido > UND_GIGANTE:
            motivos.append(f"{nombre}: {recibido:,.0f} 'unidades' parece un gramaje")
        # precio digitado vs lo que valdría según la OC de Zeus
        vu = (precios_oc or {}).get(it.get("articulo_codigo")) or 0
        precio = float(it.get("precio_total") or 0)
        if vu > 0 and recibido > 0 and precio > 0:
            segun_oc = recibido * vu
            if abs(precio - segun_oc) > segun_oc * DESVIO_PRECIO:
                motivos.append(f"{nombre}: factura ${precio:,.0f} vs ${segun_oc:,.0f} según la OC")
    return motivos


@router.post("/", status_code=201)
def crear(
    datos: str = Form(...),               # JSON: oc_numero|sin_oc, proveedor, usuario, items
    fotos: list[UploadFile] = File(...),  # OBLIGATORIO: minimo 1 foto de la factura
    db: Session = Depends(get_db),
):
    if not fotos or all(not f.filename for f in fotos):
        raise HTTPException(422, "La foto de la factura/remisión es obligatoria")
    try:
        payload = json.loads(datos)
    except json.JSONDecodeError:
        raise HTTPException(422, "Datos inválidos")

    items = payload.get("items") or []
    if not items:
        raise HTTPException(422, "La llegada debe tener al menos un producto")
    for it in items:
        if (float(it.get("cantidad_recibida") or 0) > 0
                and float(it.get("precio_total") or 0) <= 0):
            raise HTTPException(
                422, f"Falta el valor según factura de: {it.get('articulo_nombre')}")

    precios_oc = {}
    sin_oc = bool(payload.get("sin_oc"))
    if sin_oc:
        nit = (payload.get("proveedor_nit") or "").strip()
        prov = db.query(models.Proveedor).filter_by(nit=nit).first()
        if not prov:
            raise HTTPException(422, "Proveedor no válido: elígelo del buscador")
        oc_numero, proveedor_nit, proveedor_nombre = None, prov.nit, prov.nombre
        # items deben venir del catálogo oficial
        codigos = {a.codigo for a in db.query(models.ArticuloZeus.codigo).filter(
            models.ArticuloZeus.codigo.in_([i.get("articulo_codigo") for i in items]))}
        for it in items:
            if it.get("articulo_codigo") not in codigos:
                raise HTTPException(422, f"Producto no válido: {it.get('articulo_nombre')}")
    else:
        oc_numero = str(payload.get("oc_numero") or "").strip()
        oc = db.query(models.OrdenCompraZeus).filter_by(orden_numero=oc_numero).first()
        if not oc:
            raise HTTPException(422, "OC no encontrada")
        proveedor_nit, proveedor_nombre = oc.proveedor_nit, oc.proveedor_nombre
        precios_oc = {i.articulo_codigo: (i.valor_unitario or 0)
                      for i in db.query(models.OrdenCompraZeusItem)
                                  .filter_by(orden_id=oc.id)}

    motivos = _validar_sospecha(items, precios_oc)
    obs = payload.get("observaciones") or None
    if motivos:
        marca = "⚠️ REVISAR: " + " | ".join(motivos)
        obs = f"{obs} || {marca}" if obs else marca

    lleg = models.Llegada(
        oc_numero=oc_numero,
        sin_oc=sin_oc,
        sospechosa=bool(motivos),
        proveedor_nit=proveedor_nit,
        proveedor_nombre=proveedor_nombre,
        usuario_id=payload.get("usuario_id"),
        observaciones=obs,
        bodega_destino=(payload.get("bodega_destino") or None),
        factura_numero=(payload.get("factura_numero") or None),
    )
    for it in items:
        lleg.items.append(models.LlegadaItem(
            articulo_codigo=it.get("articulo_codigo"),
            articulo_nombre=it.get("articulo_nombre"),
            cantidad_esperada=float(it.get("cantidad_esperada") or 0),
            cantidad_recibida=float(it.get("cantidad_recibida") or 0),
            unidad_reportada=it.get("unidad_reportada"),
            precio_total=float(it.get("precio_total") or 0),
        ))
    for f in fotos:
        if f.filename:
            lleg.fotos.append(models.LlegadaFoto(url=_save_photo(f)))
    db.add(lleg)
    db.commit()
    db.refresh(lleg)

    # si vino de un pre-llenado IA, enlazar la telemetría con lo confirmado
    prellenado_id = payload.get("prellenado_id")
    if prellenado_id:
        try:
            db.execute(text(
                "UPDATE analisis_agente SET llegada_id=:lid, "
                "contenido = contenido || :conf WHERE id=:pid"),
                {"lid": lleg.id, "pid": int(prellenado_id),
                 "conf": " || CONFIRMADO: " + json.dumps(
                     {"items": items, "bodega": payload.get("bodega_destino")},
                     default=str)})
            db.commit()
        except Exception:
            db.rollback()

    return {"id": lleg.id, "oc_numero": lleg.oc_numero, "sin_oc": lleg.sin_oc,
            "sospechosa": lleg.sospechosa,
            "proveedor_nombre": lleg.proveedor_nombre,
            "items": len(lleg.items), "fotos": len(lleg.fotos)}


@router.get("/")
def listar(limit: int = 30, db: Session = Depends(get_db)):
    llegs = (db.query(models.Llegada)
               .options(joinedload(models.Llegada.items),
                        joinedload(models.Llegada.fotos),
                        joinedload(models.Llegada.usuario))
               .order_by(models.Llegada.fecha_registro.desc())
               .limit(limit).all())
    return [{
        "id": l.id, "oc_numero": l.oc_numero, "sin_oc": l.sin_oc,
        "sospechosa": l.sospechosa,
        "proveedor_nombre": l.proveedor_nombre,
        "fecha": l.fecha_registro.isoformat() if l.fecha_registro else None,
        "usuario": l.usuario.nombre if l.usuario else None,
        "observaciones": l.observaciones,
        "fotos": [f.url for f in l.fotos],
        "items": [{
            "articulo_codigo": i.articulo_codigo,
            "articulo_nombre": i.articulo_nombre,
            "cantidad_esperada": i.cantidad_esperada,
            "cantidad_recibida": i.cantidad_recibida,
            "unidad_reportada": i.unidad_reportada,
            "precio_total": i.precio_total,
        } for i in l.items],
    } for l in llegs]
