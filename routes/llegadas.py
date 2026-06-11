"""BODEGA — Llegada física de mercancía, guiada por las OCs abiertas de Zeus.

Las OCs se leen de las tablas ordenes_compra/_items de Neon, que oc_sync
sincroniza desde Zeus cada 30 minutos. El bodeguero no digita nombres:
elige la OC y confirma cantidades.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from routes.recepciones import _save_photo

router = APIRouter(prefix="/llegadas", tags=["llegadas"])

ESTADOS_ABIERTOS = ["PENDIENTE", "PARCIAL", "ATRASADA"]


# ── Schemas ───────────────────────────────────────────────────────────────────

class LlegadaItemIn(BaseModel):
    articulo_codigo: str
    articulo_nombre: str
    cantidad_esperada: float = 0
    cantidad_recibida: float = 0


class LlegadaIn(BaseModel):
    oc_numero: str
    usuario_id: Optional[int] = None
    observaciones: Optional[str] = None
    items: list[LlegadaItemIn]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/ocs-abiertas")
def ocs_abiertas(db: Session = Depends(get_db)):
    """OCs abiertas en Zeus (sincronizadas a Neon) para confirmar llegada."""
    ocs = (db.query(models.OrdenCompraZeus)
             .options(joinedload(models.OrdenCompraZeus.items))
             .filter(models.OrdenCompraZeus.estado.in_(ESTADOS_ABIERTOS))
             .order_by(models.OrdenCompraZeus.fecha_entrega)
             .all())
    hoy = datetime.utcnow().date()
    out = []
    for oc in ocs:
        entrega = oc.fecha_entrega
        if hasattr(entrega, "date"):   # datetime -> date (la columna real es Date)
            entrega = entrega.date()
        pendientes = [i for i in oc.items if (i.faltante or 0) > 0]
        # Si Zeus ya no reporta faltantes pero la OC sigue abierta, mostrar
        # todos los items con la cantidad original como esperado.
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


@router.post("/", status_code=201)
def crear(payload: LlegadaIn, db: Session = Depends(get_db)):
    oc = (db.query(models.OrdenCompraZeus)
            .filter_by(orden_numero=payload.oc_numero).first())
    lleg = models.Llegada(
        oc_numero=payload.oc_numero,
        proveedor_nit=oc.proveedor_nit if oc else None,
        proveedor_nombre=oc.proveedor_nombre if oc else None,
        usuario_id=payload.usuario_id,
        observaciones=payload.observaciones,
    )
    for it in payload.items:
        lleg.items.append(models.LlegadaItem(**it.model_dump()))
    db.add(lleg)
    db.commit()
    db.refresh(lleg)
    return {"id": lleg.id, "oc_numero": lleg.oc_numero,
            "proveedor_nombre": lleg.proveedor_nombre,
            "items": len(lleg.items)}


@router.post("/{llegada_id}/foto")
def subir_foto(llegada_id: int, foto: UploadFile = File(...),
               db: Session = Depends(get_db)):
    lleg = db.query(models.Llegada).filter_by(id=llegada_id).first()
    if not lleg:
        raise HTTPException(404, "Llegada no encontrada")
    url = _save_photo(foto)
    db.add(models.LlegadaFoto(llegada_id=llegada_id, url=url))
    db.commit()
    return {"id": llegada_id, "url": url}


@router.get("/")
def listar(limit: int = 30, db: Session = Depends(get_db)):
    llegs = (db.query(models.Llegada)
               .options(joinedload(models.Llegada.items),
                        joinedload(models.Llegada.fotos),
                        joinedload(models.Llegada.usuario))
               .order_by(models.Llegada.fecha_registro.desc())
               .limit(limit).all())
    return [{
        "id": l.id, "oc_numero": l.oc_numero,
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
        } for i in l.items],
    } for l in llegs]
