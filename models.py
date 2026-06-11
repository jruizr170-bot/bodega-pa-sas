from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id       = Column(Integer, primary_key=True, index=True)
    nombre   = Column(String(100), nullable=False)
    activo   = Column(Boolean, default=True)

    recepciones = relationship("Recepcion", back_populates="usuario")


class Bodega(Base):
    __tablename__ = "bodegas"

    id       = Column(Integer, primary_key=True, index=True)
    codigo   = Column(String(10), unique=True, nullable=False)
    nombre   = Column(String(100), nullable=False)
    activa   = Column(Boolean, default=True)

    recepciones = relationship("Recepcion", back_populates="bodega")


class Proveedor(Base):
    __tablename__ = "proveedores"

    id     = Column(Integer, primary_key=True, index=True)
    nit    = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(200), nullable=False)

    recepciones = relationship("Recepcion", back_populates="proveedor")


class Producto(Base):
    __tablename__ = "productos"

    id          = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String(300), nullable=False)
    unidad      = Column(String(30), default="UND")

    items = relationship("RecepcionItem", back_populates="producto")


class Recepcion(Base):
    __tablename__ = "recepciones"

    id                 = Column(Integer, primary_key=True, index=True)
    fecha_registro     = Column(DateTime, default=datetime.utcnow)
    fecha_factura      = Column(String(20), nullable=True)
    numero_factura     = Column(String(50), nullable=True)
    proveedor_id       = Column(Integer, ForeignKey("proveedores.id"), nullable=True)
    proveedor_nombre   = Column(String(200), nullable=True)
    bodega_id          = Column(Integer, ForeignKey("bodegas.id"), nullable=False)
    usuario_id         = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observaciones      = Column(Text, nullable=True)
    foto_path          = Column(String(500), nullable=True)   # legacy, mantener
    total_factura      = Column(Float, default=0.0)

    usuario   = relationship("Usuario", back_populates="recepciones")
    bodega    = relationship("Bodega", back_populates="recepciones")
    proveedor = relationship("Proveedor", back_populates="recepciones")
    items     = relationship("RecepcionItem", back_populates="recepcion",
                             cascade="all, delete-orphan")
    fotos     = relationship("RecepcionFoto", back_populates="recepcion",
                             cascade="all, delete-orphan")


class RecepcionFoto(Base):
    __tablename__ = "recepcion_fotos"

    id           = Column(Integer, primary_key=True, index=True)
    recepcion_id = Column(Integer, ForeignKey("recepciones.id"), nullable=False)
    url          = Column(String(1000), nullable=False)
    fecha_subida = Column(DateTime, default=datetime.utcnow)

    recepcion = relationship("Recepcion", back_populates="fotos")


class RecepcionItem(Base):
    __tablename__ = "recepcion_items"

    id           = Column(Integer, primary_key=True, index=True)
    recepcion_id = Column(Integer, ForeignKey("recepciones.id"), nullable=False)
    producto_id  = Column(Integer, ForeignKey("productos.id"), nullable=True)
    descripcion  = Column(String(300), nullable=False)
    cantidad     = Column(Float, nullable=False)
    unidad       = Column(String(30), default="UND")
    precio_unit  = Column(Float, default=0.0)
    total        = Column(Float, default=0.0)

    recepcion = relationship("Recepcion", back_populates="items")
    producto  = relationship("Producto", back_populates="items")


# ════════════════════════════════════════════════════════════════════════════
# App v2 (2026-06): la operación real de bodega
#   BODEGA      → Llegada: confirma la llegada física de una OC de Zeus
#   OPERACIONES → Armado: paquetes armados por programa
#                 Despacho: ruta del carro con varios municipios/programas
# Las tablas de recepciones de arriba se conservan solo como histórico.
# ════════════════════════════════════════════════════════════════════════════

class Llegada(Base):
    """Llegada física de mercancía, amarrada a una OC de Zeus (cero texto libre).
    sin_oc=True: llegada de URGENCIA (pedido sin OC montada en Zeus todavía)."""
    __tablename__ = "llegadas"

    id               = Column(Integer, primary_key=True, index=True)
    oc_numero        = Column(String(20), nullable=True, index=True)  # null en urgencias
    sin_oc           = Column(Boolean, default=False)
    sospechosa       = Column(Boolean, default=False)  # cantidades fuera de rango
    proveedor_nit    = Column(String(25))
    proveedor_nombre = Column(String(200))
    fecha_registro   = Column(DateTime, default=datetime.utcnow)
    usuario_id       = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observaciones    = Column(Text, nullable=True)

    usuario = relationship("Usuario")
    items   = relationship("LlegadaItem", back_populates="llegada",
                           cascade="all, delete-orphan")
    fotos   = relationship("LlegadaFoto", back_populates="llegada",
                           cascade="all, delete-orphan")


