"""
Mapeo de ingredientes al catálogo de Lider y cotización de la canasta.

Cubre REQ-09 (buscar el equivalente de cada ingrediente), REQ-10 y RN-04 (caché de
precios con vigencia de 24 horas), REQ-11 (precio por ingrediente y total), REQ-12
(ingredientes no cotizables se informan y se omiten del total) y la Solicitud de
cambio SC-2 (alternativa más económica por ingrediente, reemplazo y ahorro).
"""
import json
import math
import os
import re
import unicodedata
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

from sqlalchemy.orm import Session

from app.models_db import IngredientDB, IngredientProductDB, ProductCacheDB
from app.services import lider_client

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "lider_catalog.json")
PRICE_TTL = timedelta(hours=24)  # RN-04

# Equivalencias culinarias aproximadas (en g o ml)
KITCHEN_UNITS = {
    "taza": 240, "tazas": 240,
    "cucharada": 15, "cucharadas": 15, "cda": 15, "cdas": 15,
    "cucharadita": 5, "cucharaditas": 5, "cdta": 5, "cdtas": 5,
}
MASS_UNITS = {"g": 1, "gr": 1, "gramos": 1, "kg": 1000, "ml": 1, "l": 1000, "litro": 1000, "litros": 1000}
COUNT_UNITS = {"unidad", "unidades", "un", "diente", "dientes", "tallo", "tallos", "huevo", "huevos"}
PACKAGE_UNITS = {"paquete", "paquetes", "lata", "latas", "frasco", "bolsa", "sobre"}


# ---------------------------------------------------------------------------
# Utilidades de texto y cantidades
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def _to_number(token: str) -> float:
    if "/" in token:
        num, den = token.split("/", 1)
        return float(num) / float(den)
    return float(token.replace(",", "."))


_NUM = r"\d+(?:[.,]\d+)?(?:/\d+)?"


def parse_quantity(text: str) -> tuple[Optional[float], Optional[str]]:
    """
    Extrae (cantidad, unidad) de un texto como "450 g de carne" o "1/2 taza de leche".
    Unidad resultante: "g", "ml", "unidad", "paquete" o None si no se reconoce.
    Si el texto trae peso o volumen explícito (ej. "1 lata de 225 g"), ese valor manda.
    """
    t = normalize(text)
    if not t or "despensa" in t:
        return None, None

    explicit = re.search(rf"({_NUM})\s*(kg|gr|g|ml|litros?|l)\b", t)
    if explicit:
        unit = explicit.group(2)
        base = "ml" if unit in ("ml", "l", "litro", "litros") else "g"
        return _to_number(explicit.group(1)) * MASS_UNITS[unit], base

    # "1 a 2 cucharadas" -> se usa el valor mayor
    m = re.match(rf"({_NUM})(?:\s*a\s*({_NUM}))?\s*([a-z]+)?", t)
    if not m:
        return None, None
    amount = _to_number(m.group(2) or m.group(1))
    word = m.group(3) or ""
    if word in KITCHEN_UNITS:
        return amount * KITCHEN_UNITS[word], "g"
    if word in PACKAGE_UNITS:
        return amount, "paquete"
    return amount, "unidad"


# ---------------------------------------------------------------------------
# Catálogo semilla y metadatos de mapeo
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _meta() -> tuple[dict, set]:
    """Metadatos por ingrediente (alias, exclusiones, peso por unidad) y SKU vendidos a granel."""
    by_name, granel = {}, set()
    for ing in load_catalog()["ingredients"]:
        by_name[ing["name"]] = {
            "aliases": [normalize(a) for a in ing.get("aliases", [])],
            "exclude": [normalize(e) for e in ing.get("exclude", [])],
            "unit_weight_g": ing.get("unit_weight_g"),
        }
        granel.update(p["sku"] for p in ing["products"] if p.get("sold_by_weight"))
    return by_name, granel


