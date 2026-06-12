"""Matching de lo extraído de la factura contra los catálogos Zeus en Neon.

- Proveedor por NIT normalizado (fallback fuzzy por nombre).
- Artículos con rapidfuzz sobre el catálogo en memoria + señales:
  +20 si el artículo está en la OC, +15 si el proveedor ya lo ha facturado (costos_zeus).
- Conversión a unidad base usando articulos_zeus.presentacion (GR/ML/UND)
  y contenido_por_unidad para empaques (bulto/caja/saco).
"""
import re
import time
import unicodedata
from typing import List, Optional

from sqlalchemy import text

# ── umbrales (calibrables con el backtest) ──
SCORE_ALTA = 92
SCORE_MEDIA = 78
FUZZY_MINIMO_PARA_ALTA = 70   # un boost nunca vuelve "alta" un fuzzy pobre
BOOST_OC = 20
BOOST_HISTORIAL_PROVEEDOR = 15
DESVIO_PRECIO_ADVERTIR = 0.20  # mismo umbral que llegadas.py

_CACHE_CATALOGO = {"ts": 0.0, "filas": []}
CACHE_TTL_S = 600

STOPWORDS = {"DE", "LA", "EL", "DEL", "LOS", "LAS", "X", "POR", "CON", "Y", "EN", "A", "PARA"}


def normalizar_nit(nit) -> str:
    """901.955.925-4 → 901955925 (copiada de m3_matching/app/rules.py)."""
    if not nit:
        return ""
    n = re.sub(r"[.,\s]", "", str(nit))
    n = re.sub(r"-\d$", "", n)
    n = re.sub(r"[^0-9]", "", n)
    return n


def normalizar_texto(s) -> str:
    if not s:
        return ""
    s = str(s).upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    palabras = [p for p in s.split() if p not in STOPWORDS]
    return " ".join(palabras)


# tamaños, unidades y empaques: ruido para IDENTIFICAR el artículo
# (el catálogo Zeus casi nunca los trae en el nombre: "ATUN X GR", "CACAO")
_TOKENS_RUIDO = {"G", "GR", "GRS", "GRAMOS", "KG", "KILO", "KILOS", "ML", "L", "LT",
                 "LTS", "LITRO", "LITROS", "LB", "LIBRA", "LIBRAS", "UND", "UNDS",
                 "UNIDAD", "UNIDADES", "PAQ", "PAQUETE", "PAQUETES", "CAJA", "CAJAS",
                 "BULTO", "BULTOS", "SACO", "SACOS", "PACA", "PACAS", "BOLSA",
                 "BOLSAS", "LATA", "LATAS", "FRASCO", "TARRO", "BANDEJA", "DOCENA"}
_RE_TAMANO = re.compile(r"^\d+([.,]\d+)?[A-Z]{0,3}$")  # 250, 250G, 1.5KG, 12


def normalizar_para_match(s) -> str:
    """Normaliza dejando solo los tokens que identifican el producto."""
    tokens = normalizar_texto(s).split()
    utiles = [t for t in tokens if t not in _TOKENS_RUIDO and not _RE_TAMANO.match(t)]
    return " ".join(utiles) if utiles else " ".join(tokens)


def cargar_catalogo(db) -> List[dict]:
    """Catálogo de artículos Zeus en memoria (cache 10 min)."""
    ahora = time.time()
    if _CACHE_CATALOGO["filas"] and ahora - _CACHE_CATALOGO["ts"] < CACHE_TTL_S:
        return _CACHE_CATALOGO["filas"]
    filas = db.execute(text(
        "SELECT codigo, nombre, presentacion FROM articulos_zeus "
        "WHERE deshabilitado = false OR deshabilitado IS NULL"
    )).fetchall()
    catalogo = [{"codigo": f[0], "nombre": f[1] or "", "presentacion": f[2] or "",
                 "nombre_norm": normalizar_para_match(f[1])} for f in filas]
    _CACHE_CATALOGO["filas"] = catalogo
    _CACHE_CATALOGO["ts"] = ahora
    return catalogo


