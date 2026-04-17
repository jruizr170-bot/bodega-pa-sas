from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
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
