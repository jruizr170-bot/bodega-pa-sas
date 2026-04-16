from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Usuarios ──────────────────────────────────────────────────────────────────

class UsuarioOut(BaseModel):
    id: int
    nombre: str
    activo: bool

    model_config = {"from_attributes": True}


# ── Bodegas ───────────────────────────────────────────────────────────────────

class BodegaOut(BaseModel):
    id: int
    codigo: str
    nombre: str

    model_config = {"from_attributes": True}


# ── Proveedores ───────────────────────────────────────────────────────────────

class ProveedorOut(BaseModel):
    id: int
    nit: str
    nombre: str

    model_config = {"from_attributes": True}


# ── Productos ─────────────────────────────────────────────────────────────────

class ProductoOut(BaseModel):
    id: int
    descripcion: str
    unidad: str

    model_config = {"from_attributes": True}


# ── Items de recepción ────────────────────────────────────────────────────────

class ItemIn(BaseModel):
    descripcion: str
    cantidad: float
    unidad: str = "UND"
    precio_unit: float = 0.0
    total: float = 0.0
    producto_id: Optional[int] = None


class ItemOut(ItemIn):
    id: int
    recepcion_id: int

    model_config = {"from_attributes": True}


# ── Recepción ─────────────────────────────────────────────────────────────────

class RecepcionIn(BaseModel):
    fecha_factura: Optional[str] = None
    numero_factura: Optional[str] = None
    proveedor_id: Optional[int] = None
    proveedor_nombre: Optional[str] = None
    bodega_id: int
    usuario_id: Optional[int] = None
    usuario_nombre: Optional[str] = None   # texto libre — se busca o crea
    observaciones: Optional[str] = None
    total_factura: float = 0.0
    items: List[ItemIn] = []


class RecepcionOut(BaseModel):
    id: int
    fecha_registro: datetime
    fecha_factura: Optional[str]
    numero_factura: Optional[str]
    proveedor_id: Optional[int]
    proveedor_nombre: Optional[str]
    bodega_id: int
    usuario_id: Optional[int]
    observaciones: Optional[str]
    foto_path: Optional[str]
    total_factura: float
    items: List[ItemOut] = []

    # joins
    bodega: Optional[BodegaOut] = None
    usuario: Optional[UsuarioOut] = None
    proveedor: Optional[ProveedorOut] = None

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_recepciones: int
    recepciones_hoy: int
    recepciones_semana: int
    total_facturado: float
    recepciones_por_bodega: List[dict]
    ultimas_recepciones: List[RecepcionOut]
