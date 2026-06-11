"""Usuarios autorizados para registrar en la app (lista fija, ver main.auto_seed)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("")
def listar_usuarios(db: Session = Depends(get_db)):
    usuarios = (db.query(models.Usuario)
                  .filter(models.Usuario.activo.is_(True))
                  .order_by(models.Usuario.id).all())
    return [{"id": u.id, "nombre": u.nombre, "activo": u.activo} for u in usuarios]
