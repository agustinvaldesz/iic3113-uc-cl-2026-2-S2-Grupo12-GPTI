"""
Filtro excluyente de recetas por dieta y alérgenos (Solicitud de cambio SC-1).

Se aplica ANTES de llamar al LLM, en el fallback local y al validar la respuesta
del LLM, para que nunca se recomiende una receta incompatible con el perfil del
usuario aunque el modelo de lenguaje falle o ignore las instrucciones.
"""
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models_db import UserDietaryProfileDB

# Qué tipos de receta puede comer cada tipo de dieta
DIET_COMPATIBILITY = {
    "con_carne": {"con_carne", "vegetariana", "vegana"},
    "vegetariana": {"vegetariana", "vegana"},
    "vegana": {"vegana"},
}

# Texto que se le entrega al LLM para explicar las restricciones
ALLERGY_PROMPT_TEXT = {
    "gluten": "sin gluten",
    "lactosa": "sin lactosa",
    "frutos_secos": "sin frutos secos",
    "mariscos": "sin mariscos",
}
DIET_PROMPT_TEXT = {
    "vegetariana": "vegetariano (sin carne ni pescado)",
    "vegana": "vegano estricto",
}


def get_user_restrictions(db: Session, user_id: int) -> tuple[str, list[str]]:
    """Devuelve (tipo de dieta, alergias) guardados por el usuario. Sin perfil = sin restricciones."""
    profile = db.query(UserDietaryProfileDB).filter(UserDietaryProfileDB.user_id == user_id).first()
    if profile is None:
        return "con_carne", []
    return profile.diet_type or "con_carne", list(profile.allergies or [])


def is_recipe_allowed(recipe: dict, diet_type: str, allergies: Iterable[str]) -> bool:
    """
    Una receta se permite solo si su dieta es compatible y no contiene ningún alérgeno declarado.
    Una receta sin etiquetas se trata como no apta para usuarios con restricciones (criterio seguro).
    """
    allergies = set(allergies or [])
    recipe_diet = recipe.get("diet_type")
    recipe_allergens = recipe.get("allergens")

    has_restrictions = diet_type != "con_carne" or bool(allergies)
    if has_restrictions and (recipe_diet is None or recipe_allergens is None):
        return False

    allowed_diets = DIET_COMPATIBILITY.get(diet_type, DIET_COMPATIBILITY["con_carne"])
    if recipe_diet is not None and recipe_diet not in allowed_diets:
        return False

    return not (set(recipe_allergens or []) & allergies)


def filter_recipes(recipes: list[dict], diet_type: str, allergies: Optional[Iterable[str]]) -> list[dict]:
    return [r for r in recipes if is_recipe_allowed(r, diet_type, allergies or [])]


def restrictions_to_text(diet_type: str, allergies: Iterable[str]) -> list[str]:
    """Convierte el perfil en frases claras para el prompt del LLM."""
    texts = [ALLERGY_PROMPT_TEXT[a] for a in allergies if a in ALLERGY_PROMPT_TEXT]
    if diet_type in DIET_PROMPT_TEXT:
        texts.append(DIET_PROMPT_TEXT[diet_type])
    return texts
