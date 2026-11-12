import re
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, status
from app.schemas.recommendations import RecommendationRequest, RecommendationResponse
from app.services.llm_service import recommend_and_normalize_recipes
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
            
            # Identificar qué ingredientes ya están en despensa antes de cotizar
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

            # Ejecutar consultas solo para los ingredientes que faltan comprar
            if tasks:
                matches = await asyncio.gather(*tasks)
                for task_idx, match_result in zip(task_indices, matches):
                    ingredients[task_idx]["lider_match"] = match_result

            # Calcular costo total considerando la cantidad de unidades necesarias
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