def seed_catalog_if_empty(db: Session) -> int:
    """Carga el catálogo semilla en products_cache / ingredients / ingredient_products si no hay productos."""
    if db.query(ProductCacheDB).first() is not None:
        return 0
    now = datetime.utcnow()
    created = 0
    for ing in load_catalog()["ingredients"]:
        ingredient = db.query(IngredientDB).filter(IngredientDB.name == ing["name"]).first()
        if ingredient is None:
            ingredient = IngredientDB(name=ing["name"], category=ing["category"], default_unit=ing["default_unit"])
            db.add(ingredient)
            db.flush()
        for p in ing["products"]:
            product = ProductCacheDB(sku=p["sku"], name=p["name"], price=p["price"], last_updated=now)
            db.add(product)
            db.flush()
            db.add(IngredientProductDB(
                ingredient_id=ingredient.id,
                product_id=product.id,
                package_quantity=p["package_quantity"],
                package_unit=p["package_unit"],
                is_default=p["is_default"],
            ))
            created += 1
    db.commit()
    return created


def match_ingredient(text: str) -> Optional[str]:
    """Devuelve el nombre del ingrediente del catálogo que mejor calza con el texto (alias más largo)."""
    t = normalize(text)
    best, best_len = None, 0
    for name, meta in _meta()[0].items():
        if any(e in t for e in meta["exclude"]):
            continue
        for alias in meta["aliases"]:
            if len(alias) > best_len and re.search(rf"\b{re.escape(alias)}\b", t):
                best, best_len = name, len(alias)
    return best


# ---------------------------------------------------------------------------
# Precios (caché 24 h) y cálculo de costo por producto
# ---------------------------------------------------------------------------

def current_price(db: Session, product: ProductCacheDB) -> tuple[float, bool]:
    """Precio vigente del producto. Si la caché venció intenta refrescar en Lider; si falla, usa la caché y la marca como desactualizada."""
    is_stale = product.last_updated is None or datetime.utcnow() - product.last_updated > PRICE_TTL
    if is_stale:
        fresh = lider_client.fetch_price(product.name)
        if fresh:
            product.price = fresh
            product.last_updated = datetime.utcnow()
            db.commit()
            is_stale = False
    return product.price, is_stale


def _needed_in_base_unit(amount: Optional[float], unit: Optional[str], default_unit: str, unit_weight: Optional[float]) -> Optional[float]:
    """Convierte la cantidad de la receta a la unidad base del ingrediente. None = no se puede estimar (se compra 1 envase)."""
    if amount is None or unit is None or unit == "paquete":
        return None
    if default_unit in ("g", "ml"):
        if unit in ("g", "ml"):
            return amount
        if unit == "unidad" and unit_weight:
            return amount * unit_weight
        return None
    # unidad base = "unidad"
    return amount if unit == "unidad" else None


def _product_option(db: Session, link: IngredientProductDB, needed: Optional[float], packages_hint: Optional[float]) -> dict:
    product = link.product
    price, stale = current_price(db, product)
    granel = product.sku in _meta()[1]
    if needed is None:
        packages = packages_hint or 1
    elif granel:
        packages = round(needed / link.package_quantity, 3)
    else:
        packages = max(1, math.ceil(needed / link.package_quantity - 1e-9))
    return {
        "sku": product.sku,
        "name": product.name,
        "price": round(price),
        "package_quantity": link.package_quantity,
        "package_unit": link.package_unit,
        "sold_by_weight": granel,
        "packages": packages,
        "cost": round(price * packages),
        "unit_price": round(price / link.package_quantity, 2),
        "is_default": bool(link.is_default),
        "price_updated_at": product.last_updated.isoformat() if product.last_updated else None,
        "price_stale": stale,
    }


# ---------------------------------------------------------------------------
# Cotización
# ---------------------------------------------------------------------------