def match_proveedor(db, nit_extraido, nombre_extraido) -> Optional[dict]:
    """Primero por NIT exacto normalizado; si no, fuzzy por nombre (≥90)."""
    nit = normalizar_nit(nit_extraido)
    if nit:
        fila = db.execute(text(
            "SELECT nit, nombre FROM proveedores WHERE regexp_replace(nit,'[^0-9]','','g') = :n LIMIT 1"
        ), {"n": nit}).fetchone()
        if fila:
            return {"nit": fila[0], "nombre": fila[1], "via": "nit"}
    nombre_norm = normalizar_texto(nombre_extraido)
    if len(nombre_norm) >= 4:
        from rapidfuzz import fuzz
        filas = db.execute(text("SELECT nit, nombre FROM proveedores")).fetchall()
        mejor, mejor_score = None, 0
        for f in filas:
            s = fuzz.token_set_ratio(nombre_norm, normalizar_texto(f[1]))
            if s > mejor_score:
                mejor, mejor_score = f, s
        if mejor is not None and mejor_score >= 90:
            return {"nit": mejor[0], "nombre": mejor[1], "via": "nombre", "score": mejor_score}
    return None


def codigos_historial_proveedor(db, nit) -> set:
    """Artículos que ese proveedor ya ha facturado (costos_zeus) — señal fuerte."""
    nit = normalizar_nit(nit)
    if not nit:
        return set()
    filas = db.execute(text(
        "SELECT articulo_codigo FROM costos_zeus WHERE regexp_replace(nit,'[^0-9]','','g') = :n"
    ), {"n": nit}).fetchall()
    return {f[0] for f in filas}


def items_de_oc(db, oc_numero) -> List[dict]:
    if not oc_numero:
        return []
    filas = db.execute(text(
        "SELECT i.articulo_codigo, i.articulo_nombre, i.faltante, i.valor_unitario, i.bodega_codigo "
        "FROM ordenes_compra_items i JOIN ordenes_compra o ON o.id = i.orden_id "
        "WHERE o.orden_numero = :oc"
    ), {"oc": str(oc_numero)}).fetchall()
    return [{"articulo_codigo": f[0], "articulo_nombre": f[1], "faltante": f[2],
             "valor_unitario": f[3], "bodega_codigo": f[4]} for f in filas]


def precio_referencia(db, nit, codigo) -> Optional[dict]:
    nit = normalizar_nit(nit)
    if not (nit and codigo):
        return None
    fila = db.execute(text(
        "SELECT valor_unitario, fecha_ultima_compra FROM costos_zeus "
        "WHERE regexp_replace(nit,'[^0-9]','','g') = :n AND articulo_codigo = :c "
        "ORDER BY fecha_ultima_compra DESC NULLS LAST LIMIT 1"
    ), {"n": nit, "c": codigo}).fetchone()
    if not fila or fila[0] in (None, 0):
        return None
    return {"fuente": "costos_zeus", "valor_unitario": float(fila[0]),
            "fecha": str(fila[1]) if fila[1] else None}


def match_articulo(nombre_factura, catalogo, codigos_oc, codigos_prov) -> List[dict]:
    """Top-3 candidatos del catálogo para un nombre de la factura, con score combinado.

    El primer token significativo de la factura (el sustantivo: HILO, CACAO, ATUN)
    es el "ancla": si el candidato no lo contiene, el score se capa a 55 — evita
    falsos positivos tipo HILO COSEDORA → AGUJAS COSEDORA (WRatio se descartó por
    inflar candidatos cortos).
    """
    from rapidfuzz import fuzz
    consulta = normalizar_para_match(nombre_factura)
    if not consulta:
        return []
    tokens = consulta.split()
    ancla = tokens[0] if tokens else ""
    candidatos = []
    for art in catalogo:
        # promedio set+sort: el set premia la intersección, el sort castiga
        # los tokens extra (evita que un subconjunto puro infle a 100)
        base = (fuzz.token_set_ratio(consulta, art["nombre_norm"])
                + fuzz.token_sort_ratio(consulta, art["nombre_norm"])) / 2
        if base < 40:
            continue
        tiene_ancla = any(fuzz.ratio(ancla, t) >= 85 for t in art["nombre_norm"].split())
        if not tiene_ancla:
            base = min(base, 55)
        score = base
        if art["codigo"] in codigos_oc:
            score += BOOST_OC
        elif art["codigo"] in codigos_prov:
            score += BOOST_HISTORIAL_PROVEEDOR
        candidatos.append({"codigo": art["codigo"], "nombre": art["nombre"],
                           "presentacion": art["presentacion"],
                           "score": min(round(score), 110), "score_fuzzy": round(base)})
    candidatos.sort(key=lambda c: c["score"], reverse=True)
    return candidatos[:3]


