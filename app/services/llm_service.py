import os
import json
import logging
import time
import concurrent.futures
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

RECIPES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "recipes.json")

def load_recipes():
    if not os.path.exists(RECIPES_PATH):
        return []
    with open(RECIPES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _fallback_local_recommendations(
    intent: str,
    user_ingredients: list[str] = None,
    dietary_restrictions: list[str] = None,
    servings: int = 2
):
    all_recipes = load_recipes()
    pantry = [ing.lower().strip() for ing in (user_ingredients or [])]
    restrictions = [r.lower().strip() for r in (dietary_restrictions or [])]

    matching = [r for r in all_recipes if r.get("category", "").lower() == intent.lower()]
    if not matching:
        matching = all_recipes[:2]
    else:
        matching = matching[:2]

    results = []
    for r in matching:
        structured_ingredients = []
        for ing in r.get("ingredients", []):
            ing_lower = ing.lower()
            already_in_pantry = any(p in ing_lower for p in pantry)
            
            structured_ingredients.append({
                "original_name": f"{ing} (adaptado a {servings} porciones)",
                "catalog_query": ing,
                "quantity_needed": "Ya en despensa" if already_in_pantry else "1 unidad"
            })

        reasons = [f"Perfil orientado a {intent} para {servings} personas"]
        if restrictions:
            reasons.append(f"Considera restricciones: {', '.join(restrictions)}")

        results.append({
            "recipe_id": r.get("id", 1),
            "title": r.get("title", "Receta recomendada"),
            "servings": servings,
            "prep_time": r.get("prep_time", "30 mins"),
            "category": intent,
            "why_recommended": ". ".join(reasons) + ".",
            "ingredients": structured_ingredients,
            "instructions": r.get("instructions", "Seguir las instrucciones habituales.")
        })

    return results

def _call_groq(prompt: str, api_key: str):
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "Eres el motor de IA de NutriCart. Tu única función es devolver un array JSON válido con las recetas seleccionadas y escaladas. No agregues texto adicional fuera del JSON."
            },
            {"role": "user", "content": prompt}
        ],
        model="qwen/qwen3.8-27b",
        temperature=0.1
    )
    content = chat_completion.choices[0].message.content.strip()

    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    data = json.loads(content)
    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list):
                return val
    return data if isinstance(data, list) else None

def _keep_allowed(results, allowed_ids: set) -> list:
    """Descarta recetas que el LLM haya devuelto fuera de la lista permitida (SC-1)."""
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict) and r.get("recipe_id") in allowed_ids]

def recommend_and_normalize_recipes(
    intent: str,
    user_ingredients: list[str] = None,
    dietary_restrictions: list[str] = None,
    servings: int = 2,
    extra_preferences: dict = None
    recipes: list[dict] = None
):
    # 'recipes' llega ya filtrado por el perfil alimentario; si no se entrega, se usa el repositorio completo
    if recipes is None:
        recipes = load_recipes()
    if not recipes:
        return []
    allowed_ids = {r.get("id") for r in recipes}
    pantry = user_ingredients or []
    restrictions = dietary_restrictions or []
    extra = extra_preferences or {}

    prompt = f"""
    CONTEXTO DEL USUARIO:
    - Intención principal: {intent}
    - Cantidad de personas (porciones): {servings}
    - Restricciones alimentarias obligatorias: {restrictions}
    - Preferencias adicionales del formulario: {json.dumps(extra, ensure_ascii=False)}
    - Ingredientes ya disponibles en despensa: {pantry}

    Recetas disponibles en el repositorio:
    {json.dumps(recipes, ensure_ascii=False)}

    Instrucciones estrictas:
    1. Recomienda entre 1 y 2 recetas que coincidan con la intención '{intent}' y las preferencias adicionales.
    2. RESPETA ESTRICTAMENTE las restricciones {restrictions}. Si una receta contiene ingredientes incompatibles (por ejemplo gluten o lactosa), sustitúyelos por una alternativa apta o prioriza recetas que naturalmente cumplan el requisito.
    3. ESCALADO DE PORCIONES: Adapta proporcionalmente las cantidades de todos los ingredientes de la receta original para cubrir exactamente {servings} personas.
    4. En 'original_name', escribe la cantidad escalada para cocinar (ej: si la base pedía 200g para 2 personas y pidieron 4, pon '400g de pechuga de pollo').
    5. En 'catalog_query', escribe ÚNICAMENTE el nombre comercial genérico del producto en supermercados Lider de Chile SIN medidas de cocina ni números (ej: 'pechuga de pollo', 'arroz grado 1', 'salsa de soya', 'ajo en polvo') para maximizar la reutilización del caché.
    6. En 'quantity_needed', indica cuántos envases o unidades comerciales estándar deben comprarse para cubrir las {servings} porciones (ej: '1 unidad', '2 unidades').
    7. En 'why_recommended', justifica la elección mencionando cómo se adapta al perfil, restricciones, preferencias y cantidad de comensales.
    8. Responde ÚNICAMENTE un array JSON válido con este formato exacto:
    [
      {{
        "recipe_id": 1,
        "title": "Nombre de la receta",
        "servings": {servings},
        "prep_time": "30 mins",
        "category": "{intent}",
        "why_recommended": "Justificación",
        "ingredients": [
          {{
            "original_name": "Cantidad escalada e ingrediente para cocinar",
            "catalog_query": "Producto comercial sin medidas",
            "quantity_needed": "1 unidad"
          }}
        ],
        "instructions": "Pasos adaptados"
      }}
    ]
    """

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_groq, prompt, groq_key)
            try:
                result = future.result(timeout=6.5)
                elapsed = time.time() - start_time
                if result:
                    logging.info(f"Respuesta generada en vivo por Groq en {elapsed:.2f}s.")
                    return result
            except concurrent.futures.TimeoutError:
                elapsed = time.time() - start_time
                logging.warning(f"Groq superó el límite tras {elapsed:.2f}s. Activando fallback local.")
            except Exception as e:
                elapsed = time.time() - start_time
                logging.warning(f"Error en Groq tras {elapsed:.2f}s: {repr(e)}. Activando fallback local.")

    return _fallback_local_recommendations(intent, user_ingredients, dietary_restrictions, servings)
