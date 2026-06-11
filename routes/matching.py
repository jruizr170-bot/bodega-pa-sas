"""
matching.py — Endpoints para consultar resultados del motor M3-A.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal

router = APIRouter(prefix="/api/matching", tags=["matching"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _match_model(db: Session):
    """Importa MatchResultado en tiempo de ejecución (tabla puede no existir aún)."""
    try:
        from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, Enum
        from sqlalchemy.ext.declarative import declarative_base
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(db.bind)
        if "match_resultados" not in inspector.get_table_names():
            return None

        # Usar raw SQL para no depender de la instalación de m3_matching
        return True
    except Exception:
        return None


@router.get("/resumen")
def resumen_matching(db: Session = Depends(get_db)):
    """Contadores por estado."""
    from sqlalchemy import text
    try:
        rows = db.execute(
            text("SELECT estado, COUNT(*) as cnt FROM match_resultados GROUP BY estado ORDER BY cnt DESC")
        ).fetchall()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Tabla match_resultados no disponible: {e}")


@router.get("/problemas")
def listar_problemas(
    limit: int = 50,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lista casos que requieren revisión (AMARILLO, ROJO, HUERFANO_*)."""
    from sqlalchemy import text

    estados_problema = "('AMARILLO','ROJO','HUERFANO_OC','HUERFANO_FACTURA','HUERFANO_RECEPCION')"
    filtro_estado = f"AND estado = '{estado}'" if estado else f"AND estado IN {estados_problema}"

    sql = text(f"""
        SELECT id, estado, proveedor_nit, proveedor_nombre,
               factura_id, recepcion_id, orden_compra_id,
               tipo_diferencia, monto_diferencia, porcentaje_diferencia,
               detalle, resuelto, fecha_creacion
        FROM match_resultados
        WHERE resuelto = false {filtro_estado}
        ORDER BY
            CASE estado
                WHEN 'ROJO' THEN 1
                WHEN 'HUERFANO_FACTURA' THEN 2
                WHEN 'AMARILLO' THEN 3
                WHEN 'HUERFANO_OC' THEN 4
                WHEN 'HUERFANO_RECEPCION' THEN 5
                ELSE 6
            END,
            monto_diferencia DESC NULLS LAST
        LIMIT :limit
    """)
    try:
        rows = db.execute(sql, {"limit": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/resolver/{match_id}")
def marcar_resuelto(match_id: int, usuario: str, db: Session = Depends(get_db)):
    """Marca un match como resuelto manualmente."""
    from sqlalchemy import text
    result = db.execute(
        text("""
            UPDATE match_resultados
            SET resuelto = true, resuelto_por = :usuario, resuelto_at = :ts
            WHERE id = :id
        """),
        {"id": match_id, "usuario": usuario, "ts": datetime.utcnow()},
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Match no encontrado")
    return {"ok": True, "id": match_id}


@router.get("/detalle/{match_id}")
def detalle_match(match_id: int, db: Session = Depends(get_db)):
    """Retorna un match con sus ítems cruzados."""
    from sqlalchemy import text
    try:
        match_row = db.execute(
            text("SELECT * FROM match_resultados WHERE id = :id"),
            {"id": match_id},
        ).fetchone()
        if not match_row:
            raise HTTPException(status_code=404, detail="Match no encontrado")

        items = db.execute(
            text("SELECT * FROM match_items WHERE match_resultado_id = :id"),
            {"id": match_id},
        ).fetchall()

        return {
            "match":  dict(match_row._mapping),
            "items": [dict(r._mapping) for r in items],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
