from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

import models, schemas
from database import get_db

router = APIRouter(tags=["catalogo"])


# ── Usuarios ──────────────────────────────────────────────────────────────────

@router.get("/usuarios", response_model=list[schemas.UsuarioOut])
def listar_usuarios(db: Session = Depends(get_db)):
    return db.query(models.Usuario).filter(models.Usuario.activo == True).all()


# ── Bodegas ───────────────────────────────────────────────────────────────────

@router.get("/bodegas", response_model=list[schemas.BodegaOut])
def listar_bodegas(db: Session = Depends(get_db)):
    return db.query(models.Bodega).filter(models.Bodega.activa == True).all()


# ── Proveedores (autocomplete) ────────────────────────────────────────────────

@router.get("/proveedores", response_model=list[schemas.ProveedorOut])
def buscar_proveedores(
    q: str = Query("", min_length=0),
    limit: int = 10,
    db: Session = Depends(get_db),
):
    query = db.query(models.Proveedor)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.Proveedor.nombre.ilike(like),
                models.Proveedor.nit.ilike(like),
            )
        )
    return query.order_by(models.Proveedor.nombre).limit(limit).all()


@router.post("/proveedores", response_model=schemas.ProveedorOut, status_code=201)
def crear_proveedor(payload: schemas.ProveedorOut, db: Session = Depends(get_db)):
    # Allow upsert by NIT
    existing = db.query(models.Proveedor).filter(
        models.Proveedor.nit == payload.nit
    ).first()
    if existing:
        existing.nombre = payload.nombre
        db.commit()
        db.refresh(existing)
        return existing
    prov = models.Proveedor(nit=payload.nit, nombre=payload.nombre)
    db.add(prov)
    db.commit()
    db.refresh(prov)
    return prov


# ── Productos (autocomplete) ──────────────────────────────────────────────────

@router.get("/productos", response_model=list[schemas.ProductoOut])
def buscar_productos(
    q: str = Query("", min_length=0),
    limit: int = 15,
    db: Session = Depends(get_db),
):
    query = db.query(models.Producto)
    if q.strip():
        query = query.filter(
            models.Producto.descripcion.ilike(f"%{q.strip()}%")
        )
    return query.order_by(models.Producto.descripcion).limit(limit).all()
