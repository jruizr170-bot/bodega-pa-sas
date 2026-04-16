"""
seed.py - Carga datos iniciales en la base de datos.
Ejecutar una sola vez: python seed.py
"""
import sys
import os

# Asegurar que los módulos locales se encuentren
sys.path.insert(0, os.path.dirname(__file__))

import models
from database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)
db = SessionLocal()

# ── Bodegas (de config.py) ────────────────────────────────────────────────────
BODEGAS = [
    ("01", "Principal"),
    ("02", "Tentadero"),
    ("13", "Arrullos"),
    ("15", "PAE Meta"),
]
for codigo, nombre in BODEGAS:
    if not db.query(models.Bodega).filter_by(codigo=codigo).first():
        db.add(models.Bodega(codigo=codigo, nombre=nombre))
        print(f"  + Bodega {codigo} - {nombre}")

# ── Usuarios ──────────────────────────────────────────────────────────────────
USUARIOS = [
    "Almacenista Principal",
    "Almacenista Tentadero",
    "Almacenista Arrullos",
    "Almacenista PAE Meta",
    "Supervisor Bodega",
]
for nombre in USUARIOS:
    if not db.query(models.Usuario).filter_by(nombre=nombre).first():
        db.add(models.Usuario(nombre=nombre))
        print(f"  + Usuario: {nombre}")

# ── Proveedores iniciales (muestra) ──────────────────────────────────────────
PROVEEDORES = [
    ("860001477", "CARULLA VIVERO SA"),
    ("860030937", "EXITO SA"),
    ("890903790", "ALMACENES LA 14 SA"),
    ("800171752", "MAKRO SUPERMAYORISTA SA"),
    ("830002397", "ALIMENTOS POLAR COLOMBIA SAS"),
    ("900000000", "PROVEEDOR GENERICO"),
]
for nit, nombre in PROVEEDORES:
    if not db.query(models.Proveedor).filter_by(nit=nit).first():
        db.add(models.Proveedor(nit=nit, nombre=nombre))
        print(f"  + Proveedor: {nombre}")

# ── Productos iniciales ───────────────────────────────────────────────────────
PRODUCTOS = [
    ("Arroz blanco", "KG"),
    ("Aceite vegetal", "LT"),
    ("Azúcar blanca", "KG"),
    ("Sal refinada", "KG"),
    ("Frijol rojo", "KG"),
    ("Lenteja", "KG"),
    ("Pasta de trigo", "KG"),
    ("Harina de trigo", "KG"),
    ("Leche entera UHT", "LT"),
    ("Pollo entero", "KG"),
    ("Carne molida", "KG"),
    ("Huevo AA", "UND"),
    ("Pan tajado", "UND"),
    ("Atún en lata", "UND"),
    ("Detergente", "KG"),
]
for desc, unidad in PRODUCTOS:
    if not db.query(models.Producto).filter_by(descripcion=desc).first():
        db.add(models.Producto(descripcion=desc, unidad=unidad))
        print(f"  + Producto: {desc}")

db.commit()
db.close()
print("\nSeed completado.")
