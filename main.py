from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import models
from database import engine
from routes.recepciones import router as rec_router
from routes.catalogo import router as cat_router

# Crear tablas
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Recepciones Bodega - PA SAS", version="1.0.0")


@app.on_event("startup")
def auto_seed():
    """Carga datos iniciales si la BD está vacía."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(models.Bodega).count() > 0:
            return  # ya tiene datos

        BODEGAS = [("01","Principal"),("02","Tentadero"),("13","Arrullos"),("15","PAE Meta")]
        for codigo, nombre in BODEGAS:
            db.add(models.Bodega(codigo=codigo, nombre=nombre))

        USUARIOS = ["Almacenista Principal","Almacenista Tentadero",
                    "Almacenista Arrullos","Almacenista PAE Meta","Supervisor Bodega"]
        for nombre in USUARIOS:
            db.add(models.Usuario(nombre=nombre))

        PROVEEDORES = [
            ("860001477","CARULLA VIVERO SA"),("860030937","EXITO SA"),
            ("890903790","ALMACENES LA 14 SA"),("800171752","MAKRO SUPERMAYORISTA SA"),
            ("830002397","ALIMENTOS POLAR COLOMBIA SAS"),
        ]
        for nit, nombre in PROVEEDORES:
            db.add(models.Proveedor(nit=nit, nombre=nombre))

        PRODUCTOS = [
            ("Arroz blanco","KG"),("Aceite vegetal","LT"),("Azucar blanca","KG"),
            ("Sal refinada","KG"),("Frijol rojo","KG"),("Lenteja","KG"),
            ("Pasta de trigo","KG"),("Harina de trigo","KG"),("Leche entera UHT","LT"),
            ("Pollo entero","KG"),("Carne molida","KG"),("Huevo AA","UND"),
            ("Pan tajado","UND"),("Atun en lata","UND"),("Detergente","KG"),
        ]
        for desc, unidad in PRODUCTOS:
            db.add(models.Producto(descripcion=desc, unidad=unidad))

        db.commit()
    finally:
        db.close()

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(rec_router, prefix="/api")
app.include_router(cat_router, prefix="/api")

# ── Static files ──────────────────────────────────────────────────────────────
STATIC = Path(__file__).parent / "static"
STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# Servir uploads (fotos)
UPLOADS = Path(__file__).parent / "uploads"
UPLOADS.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")


# ── Páginas ───────────────────────────────────────────────────────────────────
FRONTEND = Path(__file__).parent / "frontend"

@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(FRONTEND / "index.html")

@app.get("/dashboard", response_class=FileResponse)
def dashboard():
    return FileResponse(FRONTEND / "dashboard.html")
