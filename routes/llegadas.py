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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from routes.recepciones import _save_photo

router = APIRouter(prefix="/llegadas", tags=["llegadas"])

ESTADOS_ABIERTOS = ["PENDIENTE", "PARCIAL", "ATRASADA"]
FACTOR_SOSPECHA = 1.5        # recibido > 1.5x lo esperado
UND_GIGANTE = 100_000        # "unidades" con número absurdo


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

def _validar_sospecha(items: list[dict]) -> list[str]:
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

    motivos = _validar_sospecha(items)
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
    )
    for it in items:
        lleg.items.append(models.LlegadaItem(
            articulo_codigo=it.get("articulo_codigo"),
            articulo_nombre=it.get("articulo_nombre"),
            cantidad_esperada=float(it.get("cantidad_esperada") or 0),
            cantidad_recibida=float(it.get("cantidad_recibida") or 0),
            unidad_reportada=it.get("unidad_reportada"),
        ))
    for f in fotos:
        if f.filename:
            lleg.fotos.append(models.LlegadaFoto(url=_save_photo(f)))
    db.add(lleg)
    db.commit()
    db.refresh(lleg)
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
        } for i in l.items],
    } for l in llegs]
