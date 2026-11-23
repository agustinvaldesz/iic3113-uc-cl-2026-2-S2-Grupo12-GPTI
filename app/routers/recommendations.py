import re
import asyncio
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse
from app.schemas.menus import RecipeDetailOut
from app.services.llm_service import recommend_and_normalize_recipes, load_recipes
from app.services.supabase_service import supabase
from app.services.lider_service import search_lider_via_google_shopping

router = APIRouter(
    prefix="/api/recipes",
    tags=["Recomendaciones y LLM"]
)

ALLOWED_INTENTS = {"ahorro", "saludable", "balance", "vegano", "vegetariano"}

def _get_restrictions_from_profile(user_id: str) -> list[str]:
    """Consulta en Supabase las restricciones y dieta guardadas del usuario."""
    if not supabase:
        return []
    try:
        res = supabase.table("user_dietary_profiles")\
            .select("diet_type, allergies")\
            .eq("user_id", user_id)\
            .execute()
        
        if not res.data:
            return []

        row = res.data[0]
        restrictions = []
        
        # Mapear alergias a frases claras para el LLM
        allergy_map = {
            "gluten": "sin gluten",
            "lactosa": "sin lactosa",
            "frutos_secos": "sin frutos secos",
            "mariscos": "sin mariscos"
        }
        for a in row.get("allergies", []):
            if a in allergy_map:
                restrictions.append(allergy_map[a])

        # Mapear tipo de dieta
        if row.get("diet_type") == "vegana":
            restrictions.append("vegano estricto")
        elif row.get("diet_type") == "vegetariana":
            restrictions.append("vegetariano (sin carne ni pescado)")

        return restrictions
    except Exception:
        return []

@router.post("/recommend", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest):
    intent_clean = request.intent.lower().strip()
    if intent_clean not in ALLOWED_INTENTS:
        valid_options = ", ".join(f"'{i}'" for i in sorted(ALLOWED_INTENTS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Intención no válida. Use una de las siguientes: {valid_options}."
        )

    # Si la petición trae restricciones, úsalas; si no, cárgalas desde Supabase
    dietary_restrictions = request.dietary_restrictions
    if not dietary_restrictions:
        dietary_restrictions = _get_restrictions_from_profile(request.user_id)

    # 1. Generar recomendaciones escaladas a 'servings' y preferencias extra
    llm_results = recommend_and_normalize_recipes(
        intent=intent_clean,
        user_ingredients=request.shopping_list,
        dietary_restrictions=dietary_restrictions,
        servings=request.servings,
        extra_preferences=request.extra_preferences
    )

    if not llm_results:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible generar las recomendaciones."
        )

    # 2. Cotizar ingredientes faltantes en paralelo y calcular costo total
    pantry_items = [item.lower().strip() for item in (request.shopping_list or [])]

    async with httpx.AsyncClient() as http_client:
        for rec in llm_results:
            rec.setdefault("servings", request.servings)
            ingredients = rec.get("ingredients", [])
            
            # Filtrar los que ya están en despensa antes de gastar créditos en Serper
            tasks = []
            task_indices = []
            for idx, ing in enumerate(ingredients):
                query_lower = ing["catalog_query"].lower()
                orig_lower = ing["original_name"].lower()
                already_have = any(p in query_lower or p in orig_lower for p in pantry_items)
                ing["in_pantry"] = already_have

                if already_have:
                    ing["lider_match"] = None
                else:
                    tasks.append(search_lider_via_google_shopping(ing["catalog_query"], http_client))
                    task_indices.append(idx)

            if tasks:
                matches = await asyncio.gather(*tasks)
                for task_idx, match_result in zip(task_indices, matches):
                    ingredients[task_idx]["lider_match"] = match_result

            # Calcular costo total considerando las unidades necesarias según porciones
            total_cost = 0.0
            for ing in ingredients:
                if not ing["in_pantry"] and ing.get("lider_match"):
                    qty_str = str(ing.get("quantity_needed", "1"))
                    match_num = re.search(r"\d+", qty_str)
                    units_to_buy = int(match_num.group()) if match_num else 1
                    total_cost += ing["lider_match"].get("price", 0.0) * units_to_buy

            rec["total_estimated_cost"] = round(total_cost, 2)

    return {
        "user_intent": request.intent,
        "recommendations": llm_results
    }