def quote_items(db: Session, items: list[dict], pantry: Optional[list[str]] = None, selections: Optional[dict] = None) -> dict:
    """
    Cotiza una lista de ingredientes (de una receta o de una canasta).
    items: [{"original_name", "catalog_query"?, "quantity_needed"?}]
    pantry: ingredientes que el usuario ya tiene (no se cotizan).
    selections: {nombre_ingrediente: sku} para reemplazar el producto por defecto (SC-2, "reemplazar con un clic").
    """
    selections = selections or {}
    pantry_ingredients = {match_ingredient(p) for p in (pantry or [])} - {None}
    meta = _meta()[0]

    # Agrupa líneas que corresponden al mismo ingrediente para no comprar dos veces el mismo envase
    groups: dict[str, dict] = {}
    not_quoted, in_pantry = [], []
    for item in items:
        original = item.get("original_name", "")
        query = item.get("catalog_query") or original
        name = match_ingredient(query) or match_ingredient(original)
        if name is None:
            not_quoted.append(original)
            continue
        if name in pantry_ingredients or normalize(item.get("quantity_needed", "")) == "ya en despensa":
            in_pantry.append(original)
            continue
        ingredient = db.query(IngredientDB).filter(IngredientDB.name == name).first()
        if ingredient is None:  # catálogo sin cargar para este ingrediente
            not_quoted.append(original)
            continue
        g = groups.setdefault(name, {"sources": [], "needed": 0.0, "unknown": 0})
        g["sources"].append(original)
        amount, unit = parse_quantity(original)
        if unit is None and item.get("quantity_needed"):
            amount, unit = parse_quantity(item["quantity_needed"])
        needed = _needed_in_base_unit(amount, unit, ingredient.default_unit, meta[name]["unit_weight_g"])
        if needed is None:
            g["unknown"] += amount if unit == "paquete" and amount else 1
        else:
            g["needed"] += needed

    lines, warnings = [], []
    total = total_default = potential_savings = 0
    for name, g in groups.items():
        ingredient = db.query(IngredientDB).filter(IngredientDB.name == name).first()
        links = db.query(IngredientProductDB).filter(IngredientProductDB.ingredient_id == ingredient.id).all()
        if not links:
            not_quoted.extend(g["sources"])
            continue
        needed = g["needed"] or None
        packages_hint = None if needed else max(1, g["unknown"])
        options = sorted((_product_option(db, l, needed, packages_hint) for l in links), key=lambda o: o["cost"])
        default = next((o for o in options if o["is_default"]), options[0])

        selected = default
        wanted = selections.get(name)
        if wanted:
            chosen = next((o for o in options if o["sku"] == wanted), None)
            if chosen:
                selected = chosen
            else:
                warnings.append(f"El SKU {wanted} no corresponde a '{name}'; se mantiene el producto por defecto.")

        cheapest = options[0]
        alternative = None
        if cheapest["sku"] != selected["sku"] and cheapest["cost"] < selected["cost"]:
            alternative = {**cheapest, "savings": selected["cost"] - cheapest["cost"]}
            potential_savings += alternative["savings"]

        total += selected["cost"]
        total_default += default["cost"]
        lines.append({
            "ingredient": name,
            "category": ingredient.category,
            "source_items": g["sources"],
            "quantity_needed": round(needed, 1) if needed else None,
            "unit": ingredient.default_unit if needed else None,
            "selected": selected,
            "cheaper_alternative": alternative,
            "options": options,
        })

    if any(l["selected"]["price_stale"] for l in lines):
        warnings.append("Algunos precios provienen de la caché y tienen más de 24 horas; pueden diferir del precio actual en Lider.")

    message = None
    if not_quoted:
        message = "Algunos ingredientes no se pudieron cotizar y se omitieron del total: " + ", ".join(not_quoted)

    return {
        "lines": lines,
        "total": total,
        "total_default": total_default,
        "savings": total_default - total,
        "potential_savings": potential_savings,
        "not_quoted": not_quoted,
        "in_pantry": in_pantry,
        "message": message,
        "warnings": warnings,
    }
