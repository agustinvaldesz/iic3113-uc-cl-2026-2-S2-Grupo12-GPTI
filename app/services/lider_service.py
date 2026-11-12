import os
import httpx
import logging
from datetime import datetime, timezone, timedelta
from app.services.supabase_service import supabase

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
CACHE_TTL_HOURS = 24

def _parse_clp_price(raw_price: str) -> float:
    cleaned = str(raw_price or "0").replace("$", "").replace(".", "").strip()
    return float("".join(filter(str.isdigit, cleaned)) or 0)

def _get_cached_price(query: str) -> dict | None:
    if not supabase:
        return None
    try:
        res = supabase.table("product_prices_cache")\
            .select("*")\
            .eq("catalog_query", query.lower().strip())\
            .execute()
        if res.data:
            row = res.data[0]
            updated = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - updated < timedelta(hours=CACHE_TTL_HOURS):
                return {
                    "matched": True,
                    "source": "supabase_cache",
                    "product_name": row["product_name"],
                    "price": float(row["price"]),
                    "url": row["url"],
                    "cheaper_alternatives": row.get("alternatives") or []
                }
    except Exception:
        pass
    return None

def _save_cached_price(query: str, item: dict):
    if not supabase or not item.get("matched"):
        return
    try:
        supabase.table("product_prices_cache").upsert({
            "catalog_query": query.lower().strip(),
            "product_name": item["product_name"],
            "price": item["price"],
            "url": item.get("url"),
            "source": item.get("source", "google_shopping"),
            "alternatives": item.get("cheaper_alternatives", []),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception:
        pass

async def search_lider_via_google_shopping(query: str, client: httpx.AsyncClient) -> dict:
    clean_query = query.lower().strip()

    cached = _get_cached_price(clean_query)
    if cached:
        return cached

    if not SERPER_API_KEY:
        return {
            "matched": False,
            "source": "fallback",
            "product_name": query,
            "price": 1990,
            "cheaper_alternatives": []
        }

    url = "https://google.serper.dev/shopping"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": f"{clean_query} lider", "gl": "cl", "hl": "es"}

    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=3.0)
        if resp.status_code == 200:
            items = resp.json().get("shopping", [])
            lider_items = [i for i in items if "lider" in i.get("source", "").lower()]
            candidates = lider_items if lider_items else items

            parsed_products = []
            seen_titles = set()
            for item in candidates:
                title = item.get("title", "").strip()
                price = _parse_clp_price(item.get("price"))
                if title and price > 0 and title.lower() not in seen_titles:
                    seen_titles.add(title.lower())
                    parsed_products.append({
                        "product_name": title,
                        "price": price,
                        "url": item.get("link"),
                        "is_store_brand": any(b in title.lower() for b in ["lider", "líder", "acuenta", "great value"])
                    })

            if parsed_products:
                # Ordenar de mayor a menor para cotización inicial estándar/calidad,
                # o priorizar marcas tradicionales primero y dejar marcas propias como ahorro
                standard_options = [p for p in parsed_products if not p["is_store_brand"]]
                primary = standard_options[0] if standard_options else parsed_products[0]

                # Filtrar alternativas estrictamente más baratas que la opción inicial
                cheaper = [
                    {
                        "product_name": p["product_name"],
                        "price": p["price"],
                        "savings": round(primary["price"] - p["price"], 2),
                        "url": p["url"]
                    }
                    for p in sorted(parsed_products, key=lambda x: x["price"])
                    if p["price"] < primary["price"]
                ][:3]  # Máximo 3 alternativas más baratas por ingrediente

                result = {
                    "matched": True,
                    "source": "google_shopping",
                    "product_name": primary["product_name"],
                    "price": primary["price"],
                    "url": primary["url"],
                    "cheaper_alternatives": cheaper
                }
                _save_cached_price(clean_query, result)
                return result
    except Exception as e:
        logging.warning(f"Error en Serper Shopping para '{query}': {e}")

    return {
        "matched": False,
        "source": "estimated",
        "product_name": query,
        "price": 1990,
        "cheaper_alternatives": []
    }