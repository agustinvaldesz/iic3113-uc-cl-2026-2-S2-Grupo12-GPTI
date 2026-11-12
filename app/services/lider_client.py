"""
Consulta en vivo (opcional) de precios en el sitio de Lider.

Lider no tiene API pública y su sitio bloquea consultas automatizadas (cola Queue-it
y anti-bot, verificado el 12-11-2026; ver riesgo R01). Por eso este cliente:
  - está desactivado por defecto (LIDER_LIVE_REFRESH=true para activarlo),
  - nunca lanza excepciones: si algo falla devuelve None y el sistema usa la caché.
"""
import os
import logging
from typing import Optional

import requests

LIDER_SEARCH_URL = os.getenv("LIDER_SEARCH_URL", "https://www.lider.cl/supermercado/search")
TIMEOUT_SECONDS = 3


def live_refresh_enabled() -> bool:
    return os.getenv("LIDER_LIVE_REFRESH", "false").lower() == "true"


def fetch_price(product_name: str) -> Optional[float]:
    """Intenta obtener el precio vigente de un producto. Devuelve None si no es posible."""
    if not live_refresh_enabled():
        return None
    try:
        resp = requests.get(
            LIDER_SEARCH_URL,
            params={"query": product_name},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        if resp.status_code != 200 or "json" not in resp.headers.get("Content-Type", ""):
            return None
        products = resp.json().get("products") or []
        if not products:
            return None
        price = products[0].get("price", {})
        value = price.get("BasePriceSales") if isinstance(price, dict) else price
        return float(value) if value else None
    except Exception as e:  # red, bloqueo, formato inesperado
        logging.info(f"Refresco en vivo de Lider no disponible: {e!r}")
        return None
