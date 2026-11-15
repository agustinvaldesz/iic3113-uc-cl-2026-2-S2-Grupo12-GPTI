"""
Generación de recetas con IA para el gestor de recetas.

La IA solo propone borradores: se validan y se guardan como
"pendiente" hasta que un gestor los revise (RN-01).
"""
import json
import os
import re
from groq import Groq
from pydantic import ValidationError
from app.schemas.admin_recipes import RecipeIn
from app.services.catalog_service import load_catalog, normalize

MODEL = os.getenv("GROQ_RECIPE_MODEL", "qwen/qwen3.8-27b")

# Palabras que suelen indicar un alérgeno; sirven para advertir al gestor, no para decidir solo
ALLERGEN_KEYWORDS = {
    "gluten": ["harina", "pan ", "pan rallado", "pasta", "fideo", "tallarin", "trigo", "cuscus", "salsa de soya", "galleta", "tortilla de trigo"],
    "lactosa": ["leche", "queso", "crema", "mantequilla", "yogur", "manjar"],
    "frutos_secos": ["nuez", "nueces", "almendra", "mani", "avellana", "pistacho", "castana"],
    "mariscos": ["camaron", "chorito", "almeja", "macha", "jaiba", "calamar", "pulpo", "ostion", "salsa de ostras"],
}

class GeneratorUnavailable(Exception):
    pass

def allergen_warnings(ingredients: list[str], allergens: list[str]) -> list[str]:
    text = " " + normalize(" ".join(ingredients)) + " "
    warnings = []
    for allergen, words in ALLERGEN_KEYWORDS.items():
        if allergen in allergens:
            continue
        hits = [w.strip() for w in words if w in text]
        if hits:
            warnings.append(f"Revisar '{allergen}': aparece {', '.join(sorted(set(hits)))} y la receta no lo declara.")
    return warnings

def _build_prompt(req) -> str:
    known = sorted(i["name"] for i in load_catalog()["ingredients"])
    wishes = []
    if req.diet_type:
        wishes.append(f"tipo de dieta: {req.diet_type}")
    if req.diet_focus:
        wishes.append(f"enfoque: {req.diet_focus}")
    if req.prioritize_savings:
        wishes.append("ingredientes económicos y fáciles de encontrar en un supermercado chileno")
    if req.notes:
        wishes.append(f"indicaciones del gestor: {req.notes}")
    return f"""
Crea {req.count} recetas caseras distintas para un hogar chileno. Requisitos: {"; ".join(wishes) or "variadas"}.
Usa preferentemente estos ingredientes, con el mismo nombre: {", ".join(known)}.

Responde SOLO un objeto JSON con la forma {{"recipes": [ ... ]}}. Cada receta:
{{
  "title": "Nombre",
  "servings": 4,
  "prep_time": "30 mins",
  "diet_type": "con_carne" | "vegetariana" | "vegana",
  "allergens": subconjunto de ["gluten", "lactosa", "frutos_secos", "mariscos"] (marca cualquiera que pueda estar presente),
  "diet_focus": uno o más de ["balanceada", "alta_proteina", "baja_carbohidratos", "baja_grasas"],
  "ingredients": ["450 g de pechuga de pollo", "1 cebolla", "200 ml de leche"],
  "instructions": "Pasos breves en un solo párrafo."
}}
Cada ingrediente debe empezar con una cantidad numérica y una unidad (g, ml o unidades). Sin texto fuera del JSON.
"""

def generate_drafts(req) -> tuple[list[RecipeIn], list[str]]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise GeneratorUnavailable("No hay GROQ_API_KEY configurada.")
    try:
        completion = Groq(api_key=api_key, timeout=40).chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Eres un chef nutricionista. Respondes solo JSON válido."},
                {"role": "user", "content": _build_prompt(req)},
            ],
            temperature=0.6,
            max_tokens=900 * req.count,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or ""
    except Exception as e:  # Límite de tokens, red, modelo saturado, etc.
        raise GeneratorUnavailable(f"La IA no respondió: {e!r}") from e

    content = re.sub(r"^```(json)?|```$", "", content.strip()).strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise GeneratorUnavailable("La IA respondió en un formato que no es JSON.") from e

    raw = data.get("recipes", []) if isinstance(data, dict) else data
    valid, discarded = [], []
    for item in raw if isinstance(raw, list) else []:
        try:
            valid.append(RecipeIn.model_validate(item))
        except ValidationError as e:
            title = item.get("title", "sin título") if isinstance(item, dict) else "sin título"
            discarded.append(f"{title}: {e.errors()[0]['msg']}")
    return valid, discarded