class LlegadaItem(Base):
    __tablename__ = "llegada_items"

    id                = Column(Integer, primary_key=True, index=True)
    llegada_id        = Column(Integer, ForeignKey("llegadas.id"), nullable=False)
    articulo_codigo   = Column(String(20))
    articulo_nombre   = Column(String(300))
    cantidad_esperada = Column(Float, default=0.0)   # faltante de la OC al momento
    cantidad_recibida = Column(Float, default=0.0)
    unidad_reportada  = Column(String(15), nullable=True)  # ej. "unidades" si difiere de la OC

    llegada = relationship("Llegada", back_populates="items")


class LlegadaFoto(Base):
    __tablename__ = "llegada_fotos"

    id           = Column(Integer, primary_key=True, index=True)
    llegada_id   = Column(Integer, ForeignKey("llegadas.id"), nullable=False)
    url          = Column(String(1000), nullable=False)
    fecha_subida = Column(DateTime, default=datetime.utcnow)

    llegada = relationship("Llegada", back_populates="fotos")


class Armado(Base):
    """Paquetes armados por operaciones (descuenta inventario teórico)."""
    __tablename__ = "armados"

    id            = Column(Integer, primary_key=True, index=True)
    fecha         = Column(DateTime, default=datetime.utcnow)
    programa      = Column(String(20), nullable=False)        # ARRULLOS / AIPI
    tipo_paquete  = Column(String(40), nullable=True)         # tipos AIPI; null en Arrullos
    paquetes      = Column(Integer, nullable=False)
    usuario_id    = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observaciones = Column(Text, nullable=True)

    usuario = relationship("Usuario")


class Despacho(Base):
    """Salida de ruta: un carro puede llevar varios municipios y programas."""
    __tablename__ = "despachos"

    id             = Column(Integer, primary_key=True, index=True)
    fecha          = Column(DateTime, default=datetime.utcnow)
    vehiculo_placa = Column(String(10), nullable=False)
    vehiculo_tipo  = Column(String(30), nullable=True)
    conductor      = Column(String(100), nullable=True)
    operario       = Column(String(100), nullable=True)   # acompañante de la empresa
    hora_salida    = Column(String(10), nullable=True)    # HH:MM
    hora_regreso   = Column(String(10), nullable=True)
    usuario_id     = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    observaciones  = Column(Text, nullable=True)
    foto_url       = Column(String(1000), nullable=True)  # carro cargado / acta

    usuario  = relationship("Usuario")
    destinos = relationship("DespachoDestino", back_populates="despacho",
                            cascade="all, delete-orphan")


class DespachoDestino(Base):
    __tablename__ = "despacho_destinos"

    id           = Column(Integer, primary_key=True, index=True)
    despacho_id  = Column(Integer, ForeignKey("despachos.id"), nullable=False)
    municipio    = Column(String(100), nullable=False)
    programa     = Column(String(20), nullable=False)     # ARRULLOS / AIPI
    tipo_paquete = Column(String(40), nullable=True)
    paquetes     = Column(Integer, default=0)
    complementos = Column(Integer, default=0)             # AIPI
    hora_entrega = Column(String(10), nullable=True)      # se llena al confirmar
    recibido_por = Column(String(150), nullable=True)
    novedades    = Column(Text, nullable=True)            # dañados, devoluciones, etc.

    despacho = relationship("Despacho", back_populates="destinos")


class ArticuloZeus(Base):
    """Mapeo de solo lectura al maestro de artículos sincronizado desde Zeus."""
    __tablename__ = "articulos_zeus"
    __table_args__ = {"extend_existing": True}

    codigo        = Column(String(20), primary_key=True)
    nombre        = Column(String(300))
    grupo         = Column(String(100))
    presentacion  = Column(String(100))
    deshabilitado = Column(Boolean)


class OrdenCompraZeus(Base):
    """Mapeo de solo lectura a la tabla que sincroniza oc_sync desde Zeus."""
    __tablename__ = "ordenes_compra"
    __table_args__ = {"extend_existing": True}

    id               = Column(Integer, primary_key=True)
    orden_numero     = Column(String, index=True)
    proveedor_nit    = Column(String)
    proveedor_nombre = Column(String)
    fecha_documento  = Column(Date)
    fecha_entrega    = Column(Date)
    estado           = Column(String)

    items = relationship("OrdenCompraZeusItem", back_populates="orden")


class OrdenCompraZeusItem(Base):
    __tablename__ = "ordenes_compra_items"
    __table_args__ = {"extend_existing": True}

    id              = Column(Integer, primary_key=True)
    orden_id        = Column(Integer, ForeignKey("ordenes_compra.id"))
    articulo_codigo = Column(String)
    articulo_nombre = Column(String)
    bodega_codigo   = Column(String)
    cantidad        = Column(Float)
    satisfechas     = Column(Float)
    faltante        = Column(Float)
    valor_unitario  = Column(Float)
    costo_total     = Column(Float)

    orden = relationship("OrdenCompraZeus", back_populates="items")
