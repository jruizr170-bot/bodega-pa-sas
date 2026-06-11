"""Helper compartido para subir fotos (llegadas, despachos)."""
import os
import uuid
from datetime import date
from pathlib import Path

from fastapi import UploadFile

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")
UPLOADS_BASE   = Path(__file__).parent.parent / "uploads"


def _save_photo(file: UploadFile) -> str:
    """Sube foto a Cloudinary (si está configurado) o disco local. Devuelve URL."""
    raw = file.file.read()

    # Comprimir con Pillow si >1 MB
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        if max(img.size) > 2000:
            img.thumbnail((2000, 2000), Image.LANCZOS)
        buf = io.BytesIO()
        quality = 70 if len(raw) > 1_000_000 else 85
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        raw = buf.getvalue()
    except Exception:
        pass

    if CLOUDINARY_URL:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(cloudinary_url=CLOUDINARY_URL)
        result = cloudinary.uploader.upload(
            raw,
            folder="bodega-pa-sas",
            resource_type="image",
        )
        return result["secure_url"]

    # Fallback local
    today = date.today()
    d = UPLOADS_BASE / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
    d.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.jpg"
    (d / nombre).write_bytes(raw)
    return str((d / nombre).relative_to(UPLOADS_BASE.parent))
