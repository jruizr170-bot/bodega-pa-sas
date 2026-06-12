"""Extracción de datos de fotos de facturas con Claude (visión).

Prompt canónico: superset del de agentes/agentes/a1_lector_fotos.py — agrega
contenido_por_unidad para convertir empaques (bulto/caja) a unidad base.
"""
import base64
import json
import os
import re
import time
from typing import List, Optional

# Modelo y esfuerzo configurables por entorno (IA_MODELO / IA_EFFORT).
# Sonnet 4.6: mismo modelo que ya usa el agente A1; ~$0.02-0.04 por factura.
MODELO_DEFAULT = "claude-sonnet-4-6"
EFFORT_DEFAULT = "high"

# USD por millón de tokens (input, output)
PRECIOS = {
    "claude-fable-5":   (10.0, 50.0),
    "claude-opus-4-8":  (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

PROMPT_EXTRACCION = """
Eres un sistema OCR especializado en documentos de compras de alimentos en Colombia.
Te van a mostrar una o varias fotos tomadas con celular de una misma remisión o factura física
(varias fotos = varias páginas o tomas del mismo documento; NO las trates como documentos distintos).

Tu trabajo es EXTRAER todos los datos visibles con máxima precisión.

REGLAS FISCALES COLOMBIANAS QUE DEBES DETECTAR EN LA FOTO:
Las facturas colombianas tienen campos separados que DEBES buscar:
- Subtotal / Total Bruto: valor de los productos SIN impuestos
- IVA: puede ser 0%, 5%, o 19% — extrae tanto el porcentaje como el monto
- ReteICA: retención de industria y comercio (resta)
- ReteRenta / Retención en la fuente (resta)
- ReteIVA: retención sobre el IVA (resta)
- Total a pagar: neto después de impuestos y retenciones

IMPORTANTE: El subtotal SIN impuestos es el campo más crítico para cruzar contra bodega.
Si ves solo un "Total" sin desglose, extrae ese valor en total_a_pagar y deja subtotal en 0.

Si es una REMISIÓN (no factura electrónica), típicamente NO tiene impuestos — solo cantidades.

SOBRE NÚMEROS DE FACTURA:
- Extrae el número COMPLETO tal como aparece (incluyendo prefijos: FV, FE, FA, NC, PA)
- Son frecuentes los dígitos extra o faltantes — sé meticuloso

SOBRE LAS UNIDADES DE CADA PRODUCTO:
- "unidad" es la unidad en que la factura expresa la cantidad (kg, g, lb, l, ml, und, paq, caja, bulto, saco, paca, bandeja...)
- Si la unidad es un EMPAQUE (bulto, caja, saco, paca, paq, bandeja) y el documento indica cuánto
  contiene cada empaque (ej. "BULTO X 25 KG", "CAJA 12 UND", "PACA 24X500G"), llena
  contenido_por_unidad con ese contenido. "PACA 24X500G" → {"valor": 12000, "unidad": "g"}
  (24 × 500 g). Si no se ve el contenido, pon null.
- NO conviertas la cantidad principal: déjala tal como la dice la factura.

EXTRACCIÓN GENERAL:
- Si algo no se puede leer, pon "ILEGIBLE"
- Si la foto no es de un documento comercial, pon foto_valida: false
- Los números colombianos usan punto para miles y coma para decimales (1.500.000,00)
- Responde SOLO en JSON, sin texto adicional

RESPUESTA JSON:
{
    "foto_valida": true,
    "tipo_documento": "factura_electronica|factura_fisica|remision|otro|no_identificado",
    "calidad_foto": "buena|regular|mala|ilegible",
    "proveedor": "nombre completo o ILEGIBLE",
    "nit": "número o ILEGIBLE",
    "numero_documento": "número completo con prefijo o ILEGIBLE",
    "fecha": "DD/MM/YYYY o ILEGIBLE",
    "productos": [
        {
            "nombre": "...",
            "cantidad": 0,
            "unidad": "kg|g|lb|l|ml|und|paq|caja|bulto|saco|...",
            "contenido_por_unidad": {"valor": 0, "unidad": "kg|g|l|ml|und"},
            "precio_unitario": 0,
            "precio_total": 0
        }
    ],
    "datos_fiscales": {
        "subtotal": 0,
        "iva_porcentaje": 0,
        "iva_monto": 0,
        "rete_ica": 0,
        "rete_renta": 0,
        "rete_iva": 0,
        "total_a_pagar": 0,
        "tiene_impuestos": false
    },
    "observaciones": "cualquier nota adicional visible"
}
"""

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(timeout=120.0, max_retries=2)
    return _client


def _parsear_json(texto: str) -> Optional[dict]:
    """El modelo responde JSON; tolera fences ```json ... ``` o texto alrededor."""
    texto = texto.strip()
    try:
        return json.loads(texto)
    except Exception:
        pass
    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def extraer_de_fotos(fotos_jpeg: List[bytes]) -> dict:
    """Lee una factura a partir de 1..N fotos JPEG (multi-imagen en un solo request).

    Devuelve {"ok": True, "datos": {...}, "modelo", "costo_usd", "tokens_input",
    "tokens_output", "duracion_s"} o {"ok": False, "error": "..."}.
    """
    modelo = os.environ.get("IA_MODELO", MODELO_DEFAULT)
    effort = os.environ.get("IA_EFFORT", EFFORT_DEFAULT)
    contenido = []
    for raw in fotos_jpeg:
        contenido.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(raw).decode(),
            },
        })
    contenido.append({
        "type": "text",
        "text": "Extrae todos los datos de esta factura/remisión. Presta especial atención al "
                "número de documento completo, al NIT, a las unidades de cada producto y a los "
                "campos de subtotal, IVA y retenciones.",
    })

    t0 = time.time()
    try:
        client = _get_client()
        resp = client.messages.create(
            model=modelo,
            max_tokens=4000,
            output_config={"effort": effort},
            system=PROMPT_EXTRACCION,
            messages=[{"role": "user", "content": contenido}],
        )
    except Exception as e:
        return {"ok": False, "error": "Error llamando a la IA: %s" % e}

    duracion = round(time.time() - t0, 1)
    tok_in = resp.usage.input_tokens
    tok_out = resp.usage.output_tokens
    p_in, p_out = PRECIOS.get(modelo, (10.0, 50.0))
    costo = round(tok_in / 1e6 * p_in + tok_out / 1e6 * p_out, 4)

    if resp.stop_reason == "refusal":
        return {"ok": False, "error": "La IA declinó leer esta imagen (refusal).",
                "costo_usd": costo, "duracion_s": duracion}

    texto = ""
    for b in resp.content:
        if b.type == "text":
            texto += b.text
    datos = _parsear_json(texto)
    if not datos:
        return {"ok": False, "error": "La IA no devolvió JSON válido.",
                "costo_usd": costo, "duracion_s": duracion}

    return {
        "ok": True,
        "datos": datos,
        "modelo": modelo,
        "costo_usd": costo,
        "tokens_input": tok_in,
        "tokens_output": tok_out,
        "duracion_s": duracion,
    }
