from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import models
from database import engine
from routes.recepciones import router as rec_router
from routes.catalogo import router as cat_router
from routes.matching import router as match_router
from routes.llegadas import router as lleg_router
from routes.operaciones import router as oper_router
from routes.panel import router as panel_router

# Crear tablas + migraciones suaves (columnas nuevas sobre tablas existentes)
models.Base.metadata.create_all(bind=engine)
if engine.dialect.name == "postgresql":
    from sqlalchemy import text as _text
    with engine.begin() as _c:
        _c.execute(_text(
            "ALTER TABLE llegadas "
            "ADD COLUMN IF NOT EXISTS sin_oc boolean DEFAULT false, "
            "ADD COLUMN IF NOT EXISTS sospechosa boolean DEFAULT false"))
        _c.execute(_text("ALTER TABLE llegadas ALTER COLUMN oc_numero DROP NOT NULL"))
        _c.execute(_text(
            "ALTER TABLE llegada_items "
            "ADD COLUMN IF NOT EXISTS unidad_reportada varchar(15)"))

app = FastAPI(title="Bodega PA SAS", version="2.1.0")

VERSION = "2.1"

# Las únicas personas autorizadas para registrar en la app
USUARIOS_AUTORIZADOS = ["CESAR SAENS", "BREINER", "DANIEL LOZANO",
                        "YORLEISON MAZO", "JERONIMO RUIZ"]


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.on_event("startup")
def auto_seed():
    """Asegura los 5 usuarios autorizados y desactiva el resto."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        existentes = db.query(models.Usuario).all()
        por_primer_nombre = {u.nombre.strip().upper().split()[0]: u
                             for u in existentes if u.nombre and u.nombre.strip()}
        autorizados_ids = set()
        for nombre in USUARIOS_AUTORIZADOS:
            primer = nombre.split()[0]
            u = por_primer_nombre.get(primer)
            if u:
                u.nombre = nombre   # normalizar al nombre oficial
                u.activo = True
            else:
                u = models.Usuario(nombre=nombre, activo=True)
                db.add(u)
                db.flush()
            autorizados_ids.add(u.id)
        for u in existentes:
            if u.id not in autorizados_ids:
                u.activo = False
        db.commit()
    finally:
        db.close()

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(rec_router, prefix="/api")
app.include_router(cat_router, prefix="/api")
app.include_router(match_router)
app.include_router(lleg_router, prefix="/api")
app.include_router(oper_router, prefix="/api")
app.include_router(panel_router, prefix="/api")

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
