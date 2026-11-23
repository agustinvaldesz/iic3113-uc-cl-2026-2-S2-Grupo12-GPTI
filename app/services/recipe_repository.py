"""
Recetas guardadas en la base de datos.

Solo las recetas aprobadas se usan para recomendar y armar menús (RN-01).
Las recetas se entregan como diccionarios con el mismo formato de recipes.json,
para que funcionen con el filtro de la SC-1 y con la cotización de la SC-2.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models_db import RecipeDB
from app.services.llm_service import load_recipes

def recipe_to_dict(recipe: RecipeDB) -> dict:
    return {
        "id": recipe.id,
        "title": recipe.title,
        "category": recipe.intent_category,
        "prep_time": recipe.prep_time,
        "servings": recipe.servings,
        "diet_type": recipe.diet_type,
        "allergens": list(recipe.allergens or []),
        "diet_focus": list(recipe.diet_focus or []),
        "ingredients": list(recipe.ingredient_lines or []),
        "instructions": recipe.instructions,
        "status": recipe.status,
        "source": recipe.source,
    }

def get_approved_recipes(db: Session) -> list[dict]:
    recipes = db.query(RecipeDB).filter(RecipeDB.status == "aprobada").order_by(RecipeDB.id).all()
    return [recipe_to_dict(r) for r in recipes]

def seed_recipes_if_empty(db: Session) -> int:
    """Carga las recetas base de recipes.json como aprobadas si la tabla está vacía."""
    if db.query(RecipeDB).first() is not None:
        return 0
    now = datetime.utcnow()
    base = load_recipes()
    for r in base:
        db.add(RecipeDB(
            title=r["title"],
            intent_category=r.get("category") or "balance",
            diet_type=r["diet_type"],
            allergens=r.get("allergens", []),
            diet_focus=r.get("diet_focus", []),
            servings=r.get("servings") or 4,
            prep_time=r.get("prep_time"),
            ingredient_lines=r.get("ingredients", []),
            instructions=r.get("instructions", ""),
            status="aprobada",
            source="manual",
            reviewed_at=now,
            review_notes="Receta base cargada por el equipo.",
        ))
    db.commit()
    return len(base)