def clasificar_confianza(candidatos: List[dict]) -> str:
    if not candidatos:
        return "baja"
    top = candidatos[0]
    if top["score_fuzzy"] < FUZZY_MINIMO_PARA_ALTA:
        return "baja" if top["score"] < SCORE_MEDIA else "media"
    if top["score"] >= SCORE_ALTA:
        dominante = len(candidatos) == 1 or top["score"] - candidatos[1]["score"] >= 5
        return "alta" if dominante else "media"
    if top["score"] >= SCORE_MEDIA:
        return "media"
    return "baja"


# ── conversión de unidades a base (g / ml / und) ──
# espejo de FACTOR_UNIDAD de static/app.js + empaques
_UNIDADES_MASA = {"G": 1, "GR": 1, "GRS": 1, "GRAMO": 1, "GRAMOS": 1,
                  "KG": 1000, "KILO": 1000, "KILOS": 1000, "KGS": 1000,
                  "LB": 453.6, "LIBRA": 453.6, "LIBRAS": 453.6}
_UNIDADES_VOLUMEN = {"ML": 1, "CC": 1, "L": 1000, "LT": 1000, "LTS": 1000,
                     "LITRO": 1000, "LITROS": 1000}
_UNIDADES_CONTEO = {"UND", "UN", "UNID", "UNIDAD", "UNIDADES", "U"}
_EMPAQUES = {"PAQ", "PAQUETE", "PAQUETES", "CAJA", "CAJAS", "BULTO", "BULTOS",
             "SACO", "SACOS", "PACA", "PACAS", "BANDEJA", "BANDEJAS", "BOLSA",
             "BOLSAS", "DOCENA", "DOCENAS", "CANASTA", "CANASTILLA"}


def _unidad_base_articulo(presentacion) -> str:
    p = (presentacion or "").strip().upper()
    if p in _UNIDADES_MASA or p in ("GR", "G"):
        return "g"
    if p in _UNIDADES_VOLUMEN:
        return "ml"
    return "und"


def convertir_a_base(cantidad, unidad_factura, contenido_por_unidad, presentacion_articulo) -> dict:
    """Devuelve {"cantidad_base", "unidad_base", "confiable": bool}."""
    base = _unidad_base_articulo(presentacion_articulo)
    try:
        cant = float(cantidad)
    except (TypeError, ValueError):
        return {"cantidad_base": None, "unidad_base": base, "confiable": False}
    u = (unidad_factura or "").strip().upper().rstrip(".")

    if base == "g" and u in _UNIDADES_MASA:
        return {"cantidad_base": cant * _UNIDADES_MASA[u], "unidad_base": "g", "confiable": True}
    if base == "ml" and u in _UNIDADES_VOLUMEN:
        return {"cantidad_base": cant * _UNIDADES_VOLUMEN[u], "unidad_base": "ml", "confiable": True}
    if base == "und" and u in _UNIDADES_CONTEO:
        return {"cantidad_base": cant, "unidad_base": "und", "confiable": True}

    # empaque (bulto/caja/...) con contenido conocido
    if (u in _EMPAQUES or u in _UNIDADES_CONTEO) and isinstance(contenido_por_unidad, dict):
        cu = (contenido_por_unidad.get("unidad") or "").strip().upper()
        try:
            cv = float(contenido_por_unidad.get("valor"))
        except (TypeError, ValueError):
            cv = None
        if cv:
            if base == "g" and cu in _UNIDADES_MASA:
                return {"cantidad_base": cant * cv * _UNIDADES_MASA[cu], "unidad_base": "g", "confiable": True}
            if base == "ml" and cu in _UNIDADES_VOLUMEN:
                return {"cantidad_base": cant * cv * _UNIDADES_VOLUMEN[cu], "unidad_base": "ml", "confiable": True}
            if base == "und" and cu in _UNIDADES_CONTEO:
                return {"cantidad_base": cant * cv, "unidad_base": "und", "confiable": True}

    # sin conversión segura: entregar crudo y que el bodeguero ajuste
    return {"cantidad_base": cant, "unidad_base": base, "confiable": False}
