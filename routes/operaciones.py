"""OPERACIONES — Armado de paquetes y despachos de ruta.

- Armado: cuántos paquetes se armaron, por programa (y tipo en AIPI).
- Despacho: el carro sale con varios municipios (y hasta varios programas);
  luego se confirma la entrega de cada destino.
Los municipios se eligen de los pedidos activos (pedidos/*.json del proyecto),
no se digitan libres.
"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from routes.recepciones import _save_photo

router = APIRouter(prefix="/operaciones", tags=["operaciones"])

PROGRAMAS = ["ARRULLOS", "AIPI"]
TIPOS_AIPI = ["gestantes_lactantes", "ninos_6m_1ano", "mayores_1_ano",
              "complemento_gestantes", "complemento_ninos"]
PEDIDOS_DIR = Path(__file__).parent.parent.parent / "pedidos"


# ── Schemas ───────────────────────────────────────────────────────────────────

class ArmadoIn(BaseModel):
    programa: str
    tipo_paquete: Optional[str] = None
    paquetes: int
    usuario_id: Optional[int] = None
    observaciones: Optional[str] = None


class DestinoIn(BaseModel):
    municipio: str
    programa: str
    tipo_paquete: Optional[str] = None
    paquetes: int = 0
    complementos: int = 0


class DespachoIn(BaseModel):
    vehiculo_placa: str
    vehiculo_tipo: Optional[str] = None
    conductor: Optional[str] = None
    operario: Optional[str] = None
    hora_salida: Optional[str] = None
    usuario_id: Optional[int] = None
    observaciones: Optional[str] = None
    destinos: list[DestinoIn]


class EntregaIn(BaseModel):
    hora_entrega: Optional[str] = None
    recibido_por: Optional[str] = None
    novedades: Optional[str] = None


class RegresoIn(BaseModel):
    hora_regreso: Optional[str] = None
    observaciones: Optional[str] = None


# ── Catálogos para el frontend ────────────────────────────────────────────────

@router.get("/catalogo")
def catalogo():
    """Programas, tipos AIPI y municipios de los pedidos activos."""
    municipios: dict[str, list] = {p: [] for p in PROGRAMAS}
    if PEDIDOS_DIR.exists():
        for ruta in sorted(PEDIDOS_DIR.glob("pedido_*.json")):
            try:
                p = json.loads(ruta.read_text(encoding="utf-8"))
            except Exception:
                continue
            if p.get("estado", "pendiente") != "pendiente":
                continue
            prog = p.get("programa", "")
            if prog in municipios:
                municipios[prog] = [m["municipio"] for m in p.get("municipios", [])]
    if not any(municipios.values()):  # en Render no existe pedidos/ -> fallback
        fallback = Path(__file__).parent.parent / "data" / "municipios.json"
        if fallback.exists():
            data = json.loads(fallback.read_text(encoding="utf-8"))
            for prog in PROGRAMAS:
                municipios[prog] = data.get(prog, [])
    return {"programas": PROGRAMAS, "tipos_aipi": TIPOS_AIPI,
            "municipios": municipios}


# ── Armados ───────────────────────────────────────────────────────────────────

@router.post("/armados", status_code=201)
def crear_armado(payload: ArmadoIn, db: Session = Depends(get_db)):
    if payload.programa not in PROGRAMAS:
        raise HTTPException(422, f"Programa invalido: {payload.programa}")
    a = models.Armado(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "programa": a.programa, "paquetes": a.paquetes}


@router.get("/armados")
def listar_armados(limit: int = 50, db: Session = Depends(get_db)):
    arms = (db.query(models.Armado)
              .options(joinedload(models.Armado.usuario))
              .order_by(models.Armado.fecha.desc()).limit(limit).all())
    return [{
        "id": a.id, "fecha": a.fecha.isoformat() if a.fecha else None,
        "programa": a.programa, "tipo_paquete": a.tipo_paquete,
        "paquetes": a.paquetes,
        "usuario": a.usuario.nombre if a.usuario else None,
        "observaciones": a.observaciones,
    } for a in arms]


# ── Despachos ─────────────────────────────────────────────────────────────────

def _despacho_out(d: models.Despacho) -> dict:
    return {
        "id": d.id, "fecha": d.fecha.isoformat() if d.fecha else None,
        "vehiculo_placa": d.vehiculo_placa, "vehiculo_tipo": d.vehiculo_tipo,
        "conductor": d.conductor, "operario": d.operario,
        "hora_salida": d.hora_salida, "hora_regreso": d.hora_regreso,
        "usuario": d.usuario.nombre if d.usuario else None,
        "observaciones": d.observaciones, "foto_url": d.foto_url,
        "destinos": [{
            "id": x.id, "municipio": x.municipio, "programa": x.programa,
            "tipo_paquete": x.tipo_paquete, "paquetes": x.paquetes,
            "complementos": x.complementos, "hora_entrega": x.hora_entrega,
            "recibido_por": x.recibido_por, "novedades": x.novedades,
            "entregado": x.hora_entrega is not None,
        } for x in d.destinos],
    }


@router.post("/despachos", status_code=201)
def crear_despacho(payload: DespachoIn, db: Session = Depends(get_db)):
    if not payload.destinos:
        raise HTTPException(422, "El despacho debe tener al menos un destino")
    d = models.Despacho(
        vehiculo_placa=payload.vehiculo_placa.strip().upper(),
        vehiculo_tipo=payload.vehiculo_tipo,
        conductor=payload.conductor,
        operario=payload.operario,
        hora_salida=payload.hora_salida,
        usuario_id=payload.usuario_id,
        observaciones=payload.observaciones,
    )
    for dest in payload.destinos:
        if dest.programa not in PROGRAMAS:
            raise HTTPException(422, f"Programa invalido: {dest.programa}")
        d.destinos.append(models.DespachoDestino(**dest.model_dump()))
    db.add(d)
    db.commit()
    db.refresh(d)
    return _despacho_out(d)


@router.get("/despachos")
def listar_despachos(limit: int = 30, pendientes: bool = False,
                     db: Session = Depends(get_db)):
    q = (db.query(models.Despacho)
           .options(joinedload(models.Despacho.destinos),
                    joinedload(models.Despacho.usuario))
           .order_by(models.Despacho.fecha.desc()))
    desps = q.limit(limit).all()
    if pendientes:  # solo despachos con destinos sin confirmar entrega
        desps = [d for d in desps
                 if any(x.hora_entrega is None for x in d.destinos)]
    return [_despacho_out(d) for d in desps]


@router.patch("/despachos/{despacho_id}/destinos/{destino_id}")
def confirmar_entrega(despacho_id: int, destino_id: int, payload: EntregaIn,
                      db: Session = Depends(get_db)):
    dest = (db.query(models.DespachoDestino)
              .filter_by(id=destino_id, despacho_id=despacho_id).first())
    if not dest:
        raise HTTPException(404, "Destino no encontrado")
    dest.hora_entrega = payload.hora_entrega or dest.hora_entrega
    dest.recibido_por = payload.recibido_por or dest.recibido_por
    dest.novedades = payload.novedades or dest.novedades
    db.commit()
    return {"id": dest.id, "municipio": dest.municipio,
            "hora_entrega": dest.hora_entrega, "recibido_por": dest.recibido_por}


@router.patch("/despachos/{despacho_id}")
def cerrar_despacho(despacho_id: int, payload: RegresoIn,
                    db: Session = Depends(get_db)):
    d = db.query(models.Despacho).filter_by(id=despacho_id).first()
    if not d:
        raise HTTPException(404, "Despacho no encontrado")
    if payload.hora_regreso:
        d.hora_regreso = payload.hora_regreso
    if payload.observaciones:
        d.observaciones = ((d.observaciones + " | ") if d.observaciones else "") \
                          + payload.observaciones
    db.commit()
    return {"id": d.id, "hora_regreso": d.hora_regreso}


@router.post("/despachos/{despacho_id}/foto")
def foto_despacho(despacho_id: int, foto: UploadFile = File(...),
                  db: Session = Depends(get_db)):
    d = db.query(models.Despacho).filter_by(id=despacho_id).first()
    if not d:
        raise HTTPException(404, "Despacho no encontrado")
    d.foto_url = _save_photo(foto)
    db.commit()
    return {"id": d.id, "foto_url": d.foto_url}