# --- Endpoint 3.5: Ver una receta paso a paso para el modal ---

def _parse_steps(instructions_text: str) -> list[str]:
    if not instructions_text:
        return []
    lines = [line.strip() for line in re.split(r"\n+|(?=\d+[\.\)]\s)", instructions_text) if line.strip()]
    cleaned = [re.sub(r"^\d+[\.\)]\s*", "", line).strip() for line in lines if line.strip()]
    return cleaned if cleaned else [instructions_text.strip()]

def _parse_ingredient_fallback(raw_ing: str, scale_factor: float) -> dict:
    match = re.match(r"^(\d+(?:[\.,]\d+)?)\s*([a-zA-ZáéíóúÁÉÍÓÚ]+)?\s+(?:de\s+)?(.+)$", raw_ing.strip())
    if match:
        qty = float(match.group(1).replace(",", ".")) * scale_factor
        unit = match.group(2) or "unidad"
        name = match.group(3)
        return {"name": name, "quantity": round(qty, 2), "unit": unit, "is_optional": False}
    return {"name": raw_ing.strip(), "quantity": round(1 * scale_factor, 2), "unit": "unidad", "is_optional": False}

@router.get("/{recipe_id}", response_model=RecipeDetailOut)
def get_recipe_detail(
    recipe_id: int,
    servings: Optional[int] = Query(default=None, ge=1)
):
    target_recipe = None
    base_servings = 2

    # 1. Buscar en Supabase (solo recetas con status 'aprobada')
    if supabase:
        try:
            res = supabase.table("recipes").select("*").eq("id", recipe_id).execute()
            if res.data:
                row = res.data[0]
                if row.get("status") and row.get("status") != "aprobada":
                    raise HTTPException(status_code=404, detail="No encontramos esta receta.")
                target_recipe = row
                base_servings = row.get("servings") or 2
        except HTTPException:
            raise
        except Exception:
            pass

    # 2. Fallback al JSON local si no está en Supabase
    if not target_recipe:
        local_recipes = load_recipes()
        target_recipe = next((r for r in local_recipes if r.get("id") == recipe_id), None)
        if target_recipe:
            base_servings = target_recipe.get("servings") or 2

    if not target_recipe:
        raise HTTPException(status_code=404, detail="No encontramos esta receta.")

    final_servings = servings if servings is not None else base_servings
    scale_factor = final_servings / base_servings

    # 3. Intentar leer ingredientes normalizados de recipe_ingredients
    scaled_ingredients = []
    if supabase:
        try:
            ri_res = supabase.table("recipe_ingredients")\
                .select("quantity, unit, is_optional, ingredients(name)")\
                .eq("recipe_id", recipe_id)\
                .execute()
            if ri_res.data:
                for item in ri_res.data:
                    ing_info = item.get("ingredients") or {}
                    scaled_ingredients.append({
                        "name": ing_info.get("name", "Ingrediente"),
                        "quantity": round(float(item.get("quantity", 1)) * scale_factor, 2),
                        "unit": item.get("unit", "unidad"),
                        "is_optional": bool(item.get("is_optional", False))
                    })
        except Exception:
            pass

    # 4. Si no hay tabla intermedia, parsear desde la lista de strings de la receta
    if not scaled_ingredients:
        for raw_ing in target_recipe.get("ingredients", []):
            scaled_ingredients.append(_parse_ingredient_fallback(raw_ing, scale_factor))

    return {
        "id": target_recipe["id"],
        "title": target_recipe["title"],
        "servings": final_servings,
        "prep_time": target_recipe.get("prep_time", "30 min"),
        "diet_type": target_recipe.get("diet_type") or target_recipe.get("category", "balanceada"),
        "allergens": target_recipe.get("allergens") or [],
        "ingredients": scaled_ingredients,
        "steps": _parse_steps(target_recipe.get("instructions", ""))
    }