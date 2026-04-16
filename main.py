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
