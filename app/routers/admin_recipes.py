from datetime import datetime
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_manager
from app.models_db import RecipeDB, UserDB
from app.schemas.admin_recipes import GenerateRequest, GenerateResponse, RecipeIn, RecipeOut, ReviewRequest
from app.services import recipe_generator
from app.services.recipe_generator import GeneratorUnavailable, allergen_warnings

router = APIRouter(prefix="/api/admin/recipes", tags=["Gestión de recetas"])

def _to_out(r: RecipeDB) -> dict:
    return {
        "id": r.id, "title": r.title, "servings": r.servings, "prep_time": r.prep_time,
        "diet_type": r.diet_type, "allergens": r.allergens or [], "diet_focus": r.diet_focus or [],
        "ingredients": r.ingredient_lines or [], "instructions": r.instructions,
        "status": r.status, "source": r.source, "created_at": r.created_at,
        "reviewed_at": r.reviewed_at, "review_notes": r.review_notes,
        "warnings": allergen_warnings(r.ingredient_lines or [], r.allergens or []),
    }

def _apply(recipe: RecipeDB, data: RecipeIn) -> None:
    recipe.title = data.title
    recipe.servings = data.servings
    recipe.prep_time = data.prep_time
    recipe.diet_type = data.diet_type
    recipe.allergens = list(dict.fromkeys(data.allergens))
    recipe.diet_focus = list(dict.fromkeys(data.diet_focus))
    recipe.ingredient_lines = data.ingredients
    recipe.instructions = data.instructions
    recipe.intent_category = data.diet_focus[0]

def _get(db: Session, recipe_id: int) -> RecipeDB:
    recipe = db.query(RecipeDB).filter(RecipeDB.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receta no encontrada.")
    return recipe

@router.get("", response_model=List[RecipeOut])
def list_recipes(
    status_filter: Optional[Literal["pendiente", "aprobada", "rechazada"]] = "pendiente",
    manager: UserDB = Depends(get_current_manager),
    db: Session = Depends(get_db),
):
    """Recetas por estado (por defecto, las pendientes de revisión)."""
    query = db.query(RecipeDB)
    if status_filter:
        query = query.filter(RecipeDB.status == status_filter)
    return [_to_out(r) for r in query.order_by(RecipeDB.created_at.desc()).all()]

@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(data: RecipeIn, manager: UserDB = Depends(get_current_manager), db: Session = Depends(get_db)):
    """Receta subida a mano por un gestor: queda aprobada de inmediato (la revisó quien la sube)."""
    now = datetime.utcnow()
    recipe = RecipeDB(status="aprobada", source="manual", created_by=manager.id,
                      reviewed_by=manager.id, reviewed_at=now)
    _apply(recipe, data)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return _to_out(recipe)

@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_201_CREATED)
def generate_recipes(req: GenerateRequest, manager: UserDB = Depends(get_current_manager), db: Session = Depends(get_db)):
    """Pide recetas a la IA y las guarda como pendientes para que el gestor las revise."""
    try:
        drafts, discarded = recipe_generator.generate_drafts(req)
    except GeneratorUnavailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    created = []
    for draft in drafts:
        recipe = RecipeDB(status="pendiente", source="llm", created_by=manager.id)
        _apply(recipe, draft)
        db.add(recipe)
        created.append(recipe)
    db.commit()
    return {"created": [_to_out(r) for r in created], "discarded": discarded}

@router.put("/{recipe_id}", response_model=RecipeOut)
def edit_recipe(recipe_id: int, data: RecipeIn, manager: UserDB = Depends(get_current_manager), db: Session = Depends(get_db)):
    """Corrige una receta (por ejemplo, alérgenos o cantidades) antes de aprobarla."""
    recipe = _get(db, recipe_id)
    _apply(recipe, data)
    db.commit()
    db.refresh(recipe)
    return _to_out(recipe)

@router.post("/{recipe_id}/approve", response_model=RecipeOut)
def approve_recipe(recipe_id: int, review: ReviewRequest, manager: UserDB = Depends(get_current_manager), db: Session = Depends(get_db)):
    recipe = _get(db, recipe_id)
    recipe.status, recipe.reviewed_by, recipe.reviewed_at = "aprobada", manager.id, datetime.utcnow()
    recipe.review_notes = review.notes
    db.commit()
    db.refresh(recipe)
    return _to_out(recipe)

@router.post("/{recipe_id}/reject", response_model=RecipeOut)
def reject_recipe(recipe_id: int, review: ReviewRequest, manager: UserDB = Depends(get_current_manager), db: Session = Depends(get_db)):
    if not review.notes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Indica el motivo del rechazo.")
    recipe = _get(db, recipe_id)
    recipe.status, recipe.reviewed_by, recipe.reviewed_at = "rechazada", manager.id, datetime.utcnow()
    recipe.review_notes = review.notes
    db.commit()
    db.refresh(recipe)
    return _to_out(recipe)